# SAP EWM → Multi-Brand Robot Dispatch Platform — Development Plan

**Project Root**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/`
**Current Version**: v3.4 (2026-06-02)
**Platform Goal**: Industrial-grade, fault-tolerant, multi-brand robot dispatch integrated with SAP EWM via VDA5050 protocol.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Production Floor                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ KUKA KMR │  │  MiR250  │  │OTTO 1500 │  │ (More…)  │ │
│  │  iiwa    │  │  (AGV)   │  │  (AGV)   │  │          │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │             │             │             │        │
│       └─────────────┼─────────────┼─────────────┘        │
│                     │     MQTT (VDA5050)                 │
│                     ▼                                    │
│              ┌──────────────┐                            │
│              │    MQTT      │  Mosquitto :1883            │
│              │   Broker     │  WebSocket :9001           │
│              └──────┬───────┘                            │
│                     │                                    │
└─────────────────────┼────────────────────────────────────┘
                      │
         ┌────────────┼────────────┬──────────────┐
         ▼            ▼            ▼              ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │ Node-RED │ │  Redis   │ │ Watchdog │ │  Nginx Rescue│
   │  :1880   │ │  :6379   │ │  :9090   │ │  :8080       │
   │Orchestrat│ │Cache/PS  │ │Health    │ │Offline Dash  │
   └────┬─────┘ └──────────┘ └──────────┘ └──────────────┘
        │                        ▲
        ▼                        │
   ┌──────────┐            ┌──────────────┐
   │SAP Bridge│◄───────────│Docker Socket │
   │ FastAPI  │            │   Proxy      │
   │  :8000   │            │  (Read-only) │
   └────┬─────┘            └──────────────┘
        │
        ▼
   ┌──────────────────────────────────────┐
   │         SAP EWM (S/4HANA 2022)        │
   │  OData / RFC / IDoc                   │
   └──────────────────────────────────────┘
```

### Stack
| Service | Tech | Purpose |
|---------|------|---------|
| Node-RED | Node.js 3.1.9 | Visual orchestration, dispatch logic |
| SAP Bridge | Python FastAPI + pyrfc | SAP EWM OData/RFC integration |
| Redis 7 | Key-Value Store | Session state, pub/sub, caching |
| MQTT Broker | Mosquitto 2 | VDA5050 message routing |
| Watchdog | Python | Health monitoring, circuit-breaker |
| Dify API | LLM Platform | Natural language translation layer |
| Nginx Rescue | Nginx Alpine | Offline-capable monitoring dashboard |
| SQLite | Embedded | Node-RED persistent storage |

---

## 2. Current State (v3.4)

### ✅ Completed
- Docker Compose infrastructure with all 9 services
- MQTT broker with VDA5050 topic routing
- Redis with TTL-based memory management
- SAP Bridge with OData/RFC integration
- Watchdog health monitoring with circuit-breaker
- Nginx Rescue offline dashboard
- SQLite init with migration pattern
- Docker Socket Proxy (read-only security isolation)
- Log rotation (max 10MB per file, 3 files)
- Named volumes (no bind-mount dependency)
- Resource limits on all containers
- Healthchecks on all services
- Dual IDE synchronization (Cursor + Qoder)
- 23 synchronized AI skills
- Memory management system (MEMORY.md, MEMORY_SYSTEM_GUIDE.md)

### 🔴 Known Issues
1. `erl_crash.dump` in root (from some Erlang process crash)
2. `node_modules/` committed (not in .gitignore)
3. `.tmp` files in root (`Skills_Inventory*.xlsx.tmp`)
4. Some configs may drift between .cursor/ and .qoder/
5. No CI/CD pipeline configured
6. No automated test suite

---

## 3. Development Phases

```
Phase 0: Workspace Hardening ─── Day 1-2
Phase 1: Core Stability ──────── Week 1-2
Phase 2: Feature Completeness ── Week 3-6
Phase 3: Production Readiness ── Week 7-8
Phase 4: Continuous ──────────── Ongoing
```

---

## Phase 0: Workspace Hardening (Days 1-2)

### 0.1 — Workspace Setup
- [ ] Set `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/` as permanent project root
- [ ] Configure `.claude/settings.json` with project-scoped permissions
- [ ] Verify dual IDE sync mechanism works from CODEBASE root
- [ ] Update path references in all configs to use new absolute root

### 0.2 — Hygiene Cleanup
- [ ] Add `erl_crash.dump`, `node_modules/`, `*.tmp` to `.gitignore`
- [ ] Remove stale `.tmp` files from root
- [ ] Review `node_modules/` — commit only if needed (prefer no)
- [ ] Verify `.env.example` matches actual `.env` structure
- [ ] Clean up temp skills directories (`temp-skills/`)

### 0.3 — Documentation Baseline
- [ ] Update all doc file paths to CODEBASE root
- [ ] Ensure `CLAUDE.md` / `AGENTS.md` reference absolute paths
- [ ] Create `docs/INDEX.md` — master document index

---

## Phase 1: Core Stability (Weeks 1-2)

**Goal**: Make all 9 services bulletproof — secrets correctly managed, every service survives kills/reboots, no memory leaks, SAP calls rate-limited and retried, Watchdog proven to auto-recover.

**Execution Order**:
```
Week 1: 1.1 Infrastructure → 1.2 MQTT → 1.3 Redis
Week 2: 1.4 SAP Bridge → 1.5 Watchdog → Integration Smoke Test
```

---

### 1.1 — Infrastructure Hardening (Begin Week 1)

#### 1.1.1 — Secrets Audit (P0)
- [ ] Run full secrets scan across all files:
  ```bash
  grep -rn "password\|secret\|PASSWORD\|SECRET" \
    --include="*.{yml,yaml,js,ts,py,json,env,txt,md,conf}" \
    --exclude-dir={.git,node_modules,secrets} \
    "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/"
  ```
- [ ] Verify `secrets/sap_password.txt` exists and is in `.gitignore`
- [ ] Check `docker-compose.yml` for env vars vs Docker Secrets:
  - File: `docker-compose.yml` lines 150-151 — should use `SAP_PASSWORD_FILE=/run/secrets/sap_password`
  - Verify all services: sap-bridge ✅, watchdog (check), dify (check)
- [ ] Create `.gitignore` entry for `secrets/` (if missing)
- [ ] Document approved secret locations: `docs/secrets-management.md`
  ```markdown
  - SAP password:    secrets/sap_password.txt → Docker Secret → /run/secrets/sap_password
  - Dify DB password: .env variable DIFY_DB_PASSWORD (no better option today)
  - API tokens:      .env variables (Feishu, WeCom)
  ```

#### 1.1.2 — Network Lockdown (P1)
- [ ] Review `docker-compose.yml` line 509: `internal: false`
  - Intent: allow port mapping to host for MQTT (1883), Node-RED (1880), etc.
  - Verify no service exposes ports unnecessarily:
    - sap-bridge: no ports mapped ✅ (internal-only, line 137 comment)
    - redis: `127.0.0.1:6379` ✅ (loopback only)
    - mqtt: `127.0.0.1:1883` ✅ (loopback)
    - watchdog: `127.0.0.1:9090` ✅ (loopback)
    - dify: `127.0.0.1:5001` ✅ (loopback)
    - nginx-rescue: `8080:80` — ⚠️ confirm access policy
