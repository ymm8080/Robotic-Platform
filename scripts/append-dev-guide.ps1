param()
$target = Join-Path "D:\EWM ROBOT\CODEBASE OVERVIEW" "CODEBASE OVERVIEW $((Get-Date).ToString('yyyy-MM-dd')) V2.md"

if (-not (Test-Path $target)) { Write-Output "ERROR: $target not found"; exit 1 }

$raw = Get-Content $target -Raw -Encoding UTF8
if ($raw -match '## 14\. (Installation Guide|安装指南)') { Write-Output "Dev sections already exist"; exit 0 }

# Remove old footer
$raw = $raw -replace '(?s)---\s*\*文档自动生成.*?\*由 Claude Code 汇总分析\*', ''
$raw = $raw.Trim()

$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Build the dev guide content (ASCII-safe, using here-string)
$extra = @'


## 14. Installation Guide (All D: Drive)

### 14.1 Prerequisites

| Requirement | Minimum | Recommended | Notes |
|-------------|---------|-------------|-------|
| OS | Windows 10 22H2+ | Windows 11 / Server 2022 | WSL2 required |
| CPU | 4 cores | 8 cores | Runs 10 containers |
| RAM | 8 GB | 16 GB | ~6 GB actual usage |
| Disk | 20 GB free | 50 GB SSD | All on D: drive |
| Docker | Docker Desktop 4.30+ | Latest | - |
| WSL2 | Ubuntu 22.04 | Ubuntu 24.04 | rootfs + VHDX on D: |

### 14.2 Install Docker Desktop (D: Drive)

```powershell
# Step 1: Enable WSL2 (Admin PowerShell)
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
# -> Reboot

# Step 2: Install Linux kernel update
# https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi

# Step 3: Set WSL2 as default
wsl --set-default-version 2

# Step 4: Install Ubuntu to D:
mkdir D:\wsl
wsl --import Ubuntu D:\wsl\ubuntu D:\tmp\ubuntu-rootfs.tar.xz --version 2

# Step 5: Migrate VHDX to D:
wsl --shutdown
# Move VHDX from C:\Users\<user>\AppData\... to D:\wsl\
# Registry: HKCU\...\Lxss -> BasePath -> D:\wsl

# Step 6: Install Docker Desktop to D:\Docker
# Download installer, select Use WSL 2 based engine, path D:\Docker\

# Step 7: Docker data on D:
# Settings -> Docker Engine -> add "data-root": "D:\\docker\\data"
```

### 14.3 Clone & Start

```powershell
cd D:\EWM ROBOT
git clone https://github.com/ymm8080/EWM-ROBOT-Platform.git "ROBOTIC PLATFORM CODES"
cd "ROBOTIC PLATFORM CODES"
copy .env.example .env
notepad .env
echo "your-sap-password" > secrets\sap_password.txt
docker compose up -d --build
docker compose ps
```

## 15. VDA5050 Protocol

### 15.1 Topic Structure

```
vda5050/{manufacturer}/{serialNumber}/...
  connection          # ONLINE/OFFLINE/CONNECTIONBROKEN
  state               # Position/battery/errors/load
  order               # Order commands
  visualization       # Trajectory/speed
  instantActions      # Emergency stop/pause/resume
  factsheet           # Robot capability description
```

### 15.2 Order State Machine

```
CREATED > DISPATCHED > EXECUTING > COMPLETED > SAP_CONFIRMED
                         v
                      FAILED > DLQ
```

| State | Description |
|-------|-------------|
| CREATED | SAP order received, written to outbox |
| DISPATCHED | Published to MQTT, waiting for AGV |
| EXECUTING | AGV executing |
| COMPLETED | AGV done, waiting for SAP confirm |
| SAP_CONFIRMED | SAP confirmed, final state |
| FAILED | Error, moved to dead letter queue |

### 15.3 Instant Action Types

| actionType | Description | blockingType |
|-----------|-------------|-------------|
| MOVE_TO | Move to coordinates | HARD |
| PICK | Pick from shelf/conveyor | HARD |
| PLACE | Place to shelf/conveyor | HARD |
| CHARGE | Go charge | SOFT |
| CANCEL_ORDER | Cancel current order | HARD |
| STOP | Emergency stop | HARD |
| RESUME | Resume operation | SOFT |
| SET_SPEED | Set max speed | SOFT |

## 16. Development Guide

### 16.1 Local Dev Workflow

```powershell
# Start all services
docker compose up -d --build

# Edit sap-bridge (Python) then restart
docker compose restart sap-bridge
docker compose logs -f --tail=100

# Edit Node-RED flows
# http://localhost:1880 visual editor, click Deploy
docker compose restart nodered

# Edit Dashboard (React TS) then rebuild
docker compose up -d --build dashboard

# Edit Watchdog then restart
docker compose restart watchdog
```

### 16.2 Testing

```powershell
# E2E tests
npx playwright test
npx playwright test --headed

# SAP Bridge unit tests
docker compose exec sap-bridge python -m pytest tests/ -v

# Send test order
python scripts\test-order.py

# MQTT manual test
mosquitto_pub -t "vda5050/demo/AGV-001/order" -m '{"headerId":1}'
mosquitto_sub -t "vda5050/+/+/connection" -v
```