- [ ] Create network diagram: `01_architecture/diagrams/network-topology.md`
- [ ] Document firewall rules: `05_reference/network/firewall-rules.md`

#### 1.1.3 — Backup/Restore Procedure (P1)
- [ ] Document backup script: `scripts/backup-volumes.sh`
  ```bash
  #!/bin/bash
  # Backup all named volumes to D:/EWM ROBOT/backups/
  BACKUP_DIR="D:/EWM ROBOT/backups/$(date +%Y%m%d_%H%M%S)"
  VOLUMES="nodered-data redis-data dify-data mqtt-data mqtt-logs sap-bridge-logs watchdog-logs"
  
  docker compose stop
  for vol in $VOLUMES; do
    docker run --rm -v ${vol}:/source -v ${BACKUP_DIR}:/backup alpine \
      tar czf /backup/${vol}.tar.gz -C /source .
  done
  docker compose start
  ```
- [ ] Create restore script: `scripts/restore-volumes.sh`
- [ ] Test backup → destroy volume → restore → verify all services healthy
- [ ] Document in `03_operations/runbooks/volume-backup.md`
- [ ] Schedule daily backup: cron job entry in `02_deployment/checklists/cron-jobs.md`

#### 1.1.4 — NTP Clock Sync (P1)
- [ ] Install/verify NTP on host: `w32tm /query /status`
- [ ] Run NTP appendix checklist from `docs/APPENDIX_NTP.md`
- [ ] Verify all containers inherit host time (check TZ=UTC vs local time)
- [ ] Document time source + drift tolerance in `05_reference/network/ntp-config.md`

#### 1.1.5 — Log Rotation Verification (P2)
- [ ] Force log rotation on one service:
  ```bash
  docker logs robot-platform-nodered --tail 1000000 > /dev/null  # fill buffer
  # Check log driver config: max-size: "10m", max-file: "3"
  ```
- [ ] Verify no log loss: rotate, then check recent entries intact
- [ ] Document log retention config: `05_reference/standards/logging-standards.md`

#### 1.1.6 — Workspace Hygiene (Day 1)
- [ ] Clean up root-level debris:
  ```bash
  rm -f "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/erl_crash.dump"
  rm -f "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/"*.tmp
  ```
- [ ] Update `.gitignore`:
  ```
  erl_crash.dump
  node_modules/
  *.tmp
  secrets/
  .env
  ```
- [ ] Run `docker compose down` then `docker compose up -d` — verify zero crashes on start
- [ ] Verify all 9 services show "running" + "healthy"

---

### 1.2 — MQTT Reliability (Week 1)

#### 1.2.1 — QoS & Sequence Numbers Audit
- [ ] Audit ALL VDA5050 publishers for QoS setting:
  - Check Node-RED flows (MQTT output nodes → QoS field)
  - Check SAP Bridge MQTT client config
  - Check Watchdog MQTT publisher
- [ ] Audit VDA5050 payloads for `sequenceNumber` field
  - Must be monotonically increasing per topic `vda5050/{manufacturer}/{serialNumber}/...`
- [ ] Create MQTT publish wrapper with auto-seqnumber:
  - File: `sap-bridge/services/mqtt-publisher.ts`
  ```typescript
  interface VDA5050Message {
    headerId: number;
    timestamp: string;
    version: string;
    manufacturer: string;
    serialNumber: string;
  }
  // Sequence number stored per topic in Redis INCR
  async function publishWithSequence(topic: string, message: object) {
    const seq = await redis.incr(`mqtt:seq:${topic}`);
    await mqttClient.publish(topic, JSON.stringify({ ...message, sequenceNumber: seq }), { qos: 1 });
  }
  ```

#### 1.2.2 — Broker Reconnect Behavior
- [ ] Test scenario: kill Mosquitto → verify auto-recovery
  ```bash
  docker kill robot-platform-mqtt
  # Wait 10s
  docker compose up -d mqtt
  ```
- [ ] Verify ALL MQTT clients reconnect within 30s:
  - Node-RED MQTT nodes (check logs: `docker logs robot-platform-nodered --tail 50 | grep -i mqtt`)
  - SAP Bridge (check logs: `docker logs robot-platform-sap-bridge --tail 20 | grep -i mqtt`)
  - Watchdog (check logs)
- [ ] Configure clean session=false + clientId persistence for durable subscriptions
- [ ] Document reconnect timeout expectations: `05_reference/protocols/mqtt/mqtt-config.md`

#### 1.2.3 — Topic Hierarchy Validation
- [ ] Verify topic structure matches VDA5050 spec:
  ```
  vda5050/{manufacturer}/{serialNumber}/connection
  vda5050/{manufacturer}/{serialNumber}/state
  vda5050/{manufacturer}/{serialNumber}/order
  vda5050/{manufacturer}/{serialNumber}/instantActions
  vda5050/{manufacturer}/{serialNumber}/visualization
  ```
- [ ] Verify subscription wildcards work:
  ```bash
  mosquitto_sub -t "vda5050/+/+/state" -v  # all robots state
  mosquitto_sub -t "vda5050/+/+/#" -v       # all topics all robots
  ```
- [ ] Check for topic conflicts (two brands share same manufacturer prefix?)

#### 1.2.4 — Connection State Tracking
- [ ] Create heartbeat monitor service:
  - File: `sap-bridge/services/heartbeat-monitor.ts`
  - Subscribe to `vda5050/+/+/connection`
  - Track last heartbeat per robot in Redis HASH with TTL
  ```redis
  HSET robot:connection:KUKA-001 state ONLINE lastSeen 1718960000
  EXPIRE robot:connection:KUKA-001 300
  ```
- [ ] Alert if any robot shows OFFLINE > 30s (via Watchdog notification channel)
- [ ] Robot status API endpoint:
  ```bash
  GET /api/v1/robots/status
  # Returns: [{ id, brand, state, lastSeen, battery }]
  ```

#### 1.2.5 — Last-Will-and-Testament (LWT)
- [ ] Configure LWT on all robot MQTT connections:
  - Topic: `vda5050/{manufacturer}/{serialNumber}/connection`
  - Payload: `{"state": "DISCONNECTED", "timestamp": "<ISO8601>"}`
  - Retain: `true` (so new subscribers see current state immediately)
- [ ] Verify LWT triggers correctly:
  - Kill one robot simulator → MQTT broker publishes LWT → monitor sees DISCONNECTED
- [ ] Document LWT config: `05_reference/protocols/mqtt/lwt-config.md`

#### 1.2.6 — MQTT Integration Tests
- [ ] Create test: `sap-bridge/tests/mqtt/reconnect.test.ts`
  - Kill broker → verify reconnect → verify no message loss