### 16.3 Dev Standards

- **TypeScript** for new services (strategy engine, MCP services)
- **Python 3.11+** for sap-bridge module
- **JavaScript ES6+** for Node-RED flows
- Coverage >= 80%, zero lint errors
- Conventional Commits for git messages
- ADR for architecture changes (10_adr/)
- VDA5050 message fields are immutable (needs ADR)
- New robot brands -> strategy pattern, not core logic changes

## 17. Database Guide

### 17.1 Current Schema (SQLite)

```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    robot_id TEXT, zone_id TEXT,
    version INTEGER DEFAULT 1,   -- optimistic lock
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE outbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 17.2 Outbox Pattern

```
orders -> outbox_events(PENDING)
              | periodic poll
         outbox processor
              | success -> SENT
              | fail -> retry -> 5x -> DLQ
```

Rules:
- Order creation MUST write to outbox (transactional)
- Max 5 retries, 30s interval
- Exceeded -> dead letter queue + alert

### 17.3 PostgreSQL Migration (v4.0)

```sql
-- sql/init-pg.sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_no VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    robot_id VARCHAR(128),
    location JSONB,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Migration tool: scripts/data-migration-sqlite-to-pg.sh

## 18. Contribution Guide

### 18.1 Branch Strategy

```
master        > Production-ready
  develop     > Integration branch
  feat/*      > Feature development
  fix/*       > Bug fixes
  release/*   > Release prep
```

### 18.2 PR Flow

1. Create feat/xxx from master
2. Develop + local test
3. PR -> develop
4. CI (E2E + unit tests)
5. Code review + merge
6. Regression test -> master

## 19. Security Design

| Measure | Implementation | Description |
|---------|---------------|-------------|
| Port binding | 127.0.0.1: prefix | All services localhost only |
| Docker Socket Proxy | tecnativa/docker-socket-proxy | Watchdog: stats/ps only, no exec |
| Docker Secrets | secrets/sap_password.txt | Password not in env vars |
| Read-only mounts | :ro suffix | Config/code read-only in containers |
| no-new-privileges | security_opt | Prevent privilege escalation |
| Log overflow protection | max-size:10m, max-file:3 | <=30MB per container |
| Resource limits | deploy.resources.limits | Hard CPU/memory caps |
| IP whitelist | nodered/settings.js | Rescue dashboard IP whitelist |
| Safe mode | Watchdog + Redis | Auto-stop dispatch on anomaly |
| Offline survival | Nginx rescue page | Operable even when Node-RED down |

## 20. Tech Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Container Runtime | Docker / Compose | 27.x / v2.x | Container orchestration (10 services) |
| Message Broker | Mosquitto (MQTT) | 2.x | VDA5050 protocol routing |
| Cache/Queue | Redis | 7-alpine | Session state, pub/sub |
| Database | SQLite -> PG(v4.0) | - | Persistence + Outbox |
| Orchestration | Node-RED | 3.1.9 | Order state machine, SAP bridge |
| SAP Bridge | Python FastAPI + pyrfc | 3.11 | OData/RFC integration |
| Dashboard | React + TypeScript + Nginx | - | Operations SPA |
| Health Monitor | Python Watchdog | 3.11 | 3-tier circuit breaker |
| LLM Translation | Dify API | latest | NL to commands |
| E2E Testing | Playwright | - | Cross-browser tests |
| Log Collection | Fluent Bit | - | Container log aggregation |
| Security Proxy | Docker Socket Proxy | - | Permission isolation |

## 21. KPIs

| Metric | Current | Target |
|--------|---------|--------|
| Containers | 10 | 12 (v4.0) |
| E2E Tests | 7 spec | 15+ |
| Unit Tests | 4 cases | 40+ |
| Order Latency | ~10-30s | <10s |
| Watchdog Response | <3s | <1s |

## 22. Operations Commands

```powershell
docker compose ps                     # All service status
docker compose logs -f --tail=100     # Live logs
docker compose logs nodered --tail=50 # Specific service
docker compose restart nodered        # Restart single service
docker compose down                   # Stop all
docker compose down -v                # Stop + delete volumes (WARNING: data loss)
docker compose up -d --build          # Rebuild and start
docker stats                          # Container resource monitor
```

## 23. Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| docker compose up port conflict | Host service uses same port | Change *_EXTERNAL_PORT in .env |
| Dify startup >5 min | First-time model download | Configure offline HuggingFace |
| SAP Bridge crashes | Wrong SAP params | Check SAP_ASHOST/SAP_SYSNR |
| Node-RED restart loop | Redis not ready | docker compose logs redis |
| WSL2 fills C: drive | VHDX not migrated | Follow 14.2 Step 5 |
| Docker images fill C: | data-root on C: | Change to D:\docker\data |

---

*Document auto-generated: TIMESTAMP_PLACEHOLDER | Scripts: scripts\generate-codebase-overview.ps1 + scripts\append-dev-guide.ps1*
'@

# Append (replace timestamp placeholder)
$extra = $extra -replace 'TIMESTAMP_PLACEHOLDER', $ts
$raw + "`r`n" + $extra | Out-File -FilePath $target -Encoding utf8
Write-Output "Done - dev sections appended to $target"