- [ ] Create test: `sap-bridge/tests/mqtt/sequence-order.test.ts`
  - Publish 1000 messages with sequence numbers → verify order preserved
- [ ] Create test: `sap-bridge/tests/mqtt/lwt.test.ts`
  - Drop connection → verify LWT message received

---

### 1.3 — Redis Stability (Week 1-2)

#### 1.3.1 — TTL Enforcement Audit
- [ ] Scan all code for Redis SET without EXPIRE:
  ```bash
  grep -rn "redis\.set\|redis\.setex\|SET\|HSET" \
    --include="*.{js,ts,py}" \
    "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/sap-bridge/" \
    "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/nodered/" \
    "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/watchdog/"
  ```
- [ ] For every key pattern, add TTL:
  | Key pattern | TTL | Location |
  |-------------|-----|----------|
  | `session:robot:*` | 3600s (1h) | sap-bridge |
  | `robot:connection:*` | 300s (5min) | sap-bridge |
  | `mqtt:seq:*` | 86400s (24h) | sap-bridge |
  | `nodered:*` | varies | Node-RED flows |
  | `inventory:*` | 300s (5min) | sap-bridge |
- [ ] Verify `redis.conf` eviction policy: `maxmemory-policy allkeys-lru`
  - File: `redis/redis.conf`
- [ ] Document TTL matrix: `05_reference/standards/redis-key-conventions.md`

#### 1.3.2 — Memory Pressure Test
- [ ] Simulate memory pressure:
  ```bash
  # Fill Redis with test data to 80% memory
  for i in $(seq 1 100000); do
    redis-cli SET test:pressure:$i "$(head -c 1000 /dev/zero | tr '\0' 'A')" EX 3600
  done
  ```
- [ ] Monitor: `docker exec robot-platform-redis redis-cli INFO memory`
- [ ] Verify eviction policy removes oldest keys, does NOT crash
- [ ] Set up Watchdog alert at 75% memory usage
- [ ] Test recovery: watchdog triggers safe-mode when Redis >80%

#### 1.3.3 — Keyspace Notifications
- [ ] Verify Redis config: `CONFIG SET notify-keyspace-events KEA`
  - Check `redis/redis.conf` for `notify-keyspace-events KEA`
- [ ] Subscribe to expiry events for session cleanup:
  ```bash
  redis-cli PSUBSCRIBE "__keyevent@0__:expired"
  ```
- [ ] Verify Node-RED subscribes to expired sessions and cleans up stale state
- [ ] Document keyspace notification pattern: `05_reference/standards/redis-keyspace.md`

#### 1.3.4 — Redis Persistence
- [ ] Enable AOF + RDB in `redis/redis.conf`:
  ```
  save 900 1        # RDB: 15 min if at least 1 key changed
  save 300 10       # RDB: 5 min if at least 10 keys changed
  save 60 10000     # RDB: 1 min if at least 10000 keys changed
  appendonly yes    # AOF enabled
  appendfsync everysec
  ```
- [ ] Verify persistence files in named volume:
  ```bash
  docker exec robot-platform-redis ls -la /data/
  # Should see: dump.rdb, appendonly.aof
  ```
- [ ] Test restart persistence: fill data → restart redis → verify data survives
- [ ] Document backup + restore procedure for Redis data

#### 1.3.5 — Redis Config Hardening
- [ ] Add `requirepass` to `redis/redis.conf` (optional — only if exposed beyond internal net)
- [ ] Rename dangerous commands in `redis/redis.conf`:
  ```
  rename-command FLUSHALL ""
  rename-command FLUSHDB ""
  rename-command CONFIG ""
  ```
- [ ] Increase max memory to `8GB` in `redis.conf`: `maxmemory 8gb`
- [ ] Verify `redis.conf` is mounted as read-only in `docker-compose.yml` (already `:ro` ✅)

---

### 1.4 — SAP Bridge Stability (Week 2)

#### 1.4.1 — OData Rate Limiter Validation
- [ ] Review existing rate limiter code: `sap-bridge/services/rate-limiter.ts`
- [ ] Verify token bucket config: 80 tokens/minute (safe margin from SAP's 100)
- [ ] Load test:
  ```bash
  # Fire 120 requests in 60 seconds
  for i in $(seq 1 120); do
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1880/sap-bridge/odata/test &
  done
  wait
  ```
- [ ] Verify: first 80 succeed (200), next 40 are throttled (429)
- [ ] Add rate limit headers to response: `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- [ ] Document rate limit config: `05_reference/sap/auth/sap-rate-limits.md`

#### 1.4.2 — Outbox Pattern Reliability
- [ ] Review outbox implementation:
  - File: `sap-bridge/outbox/outbox-handler.ts`
  - Must: atomic DB write → outbox INSERT → async worker picks up
  - Must: exponential backoff on SAP failure (1s, 2s, 4s, 8s, 16s, max 60s)
  - Must: max 5 retries, then deadletter
- [ ] Test: kill SAP during outbox write
  ```bash
  # 1. Send order (writes to outbox)
  curl -X POST http://localhost:1880/sap-bridge/orders -d '{...}'
  # 2. Kill SAP connectivity (block port)
  # 3. Verify outbox queues "pending"
  # 4. Restore SAP connectivity
  # 5. Verify outbox processes and order confirms
  ```
- [ ] Create monitoring query for stuck outbox items:
  - Endpoint: `GET /api/v1/admin/outbox/pending`
  - Count + oldest pending + max retries exceeded
- [ ] Add Watchdog alert on outbox backlog > 100 items

#### 1.4.3 — SAP Connection Pool Health
- [ ] Review SAP connection pool: `sap-bridge/services/sap-pool.ts`
- [ ] Verify max connections = 5 (config: `SAP_MAX_CONNECTIONS=5`)
- [ ] Add health check endpoint: `GET /health/sap`
  - Returns: `{"connected": true, "poolSize": 5, "active": 2, "idle": 3}`
- [ ] Add auto-reconnect on connection drop:
  - On `COMMUNICATION_FAILURE` → close pool → reopen after 5s delay
  - On `RFC_FAILURE` → retry once → if fails again, mark degraded
- [ ] Create test: `sap-bridge/tests/sap/pool-reconnect.test.ts`
- [ ] Create test: `sap-bridge/tests/sap/connection-timeout.test.ts`

#### 1.4.4 — CSRF Token Rotation
- [ ] Review CSRF token flow:
  - Fetch token: `GET /sap/bc/sec/csrf` → header `X-CSRF-Token: Fetch` → receives token
  - Use token: header `X-CSRF-Token: <token>` on POST/PUT/DELETE
- [ ] Verify token refresh before expiry:
  - SAP tokens expire after ~30 min of inactivity
  - Add refresh logic: fetch new token every 25 min
  - Store in Redis: `sap:csrf_token` with TTL 1500s
- [ ] Test: write order → wait 30 min → write another → verify second succeeds
- [ ] Document CSRF flow: `05_reference/sap/auth/csrf-token-flow.md`

#### 1.4.5 — SAP Error Code Documentation
- [ ] Compile known SAP error codes:
  | Code | Meaning | Recovery |
  |------|---------|----------|
  | 200 | OK | — |
  | 204 | No Content | — |
  | 400 | Bad Request | Check payload format |
  | 401 | Unauthorized | Refresh credentials |
  | 403 | Forbidden | Check authorization |
  | 404 | Not Found | Check URL |
  | 429 | Rate Limited | Backoff, retry |
  | 500 | Internal Error | Retry, escalate if persists |
  | RFC_FAILURE | RFC call failed | Reconnect pool, retry |
  | COMMUNICATION_FAILURE | Network error | Check SAP reachability |
- [ ] Create error handling doc: `05_reference/sap/ewm-api/sap-error-codes.md`
- [ ] Update Watchdog alert rules for SAP error rate > 5%

#### 1.4.6 — SAP Bridge Health Endpoints
- [ ] Create health check endpoint: `sap-bridge/main.py` → `/health`
  ```json
  {
    "status": "healthy",
    "sap_connected": true,
    "redis_connected": true,
    "outbox_pending": 3,
    "rate_limiter": {"remaining": 45, "reset_in": 30},
    "uptime_seconds": 123456
  }
  ```
- [ ] Create readiness endpoint: `/ready` — returns 200 only when SAP + Redis both connected
- [ ] Create liveness endpoint: `/live` — always returns 200 (process is up)
- [ ] Update Docker healthcheck in `docker-compose.yml` to use `/health`

---

### 1.5 — Watchdog Tuning (Week 2)

#### 1.5.1 — Circuit-Breaker Thresholds
- [ ] Review current thresholds in `watchdog/config.yaml`:
  - `CPU_THRESHOLD=80` (80% CPU triggers warning)
  - `CHECKPOINT_THRESHOLD=5000` (Node-RED checkpoint backlog)
  - `THROTTLE_RATE_MIN=10` (minimum msg/s before throttle)
  - `NORMAL_RATE_DEFAULT=50` (normal msg rate expected)
- [ ] Tune per-service thresholds:
  | Service | Metric | Warning | Critical | Action |
  |---------|--------|---------|----------|--------|
  | Node-RED | CPU | >70% | >85% | Throttle |
  | Node-RED | Memory | >512MB | >768MB | Safe mode |
  | Node-RED | Checkpoint backlog | >2000 | >5000 | Safe mode |
  | SAP Bridge | Error rate | >5% | >15% | Degrade |
  | Redis | Memory | >6GB (75%) | >7GB (87%) | Safe mode |
  | System | CPU | >80% | >90% | Notify |
- [ ] Document thresholds: `watchdog/config.yaml` (update inline)
- [ ] Add threshold change as config reload (no restart needed)

#### 1.5.2 — Safe-Mode Trigger Tests
- [ ] Test Redis OOM trigger:
  ```bash
  # Fill Redis to trigger OOM threshold
  redis-cli CONFIG SET maxmemory 100mb
  for i in $(seq 1 100000); do redis-cli SET test:$i "$(head -c 1000 /dev/zero | tr '\0' 'A')" EX 3600; done
  ```
  - Verify watchdog detects >80% memory → sets `watchdog:safe_mode` in Redis → Node-RED enters throttle
- [ ] Test Node-RED unhealthy trigger:
  ```bash
  docker kill robot-platform-nodered
  ```
  - Verify watchdog detects unhealthy → safe mode → notification → auto-restart
- [ ] Test CPU fatal trigger:
  - Stress CPU: `docker exec robot-platform-nodered dd if=/dev/zero of=/dev/null &` (in container)
  - Verify watchdog detects high CPU → throttles message rate → restores when CPU drops

#### 1.5.3 — Notification Channel Verification
- [ ] Test Feishu webhook:
  ```bash
  # Trigger a test alert
  curl -X POST http://localhost:9090/api/v1/alert/test -H "Content-Type: application/json" \
    -d '{"channel": "feishu", "message": "Phase 1 test alert"}'
  ```
- [ ] Test WeCom webhook:
  ```bash
  curl -X POST http://localhost:9090/api/v1/alert/test \
    -d '{"channel": "wecom", "message": "Phase 1 test alert"}'
  ```
- [ ] Verify notification appears in expected chat/channel
- [ ] Test alert on actual trigger: overload Redis → verify notification sent
- [ ] Document notification config: `docs/APPENDIX_NOTIFICATION.md`

#### 1.5.4 — Watchdog Integration Tests
- [ ] Create test suite: `watchdog/tests/test_integration.py`
  - Test: healthy service → watchdog reports healthy
  - Test: kill service → watchdog detects → notifies → attempts recovery
  - Test: safe mode toggle → verify Node-RED enters/exits safe mode
  - Test: multiple consecutive failures → watchdog escalates severity
  - Test: recovery after all services restored → watchdog exits safe mode
- [ ] Run tests: `cd watchdog && python -m pytest tests/ -v`
- [ ] Add test for each safe-mode trigger type
- [ ] Add test for each notification channel

#### 1.5.5 — Watchdog Self-Health
- [ ] Create `/health` endpoint on watchdog (port 9090):
  ```json
  {
    "status": "healthy",
    "uptime": 123456,
    "noded_healthy": true,
    "sap_bridge_healthy": true,
    "mqtt_healthy": true,
    "redis_healthy": true,
    "safe_mode_active": false,
    "last_recovery_attempt": 1718960000,
    "notification_channels": {"feishu": true, "wecom": false}
  }
  ```
- [ ] Watchdog monitors itself: if dead, Docker restart policy handles recovery
- [ ] Add grafana-exportable metrics: `watchdog_healthy 1`

---

### 1.6 — Phase 1 Integration Smoke Test (End of Week 2)

Run this full checklist before claiming Phase 1 complete:

```bash
# ═══════════════════════════════════════════════════════════════
# Phase 1 Integration Smoke Test
# ═══════════════════════════════════════════════════════════════

echo "=== 1. All Services Running ==="
docker compose ps
# Expected: all 9 services "Up" and "healthy"

echo "=== 2. Secrets Not Leaked ==="
grep -rn "sap_password\|PASSWORD=\|password=" --include="*.{yml,js,ts,py,env}" \
  --exclude-dir={.git,node_modules,secrets} . 2>/dev/null || echo "✅ No secrets in code"

echo "=== 3. MQTT Broker Reachable ==="
mosquitto_pub -t "healthcheck" -m "test" -r
mosquitto_sub -t "healthcheck" -C 1
# Expected: receives "test"

echo "=== 4. Redis Reachable + TTL Config ==="
docker exec robot-platform-redis redis-cli PING
# Expected: PONG
docker exec robot-platform-redis redis-cli CONFIG GET maxmemory
docker exec robot-platform-redis redis-cli CONFIG GET maxmemory-policy
# Expected: maxmemory=8gb, policy=allkeys-lru

echo "=== 5. SAP Bridge Health ==="
curl -f http://localhost:1880/sap-bridge/health
# Expected: {"status":"healthy",...}

echo "=== 6. Rate Limiter Works ==="
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:1880/sap-bridge/odata/test)
  if [ "$code" = "429" ]; then
    echo "✅ Rate limiter triggered at request $i"
    break
  fi
done

echo "=== 7. Watchdog Health ==="
curl -f http://localhost:9090/health
# Expected: {"status":"healthy",...}

echo "=== 8. Outbox Pattern (Kill Test) ==="
# Covered in 1.4.2 manual test — verify no stuck items
curl -s http://localhost:1880/api/v1/admin/outbox/pending | jq '.count'
# Expected: 0 (or low number, clearing quickly)

echo "=== 9. Log Rotation (No Bloat) ==="
docker exec robot-platform-nodered ls -la /data/ | grep -c "\.log"
# Verify no log file > 10MB

echo "=== 10. Connection Tracking ==="
# Start a dummy robot simulator
# Verify it appears in connection list
curl -s http://localhost:1880/api/v1/robots/status | jq '.'
# Expected: shows connected robot(s)

echo "=== Phase 1 Smoke Test Complete ==="
```

---

## Phase 2: Feature Completeness (Weeks 3-6)

**Goal**: Ship all core robot dispatch features — multi-brand support, full order lifecycle, deep SAP integration, ops dashboard, and optimized Node-RED flows.

**Execution Order** (sequential within each week, parallel between sub-teams):
```
Week 3: 2.1 Strategy Pattern + 2.3 SAP CRUD
Week 4: 2.2 Order Management + 2.4 Dashboard Skeleton
Week 5: 2.1 Brand Quirks + 2.3 IDoc + 2.5 Flow Audit
Week 6: 2.4 Dashboard Complete + 2.5 Optimization + Integration Test
```

---

### 2.1 — Multi-Brand Robot Strategy (Week 3-5)

**Pattern**: Strategy pattern per brand, registered via config injection.

#### 2.1.1 — ADR: Robot Brand Strategy Architecture
- [ ] Write ADR-006: Multi-brand strategy pattern decision
  - File: `10_adr/ADR-006-multi-brand-strategy.md`
  - Content: Why strategy over if-else, interface contract, brand registry design
- [ ] Write ADR-007: Simulator-first testing approach
  - File: `10_adr/ADR-007-simulator-first-testing.md`

#### 2.1.2 — Core Strategy Framework
- [ ] Create strategy interface: `sap-bridge/strategies/robot-strategy.ts`
  ```typescript
  // Expected contract:
  interface RobotStrategy {
    readonly brand: string;
    readonly supportedVersions: string[];
    handleState(state: VDA5050State): RobotState;
    handleAction(action: VDA5050Action): BrandAction;
    normalizeBattery(raw: number): { percent: number; voltage?: number };
    getQuirks(): BrandQuirk[];
  }
  ```
- [ ] Create base strategy with default VDA5050 behavior:
  - File: `sap-bridge/strategies/base-strategy.ts`
- [ ] Create brand registry with config injection:
  - File: `sap-bridge/strategies/registry.ts`
  - Load strategies from `sap-bridge/strategies/*.ts`, register by brand name
- [ ] Add TypeScript config if missing: `sap-bridge/tsconfig.json`

#### 2.1.3 — Brand-Specific Implementations
- [ ] **KUKA KMR iiwa** — `sap-bridge/strategies/kuka-strategy.ts`
  - VDA5050 v2.0.0
  - Custom action: lifting mechanism (`actionType: "lift"`)
  - State mapping: standard v2.0.0
  - Quirks: lift requires pre-navigate, lift height in mm
- [ ] **MiR250** — `sap-bridge/strategies/mir-strategy.ts`
  - VDA5050 v1.1.0 (older spec)
  - Navigate state drift: MiR reports `DRIVING` where spec expects `MOVING`
  - Quirk: MiR sends `WAITING` before `IDLE` after job complete
  - Workaround: map state with tolerance window (500ms debounce)
- [ ] **OTTO 1500** — `sap-bridge/strategies/otto-strategy.ts`
  - VDA5050 v2.0.0
  - Battery: millivolts → percentage conversion
  - Quirk: OTTO reports `CHARGING` state differently
  - Workaround: custom battery curve lookup table

#### 2.1.4 — Simulator Suite
- [ ] Create base simulator: `sap-bridge/simulators/base-simulator.ts`
  - Emits VDA5050 messages on MQTT
  - Responds to order commands
  - Reports connection state with heartbeat
- [ ] KUKA simulator: `sap-bridge/simulators/kuka-simulator.ts`
- [ ] MiR simulator: `sap-bridge/simulators/mir-simulator.ts`
- [ ] OTTO simulator: `sap-bridge/simulators/otto-simulator.ts`
- [ ] Simulator runner: `sap-bridge/simulators/run.ts`
  - CLI: `ts-node simulators/run.ts --brand KUKA --count 3`

#### 2.1.5 — Compliance Tests
- [ ] Create test suite: `sap-bridge/tests/strategies/compliance.test.ts`
  - Shared compliance matrix for all brands
  - Test all required VDA5050 state transitions
  - Test action execution per brand
  - Test error handling per brand quirks
- [ ] Brand-specific test: `sap-bridge/tests/strategies/kuka.test.ts`
- [ ] Brand-specific test: `sap-bridge/tests/strategies/mir.test.ts`
- [ ] Brand-specific test: `sap-bridge/tests/strategies/otto.test.ts`
- [ ] Registry test: `sap-bridge/tests/strategies/registry.test.ts`

#### 2.1.6 — Integration
- [ ] Wire strategy registry into SAP Bridge main app
  - File: `sap-bridge/main.py` → call strategy for brand-specific logic
- [ ] Add brand config to environment/config: `sap-bridge/config.yaml`
- [ ] Update `docker-compose.yml` if new volume mounts needed
- [ ] Verify end-to-end: simulator → MQTT → SAP Bridge → Redis

---

### 2.2 — Order Management (Week 4-5)

**Pattern**: Outbox pattern for SAP sync + priority queue in Redis.

#### 2.2.1 — Data Model
- [ ] Define order types: `sap-bridge/models/order.ts`
  ```typescript
  interface WarehouseOrder {
    id: string;
    type: 'PICK' | 'PUT' | 'MOVE' | 'CHARGE';
    priority: 0 | 1 | 2 | 3;  // 0=critical, 3=low
    source: string;            // SAP warehouse task ID
    robotBrand?: string;
    robotSerial?: string;
    status: OrderStatus;
    payload: VDA5050Order;
    createdAt: number;
    completedAt?: number;
  }
  
  type OrderStatus = 
    | 'CREATED' | 'ASSIGNED' | 'IN_PROGRESS' 
    | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  ```
- [ ] Update SQLite schema: `sql/migrations/002_orders.sql`
  ```sql
  CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    priority INTEGER DEFAULT 3,
    source TEXT,
    robot_brand TEXT,
    robot_serial TEXT,
    status TEXT DEFAULT 'CREATED',
    payload TEXT NOT NULL,
    created_at INTEGER DEFAULT (unixepoch()),
    completed_at INTEGER
  );
  CREATE INDEX idx_orders_status ON orders(status);
  CREATE INDEX idx_orders_priority ON orders(priority);
  ```

#### 2.2.2 — Order Lifecycle Service
- [ ] Create `sap-bridge/services/order-service.ts`
  - `createOrder(sapTask) → WarehouseOrder`
  - `assignOrder(orderId, robotId) → void`
  - `executeOrder(orderId) → void`  — publishes VDA5050 order to MQTT
  - `completeOrder(orderId) → void` — notifies SAP via outbox
  - `cancelOrder(orderId) → void`
  - `getOrderStatus(orderId) → OrderStatus`
- [ ] Create `sap-bridge/orders/order-mapper.ts`
  - SAP EWM warehouse task → VDA5050 order mapping
  - Handle different SAP task types (pick, put, move, charge)

#### 2.2.3 — Priority Queue
- [ ] Implement Redis sorted-set queue: `sap-bridge/queue/priority-queue.ts`
  ```redis
  # Score = priority (0 urgent, 3 low) + timestamp (for FIFO within priority)
  ZADD orders:queue {score} {orderId}
  ```
- [ ] Queue worker: `sap-bridge/queue/worker.ts`
  - Polls Redis for highest-priority order every 500ms
  - Assigns to available robot matching brand/type
  - Pushes to deadletter after 3 retries
- [ ] Deadletter handler: `sap-bridge/queue/deadletter.ts`
  - Store in SQLite with full error context
  - Alert via Watchdog notification channel
  - Manual retry endpoint

#### 2.2.4 — Batch Order Submission
- [ ] Create `sap-bridge/services/batch-service.ts`
  - Collect pending orders from SAP (poll every 60s)
  - Batch-create VDA5050 orders (max 10 per batch)
  - Submit to priority queue with staggered dispatch
  - Configurable: `BATCH_SIZE=10`, `BATCH_INTERVAL=60000`

#### 2.2.5 — Order API Endpoints
- [ ] REST API in SAP Bridge:
  ```yaml
  GET    /api/v1/orders              # List orders (filter by status, brand)
  POST   /api/v1/orders              # Create order manually
  GET    /api/v1/orders/{id}         # Get order details
  PUT    /api/v1/orders/{id}/cancel  # Cancel order
  GET    /api/v1/orders/queue        # View queue depth
  POST   /api/v1/orders/batch        # Submit batch
  ```
- [ ] Integration tests: `sap-bridge/tests/orders/api.test.ts`
- [ ] Unit tests for each service method

---

### 2.3 — SAP EWM Integration Deepening (Week 3-5)

#### 2.3.1 — CRUD Warehouse Tasks via OData
- [ ] Create `sap-bridge/services/ewm-warehouse-service.ts`
  - `getWarehouseTasks(filter) → WarehouseTask[]`
  - `createWarehouseTask(task) → WarehouseTask`
  - `updateWarehouseTask(id, changes) → void`
  - `confirmWarehouseTask(id) → void`  — mark complete in SAP
- [ ] OData endpoint wrappers:
  - File: `sap-bridge/services/odata/warehouse-tasks.ts`
  - Handle pagination (SAP returns max 100 records)
  - Handle SAP error codes with retry logic

#### 2.3.2 — Inventory Sync
- [ ] Create `sap-bridge/services/inventory-service.ts`
  - `syncStockFromSAP(location?) → Inventory[]`
  - `reportConsumption(material, qty, orderId) → void`
  - `reportProduction(material, qty, orderId) → void`
- [ ] Sync schedule: configurable cron (default: every 5 min)
- [ ] Redis cache: inventory with TTL (default: 300s)

#### 2.3.3 — Production Supply/Demand Matching
- [ ] Create `sap-bridge/services/production-service.ts`
  - Pull production orders from SAP EWM
  - Match material supply to production demand
  - Generate robot transport tasks for material movement
- [ ] Algorithm: nearest-available-robot + earliest-deadline-first
- [ ] File: `sap-bridge/services/matching/matcher.ts`

#### 2.3.4 — SAP IDoc Listener
- [ ] Create IDoc receiver service: `sap-bridge/idoc/listener.ts`
  - HTTP endpoint for SAP IDoc push (configurable port/path)
  - Parse IDoc XML (EDI_DC40 header, E1EDL01 segments)
  - Map to internal event and push to Redis pub/sub
- [ ] IDoc parsers:
  - `sap-bridge/idoc/parsers/warehouse-task.ts`  — LID task notifications
  - `sap-bridge/idoc/parsers/inventory.ts`       — stock changes
  - `sap-bridge/idoc/parsers/order-status.ts`    — order status updates
- [ ] Test with sample IDoc XML in `sap-bridge/tests/idoc/samples/`

#### 2.3.5 — SAP Batch Split Handling
- [ ] Create `sap-bridge/services/batch-split.ts`
  - Detect multi-pick warehouse tasks
  - Split into individual VDA5050 orders per pick location
  - Track partial completions
  - Recombine on final confirmation to SAP
- [ ] Config: `BATCH_SPLIT_ENABLED=true`, `MAX_SPLIT_PARTS=10`

#### 2.3.6 — Integration Tests
- [ ] Mock SAP server: `sap-bridge/tests/mocks/sap-server.ts`
  - Simulate OData responses, IDoc push, RFC calls
- [ ] Test suite: `sap-bridge/tests/integration/sap-crud.test.ts`
- [ ] Test suite: `sap-bridge/tests/integration/inventory-sync.test.ts`
- [ ] Test suite: `sap-bridge/tests/integration/idoc-listener.test.ts`

---

### 2.4 — Rescue Dashboard Enhancement (Week 4-6)

**Location**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/nginx/rescue-dashboard-offline.html`

#### 2.4.1 — Offline-First Architecture
- [ ] Add service worker: `nginx/sw.js`
  - Cache dashboard shell on first load
  - Serve cached version when Node-RED/backend unavailable
  - Background-sync queued actions when back online
- [ ] Add IndexedDB for client-side state:
  - Store last-known robot positions
  - Store pending manual orders
  - Sync on reconnect

#### 2.4.2 — Real-Time Robot Positions
- [ ] Subscribe to `vda5050/{manufacturer}/{serialNumber}/state` via MQTT WebSocket
- [ ] Display on 2D canvas (top-down warehouse map)
  - File: `nginx/assets/warehouse-map.js`
  - Grid overlay with zone labels
  - Robot icons colored by status (green=idle, blue=working, red=error, gray=offline)
- [ ] Last-known position persisted to IndexedDB
- [ ] Show position timestamp + staleness indicator

#### 2.4.3 — Manual Order Creation/Override
- [ ] Dashboard order form:
  - Robot selection (dropdown, filtered by available)
  - Task type: PICK | PUT | MOVE | CHARGE | EMERGENCY_STOP
  - Priority selector (0-critical, 3-low)
  - Target location (zone + coordinates)
  - Source location (for transport tasks)
- [ ] Submit → POST to `/api/v1/orders/create`
- [ ] Queue feedback: show position in queue, estimated dispatch time

#### 2.4.4 — Emergency Stop
- [ ] Big red E-STOP button (prominent, confirmation dialog)
- [ ] Send `vda5050/{manufacturer}/{serialNumber}/emergencyStop` to all brands
- [ ] Visual confirmation: all robots show "ESTOPPED" state
- [ ] Reset button: send `vda5050/{manufacturer}/{serialNumber}/state` to resume
- [ ] Audit log in SQLite: who triggered E-Stop, timestamp, resolution

#### 2.4.5 — Battery Overview
- [ ] Battery panel: sortable table of all robots
  - Columns: Robot, Brand, Battery %, Status, Last Updated
  - Color-coded: green (>50%), yellow (20-50%), red (<20%)
- [ ] Low-battery alert: push notification + pulsing icon on dashboard
- [ ] Auto-charge trigger: robot < 20% → auto-assign CHARGE order
  - Configurable: `AUTO_CHARGE_THRESHOLD=20`

#### 2.4.6 — Dashboard Testing
- [ ] Offline-mode test: kill Node-RED, verify dashboard still renders
- [ ] Robot position update test: publish fake MQTT state, verify UI updates
- [ ] E-Stop test: verify all robots receive stop command
- [ ] Cross-browser test: Chrome, Edge, Firefox

---

### 2.5 — Node-RED Flow Optimization (Week 5-6)

#### 2.5.1 — Flow Audit
- [ ] Export all current flows to `nodered/flows/` for git tracking
  - Command: `curl http://localhost:1880/flows > nodered/flows/backup-$(date +%Y%m%d).json`
- [ ] Audit each flow for:
  - Missing error handlers (red triangle on every node?)
  - Hardcoded configs (move to environment variables)
  - Large context data (>1MB → Redis)
  - Redundant nodes (merge where possible)
- [ ] Create audit report: `nodered/flows/audit-2026-06.md`

#### 2.5.2 — State Externalization to Redis
- [ ] Identify all `flow.set()` / `global.set()` calls with >100KB data
- [ ] Refactor pattern:
  ```javascript
  // BEFORE (Node-RED context - memory)
  flow.set('robotStates', largeObject);
  
  // AFTER (Redis external store)
  const Redis = global.get('redis');
  await Redis.set('nodered:robotStates', JSON.stringify(data), 'EX', 3600);
  ```
- [ ] Create Node-RED subflow: `subflows/redis-store.json`
  - Generic Redis read/write node with error handling
- [ ] Verify Node-RED memory stays under 512MB after 24h

#### 2.5.3 — Flow Versioning with Git
- [ ] Set up flow export hook:
  - Script: `scripts/export-flows.sh`
  - Auto-export flows on Node-RED start/restart
  - Name format: `nodered/flows/v3.4/flow-name.json`
- [ ] Add `.gitignore` exception for `nodered/flows/`
- [ ] Document diff workflow:
  ```bash
  # Compare flow versions
  diff <(jq . nodered/flows/v3.4/robot-dispatch.json) <(jq . nodered/flows/v3.5/robot-dispatch.json)
  ```

#### 2.5.4 — Subflow Library
- [ ] Create reusable subflows in `nodered/subflows/`:
  | Subflow | Purpose | Reused By |
  |---------|---------|-----------|
  | `redis-read` | Read from Redis with retry | All flows |
  | `redis-write` | Write to Redis with TTL | All flows |
  | `mqtt-publish-vda5050` | Publish VDA5050 message with seq# | Dispatch flows |
  | `sap-outbox-write` | Write to outbox table | SAP integration flows |
  | `robot-state-validator` | Validate state against VDA5050 schema | State handling flows |
  | `alert-notify` | Send alert via Feishu/WeCom | Watchdog, all flows |
- [ ] Import all subflows into Node-RED via settings.js

#### 2.5.5 — Flow-Level Health Metrics
- [ ] Add Prometheus metrics node to Node-RED:
  - `nodered_flow_execution_time` — histogram per flow
  - `nodered_flow_errors_total` — counter per flow
  - `nodered_mqtt_messages_total` — counter per topic
  - `nodered_sap_calls_total` — counter with status label
- [ ] Export metrics at `http://localhost:1880/metrics`
- [ ] Add to `docker-compose.yml` for Prometheus scraper (v3.2)

#### 2.5.6 — Flow Optimization Verification
- [ ] Before/after memory comparison (48h test)
- [ ] Before/after message throughput (msg/s under load)
- [ ] Error rate comparison (should decrease after audit fixes)
- [ ] Document results in `nodered/flows/optimization-report.md`

---

### Phase 2 — Integration Test (End of Week 6)

Full end-to-end verification before claiming Phase 2 complete:

```bash
# 1. Start all services
docker compose up -d --build

# 2. Start 3 robot simulators (1 per brand)
ts-node sap-bridge/simulators/run.ts --brand KUKA --count 1 &
ts-node sap-bridge/simulators/run.ts --brand MIR --count 1 &
ts-node sap-bridge/simulators/run.ts --brand OTTO --count 1 &

# 3. Create SAP warehouse task (via mock)
curl -X POST http://localhost:1880/sap-bridge/orders \
  -H "Content-Type: application/json" \
  -d '{"type":"PICK","source":"SAP-TASK-001","priority":1}'

# 4. Verify order flows through lifecycle
curl http://localhost:1880/api/v1/orders | jq .

# 5. Verify robot receives VDA5050 order via MQTT
mosquitto_sub -t "vda5050/+/+/orders" -v -C 1

# 6. Verify state updates flow back to dashboard
curl http://localhost:8080/  # Nginx rescue dashboard

# 7. Run compliance tests
npm test -- --grep "strategies"

# 8. Run integration tests
npm test -- --grep "integration"

# 9. Verify memory within limits
docker stats --no-stream

# 10. Document results
echo "Phase 2 complete: $(date)" >> docs/phase2-completion-report.md
```

---

## Phase 3: Production Readiness (Weeks 7-8)

### 3.1 — Testing
| Type | Target | Tool |
|------|--------|------|
| Unit | 80%+ coverage on TypeScript services | Jest/Vitest |
| Integration | SAP bridge with mock SAP | pytest + responses |
| E2E | Full order lifecycle (robot → SAP → robot) | Docker Compose test |
| Load | 100 concurrent robot sessions | k6 / custom script |
| Chaos | MQTT kill, Redis fail, SAP timeout | Chaos Monkey |

### 3.2 — Monitoring & Observability
- [ ] Prometheus metrics endpoint on each service
- [ ] Grafana dashboard: robot health, order throughput, SAP latency
- [ ] Structured JSON logging (OpenTelemetry format)
- [ ] Centralized log aggregation (Fluent Bit already configured)
- [ ] Alert rules: robot offline >30s, SAP error rate >5%, Redis >80%

### 3.3 — CI/CD Pipeline
- [ ] GitHub Actions: lint → test → build → deploy
- [ ] Pre-commit hooks: lint, test, verify-before-done
- [ ] Docker image builds per service (sap-bridge, watchdog)
- [ ] Git flow: feature branches → PR → code review → staging → prod
- [ ] Automated ADR validation on PR

### 3.4 — Security Hardening
- [ ] Secrets rotation schedule (monthly SAP password)
- [ ] Container vulnerability scanning (Trivy)
- [ ] Network policy review (least privilege per service)
- [ ] Audit log: all SAP writes recorded with trace ID
- [ ] MQTT TLS encryption for production

### 3.5 — Disaster Recovery
- [ ] Named volume backup script (automated, daily)
- [ ] Recovery runbook with step-by-step restore
- [ ] Staging environment parity with production
- [ ] DR drill: full recovery within 1 hour

---

## Phase 4: Continuous (Ongoing)

### 4.1 — Development Process
- [ ] ADR-first for architecture changes
- [ ] Memory update at session end
- [ ] Verify-before-done enforcement
- [ ] Weekly MEMORY.md review (patterns, pitfalls, pruning)

### 4.2 — Skills & AI Configuration
- [ ] Monitor skill drift between .cursor/ and .qoder/
- [ ] Add new skills as patterns emerge
- [ ] Prune obsolete skills monthly
- [ ] Update AGENTS.md with new learnings

### 4.3 — Performance Optimization
- [ ] Monthly Redis memory audit
- [ ] Quarterly VDA5050 compliance re-check
- [ ] Regular dependency updates (Docker images, npm packages)
- [ ] Load test every major release

---

## 4. Project Structure Map

```
D:/EWM ROBOT/ROBOTIC PLATFORM CODES/
├── 00_inbox/                     # Inbox for new ideas/issues
├── 01_architecture/              # System design documents
│   ├── components/               # Component architecture specs
│   ├── decisions/                # Decision logs (pre-ADR)
│   └── diagrams/                 # Architecture diagrams (draw.io etc.)
├── 02_deployment/                # Infrastructure & deployment
│   ├── checklists/               # Pre-deployment checklists
│   ├── environments/             # Per-environment configs
│   └── troubleshooting/          # Known deployment issues
├── 03_operations/                # Runbooks & operations
├── 04_development/               # Development standards
│   ├── api/                      # API specifications
│   ├── standards/                # Code standards & conventions
│   └── workflows/                # Development workflows
├── 05_reference/                 # Reference documentation
├── 06_meetings/                  # Meeting notes
├── 07_troubleshooting/           # Troubleshooting guides
├── 10_adr/                       # Architecture Decision Records
├── assets/                       # Static assets (images, icons)
├── docs/                         # Documentation
├── sap-bridge/                   # SAP EWM integration (Python FastAPI)
│   ├── services/                 # OData service definitions
│   ├── outbox/                   # Outbox pattern handlers
│   └── strategies/               # Robot brand strategies
├── watchdog/                     # Health monitoring
│   ├── watchdog.py
│   ├── config.yaml
│   └── Dockerfile
├── nodered/                      # Node-RED configuration
│   └── settings.js
├── mqtt/                         # Mosquitto configuration
│   └── mosquitto.conf
├── redis/                        # Redis configuration
│   └── redis.conf
├── nginx/                        # Nginx rescue dashboard
├── sql/                          # Database schemas & migrations
│   ├── init.sql
│   └── migrations/
├── scripts/                      # Utility scripts
├── secrets/                      # Docker Secrets (gitignored in prod)
├── prompts/                      # AI prompt templates
├── templates/                    # Templates for common files
├── .cursor/                      # Cursor IDE config (synced)
├── .qoder/                       # Qoder IDE config (synced)
├── docker-compose.yml
├── package.json
├── PROJECT_CONTEXT.md
├── MEMORY.md
├── AGENTS.md
└── README.md
```

---

## 5. Service Ports & Dependencies

```
Service          Port     Protocol    Depends On
────────────────────────────────────────────────────
Node-RED         1880     HTTP        Redis, SQLite-Init
Redis            6379     TCP         —
SAP Bridge       8000     HTTP        Redis
MQTT Broker      1883     TCP         —
MQTT WS          9001     WS          —
Dify API         5001     HTTP        Redis, PostgreSQL(ext)
Nginx Rescue     8080     HTTP        —
Watchdog         9090     HTTP        Redis, Docker-Proxy, Node-RED
Docker Proxy     2375     TCP         — (bind /var/run/docker.sock)
```

---

## 6. Key Design Decisions (from ADRs)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-001 | MQTT over HTTP polling | Lower latency, VDA5050 native, real-time streaming |
| ADR-002 | Node-RED over custom state machine | Operations team can modify flows visually |
| ADR-003 | Outbox pattern for SAP sync | Guarantees eventual consistency despite SAP rate limits |
| ADR-004 | Redis over PostgreSQL for sessions | Lower latency, pub/sub, TTL expiration |
| ADR-005 | Watchdog for auto-recovery | Self-healing without manual intervention |
| Pending | Dual IDE sync | Both Cursor and Qoder must be identical |

---

## 7. Critical Patterns (from MEMORY.md)

- **Strategy Pattern** for robot brand logic — never if-else chains
- **Outbox Pattern** for SAP writes — atomic DB write → async process
- **Redis TTL** on all keys — prevent memory leak (8GB limit)
- **MQTT QoS 1** + sequence numbers — prevent message reordering
- **Token Bucket** for SAP — 80 req/min safe limit
- **Externalize State >1MB** from Node-RED to Redis

---

## 8. Anti-Patterns (DO NOT DO)

❌ Modify VDA5050 message schemas without ADR  
❌ Bypass outbox pattern for SAP calls  
❌ Claim done without verification evidence  
❌ Update one IDE config without syncing the other  
❌ Hardcode robot-specific logic (use strategy pattern)  
❌ Ignore Redis memory growth alerts  
❌ Deploy without updating runbooks  
❌ Deploy on Friday (except emergencies)

---

## 9. Getting Started Checklist

```powershell
# 1. Set project root
Set-Location "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/"

# 2. Verify environment
Test-Path .env
Test-Path secrets/sap_password.txt

# 3. Build & start
docker compose up -d --build

# 4. Verify services
docker compose ps
curl http://localhost:1880/api/system-health
curl http://localhost:9090/health
mosquitto_sub -t "vda5050/+/+/connection" -v

# 5. Check memory files current
Get-Item MEMORY.md, PROJECT_CONTEXT.md, AGENTS.md | Select-Object Name, LastWriteTime
```

---

## 10. Version Roadmap

```
v3.4  (2026-06) ─ Current — Infrastructure complete, basic dispatch
v3.5  (2026-07) ─ Phase 1 complete: stability, testing, monitoring
v3.6  (2026-08) ─ Phase 2 complete: multi-brand, order management
v3.7  (2026-09) ─ Phase 3 complete: production-ready, CI/CD, DR
v4.0  (2026-Q4) ─ Full production — 10+ brands, 100+ robots, HA
```

---

*Generated: 2026-06-21 | Source: D:/EWM ROBOT/ROBOTIC PLATFORM CODES/*
*Maintainers: Platform Team | Review: Monthly*
