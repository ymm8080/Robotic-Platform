# AGENTS.md

> SAP EWM -> Multi-Brand Robot Dispatch Platform (VDA5050)
> Project version: v4.1 | Rules version: v4.1 | Last updated: 2026-07-08

## Project Identity

SAP EWM integration with VDA5050 robot dispatch platform.
Microservices on Docker Compose with Node-RED, MQTT, Redis, PostgreSQL.
Industrial-grade fault tolerance + Physical-level error-proofing + Human-friendly degradation.

## Global Response Standards (Anti-Sycophancy + Token Efficiency)

**Anti-sycophancy:**
1. Tag claims: `[KNOWN]` · `[COMPUTED]` · `[INFERRED]` · `[GUESS]` · `[COMMON]` · `[FRAME]`
2. CONFIDENCE: HIGH ≥80% · MED 50–80% · LOW 20–50% · VERY LOW <20% · UNKNOWN. `[FRAME]` real-world and `[GUESS]` cap at LOW.
3. Don't know? First line "I don't know." No fabricating.
4. Sycophancy red flags → cut specifics, add `[GUESS]`, or say "I don't know."
5. Post-hoc → mark `[INFERRED, post-hoc]`.
6. No fabricated citations.
7. Rules broken? Append `[RULES I BROKE]: which, where, why.`

**Token efficiency (applies everywhere):**
8. Be concise. No greetings, closings, or praising.
9. No verbose disclaimers.
10. One answer per question — no restating the question.
11. Prefer Grep/Glob over reading entire files to locate relevant code first.

Applies globally to every response — research, analysis, problem-solving, code review, Q&A.

## Iron Rules (from 000-global-iron-rules)

1. **LLM absolute prohibition**: LLM must never directly issue physical control commands (E-stop, charge, door open). LLM only suggests; humans/Watchdog execute.
2. **Physical E-stop**: Human E-stop button overrides all software logic. No exceptions.
3. **Data sovereignty**: Production data stays on-premise. No cloud sync without explicit ADR.
4. **Credential management**: Docker secrets only. No env vars for passwords. No hardcoded credentials.
5. **Timezone**: All timestamps UTC in storage; display in `Asia/Shanghai` (UTC+8).
6. **Language boundaries**:
   - Node-RED: JavaScript ES6+ ONLY
   - SAP Bridge: Python 3.11+ ONLY
   - Dashboard: TypeScript ONLY
7. **Version compliance**: All code must comply with `.claude/rules/VERSION` (currently v4.1).
8. **Supplier sovereignty**: Never modify robot vendor SDK. Wrap, don't fork.
9. **Message gateway accuracy**: Six-layer validation for all mobile write operations.
10. **Callback security**: Verify platform callback signatures before processing.
11. **Audit log immutability**: Audit logs are append-only. Never DELETE or UPDATE.
12. **Data persistence**: Outbox pattern mandatory for all SAP-synced writes.
13. **Change-before-backup**: Backup before any schema or config change.
14. **MQTT rollback**: VDA5050 message schema changes require ADR + backward compatibility.

### File Placement Decision Tree (Rule 13)
1. Is it a new service? → `<service-name>/` directory at root
2. Is it a Node-RED flow? → `nodered/flows/` or `nodered/subflows/`
3. Is it a SAP bridge module? → `sap-bridge/<module>/`
4. Is it a script? → `scripts/`
5. Is it documentation? → Numbered knowledge base (`01_architecture/`, `02_deployment/`, etc.)
6. Is it a test? → Co-locate with source in `tests/` subdirectory
7. Is it a skill? → `.agents/skills/<skill-name>/SKILL.md`
8. Is it a rule? → `.claude/rules/`
9. If unsure → ASK before creating

### Post-Creation Checklist (Rule 14)
After creating any file:
- [ ] Correct directory per decision tree above
- [ ] Correct language per boundaries
- [ ] No secrets hardcoded
- [ ] Tests co-located if applicable
- [ ] Documentation updated if architecture changed
- [ ] ADR created if architectural decision

## Rules Index (22 files in `.claude/rules/`)

All rules synced to `.claude/rules/`. Key ones:

| Rule | Scope | alwaysApply |
|------|-------|-------------|
| `000-global-iron-rules.mdc` | Global iron laws | true |
| `karpathy-guidelines.mdc` | LLM coding best practices | true |
| `verify-before-done.md` | Evidence-based completion | always |
| `gsd-workflow.mdc` | GSD 快速交付工作流 | true |
| `compressed-communication.mdc` | 压缩沟通模式 | true |
| `010-nodered-core.mdc` | Node-RED flows | context |
| `020-sap-bridge.mdc` | SAP bridge (Python) | context |
| `030-robot-device.mdc` | Robot drivers | context |
| `040-ops-rescue.mdc` | Ops rescue procedures | context |
| `050-state-machine.mdc` | State machine rules | context |
| `060-db-and-outbox.mdc` | DB & outbox pattern | context |
| `070-infra-and-rescue.mdc` | Infrastructure & rescue | context |
| `080-enterprise-policies.mdc` | Notification matrix + compliance | context |
| `090-operational-limits.mdc` | Node-RED throttling + cost sentinel | context |
| `circuit-breaker.mdc` | Circuit breaker pattern | context |
| `idempotency-patterns.mdc` | Idempotency patterns | context |
| `mqtt-protocol.mdc` | MQTT protocol rules | context |
| `observability.mdc` | Logging/metrics/tracing | context |
| `async-retry-tester.mdc` | Async retry test patterns | context |
| `dify-workflow.mdc` | Dify workflow integration | context |
| `ewm-state-machine.mdc` | EWM state machine rules | context |
| `sap-odata-handler.mdc` | SAP OData handler rules | context |
| `vda5050-state-machine.mdc` | VDA5050 state machine rules | context |

## Memory Hierarchy

**Tier 1: Always Load** (PROJECT_CONTEXT.md) — Current architecture, active decisions, critical protocols

**Tier 2: Load When Relevant** (MEMORY.md sections) — Patterns, pitfalls, workflows (loaded when trigger conditions match)

**Tier 3: Search On Demand** (Full MEMORY.md) — Session history, older decisions, environment context

## System Architecture

### Core Components & Service Ports
| Service | Port | Role |
|---------|------|------|
| MQTT (Mosquitto) | 1883 | VDA5050 message routing |
| Node-RED | 1880 | Visual orchestration, SAP bridge logic |
| Redis | 6379 | Caching, pub/sub, session state (DB0=nodered, DB1=sap-bridge, DB2=gateway) |
| PostgreSQL | 5432 | Sole persistent DB (outbox pattern, audit logs) |
| SAP Bridge | 9000 (host) / 8000 (container) | OData/RFC/IDoc integration to SAP EWM |
| WM RFC Simulator | 8001 | SAP Classic WM mock for dev/test |
| Dify | 5001 | LLM translation/NLP layer |
| Rescue Dashboard (Nginx) | 8080 | Offline-capable emergency monitoring |
| Watchdog | 9090 | Health monitoring, auto-recovery, circuit breaker |
| Dashboard (React) | 4000 (host) / 80 (container) | Operator monitoring SPA |
| Prometheus | 9091 (host) / 9090 (container) | Metrics collection |
| Alertmanager | 9093 | Alert routing (Feishu/WeCom) |
| Grafana | 3000 | Visualization dashboards |
| Kafka | 9092 | Event bus for gateway-core decoupling |
| Elasticsearch | 9200 | Audit log storage for gateway |
| Message Gateway | 8010 | Multi-channel notification with six-layer validation |

### Source Code Structure
- `sap-bridge/` — Python FastAPI, SAP EWM integration (OData/RFC/IDoc), multi-brand robot strategy pattern
- `gateway/` — Python FastAPI, Message Gateway (WeChat/Feishu/DingTalk/Email), six-layer validation
- `nodered/` — Node-RED flows, custom nodes, subflows
- `dashboard/` — React + TypeScript + Vite SPA
- `watchdog/` — Python health monitoring service
- `wcs-sandbox/` — WCS brand mock services for testing
- `scripts/` — Operations & development scripts (PowerShell + Bash)
- `monitoring/` — Prometheus, Alertmanager, Grafana configs
- `sql/` — PostgreSQL init scripts and migrations

### Key Technical Patterns
1. **Strategy Pattern**: Robot brand-specific logic via `sap-bridge/strategies/` (Geek+, HaiRobotics, KUKA, MiR, OTTO, Quicktron)
2. **Outbox Pattern**: SAP sync reliability via `nodered/outbox-nodes-v4.1.js` (ADR-003)
3. **Circuit Breaker**: Watchdog monitors Node-RED health, triggers safe-mode via Redis
4. **Six-Layer Validation**: Message Gateway enforces identity, permission, object, anti-replay, secondary confirmation, pre-execution
5. **Multi-Backend SAP**: Supports EWM (OData) + Classic WM (RFC) via `sap-bridge/backends/`
6. **Docker Secrets**: Credentials via Docker secrets, not env vars

## Critical Protocols

### VDA5050 Robot Protocol
- Order management (create, update, cancel)
- State reporting (position, battery, errors)
- Connection state tracking
- Action execution (pick, place, navigate)
- Topic hierarchy: `vda5050/{manufacturer}/{serialNumber}/...`
- QoS levels: 0 (telemetry), 1 (status), 2 (tasks)

### VDA5050 AGV State Machine
```
Idle -> Executing -> Idle (normal)
Idle -> Executing -> Fault -> Idle (recovery)
Idle -> Charging -> Idle (battery sufficient)
Executing -> Charging (low battery, critical)
```
- Heartbeat timeout: 120s → OFFLINE (not 90s, prevents WiFi roaming false-positive)
- Low battery: <20% limit short orders (≤50m); <10% force return to charge

### SAP Integration
- OData services for EWM warehouse tasks (CSRF token fetch-then-use)
- RFC calls for synchronous operations
- IDoc for asynchronous batch processing
- Authentication: Basic auth + CSRF tokens
- Retry: exponential backoff, 5 attempts, 2-60s range

## Development Standards

### Code
- TypeScript for all new services
- Conventional Commits for git messages
- Test coverage minimum: 80% (SAP 90%, State Machine 95%, Retry 100%, Battery 85%)
- Zero linting errors on commit (ruff for Python, prettier for JS/YAML/JSON/MD)
- Strategy pattern for multi-brand logic
- Pre-commit hooks: ruff, prettier, trailing whitespace, ADR format, pytest (pre-push)

### Language Boundaries (STRICT)
- Node-RED: JavaScript ES6+ only
- SAP Bridge: Python 3.11+ only
- Dashboard: TypeScript only
- Tests: pytest (Python), Vitest (dashboard), Playwright (E2E)

### Circuit Breaker Thresholds
- SAP: 5 failures / 120s recovery
- Jiizhijia: 3 failures / 60s recovery
- Dify: 5 failures / 180s recovery
- Rate limits: SAP 10/s, AGV 50/s, API 100/min

### Documentation
- Update inline with code changes
- ADR required for architecture changes (see `10_adr/`)
- Runbooks updated before deployment
- Project design files in `D:\EWM Robot\Reference`

## Anti-Patterns (PROHIBITED)

- Don't modify VDA5050 message schemas without ADR
- Don't bypass outbox pattern for SAP calls
- Don't claim done without running verification (see `verify-before-done` skill)
- Don't hardcode robot-specific logic (use strategy pattern)
- Don't ignore Redis memory growth alerts
- Don't deploy without updating runbooks
- Don't bypass six-layer validation for mobile write operations
- Don't accept unverified platform callback signatures
- Don't use synchronous HTTP calls to SAP (must be async/await)
- Don't skip retry logic on SAP HTTP calls
- Don't allow direct Fault -> Executing AGV state transitions
- Don't skip heartbeat monitoring

## Skills Index

Custom project-specific skills in `.agents/skills/`:
- `sap-odata-handler` — SAP OData integration (CSRF, retry, circuit breaker)
- `vda5050-state-machine` — VDA5050 AGV state machine (states, heartbeat, battery)
- `async-retry-tester` — Async retry testing (pytest-asyncio, mock SAP/AGV)
- `superpowers` — Pre-implementation checklist
- `verify-before-done` — Evidence-based completion verification
- `diagnose` — Systematic debugging methodology
- `memory-manager` — AI memory management
- `dify-workflow` — Dify workflow DSL builder
- `state-machine` — Robot lifecycle state machine patterns
- `node-red-data-boundary` — Node-RED data boundary & throttling
- `vda-5050-adapter-design` — VDA5050 adapter strategy pattern
- `degradation-drill-sop` — 3/7/14 day degradation drills
- `rescue-dashboard` — Rescue dashboard & safe-mode SOP
- `nodered-git-workflow` — Node-RED Git workflow
- `robot-firmware-ota` — Robot firmware OTA risk management
- `schema-migration-automation` — Database schema migration automation

> Note: `GSD.md` + `caveman.md` have migrated to `.claude/rules/` — auto-applied, no manual trigger needed.

102 GitHub-sourced skills also available covering: code review, testing, debugging, CI/CD, Docker, K8s, MQTT, circuit breakers, security, performance, OpenTelemetry, accessibility, and more.

## Subagent Coordination

When dispatching subagents for this project:
- **node-red-core-builder**: Node-RED core work (JS ES6+ only). Authoritative on HTTP timeout conflicts.
- **sap-bridge-coder**: SAP bridge layer (Python 3.11+ only).
- **robot-adapter-writer**: Hardware adapters (Node-RED Sub-flow, JS only).
- **ops-rescuer**: Emergency ops (safe-mode commands only, no code suggestions).
- **dify-feishu-architect**: Dify + Feishu/WeCom dual-channel integration.
- **_orchestrator**: Cross-domain coordination. When ops-rescuer is active, all other agents are read-only.

## Session Workflow

### Start
1. Read this AGENTS.md (project context)
2. Check `.claude/memory/MEMORY.md` for cross-session learnings (if available)
3. Check for relevant patterns/pitfalls

### During
1. Follow verification-before-done rules — never claim "done" without running verification commands and showing evidence
2. Reference existing patterns before creating new solutions
3. Use compressed communication (concise, no filler)
4. Create ADRs for architecture decisions

### End
1. Update memory with new learnings
2. Update AGENTS.md if architecture changed
3. Verify files updated successfully

## Emergency Procedures

### Redis Memory Critical
```bash
docker exec redis redis-cli INFO memory
docker exec redis redis-cli FLUSHALL  # if >90%
docker-compose restart nodered
```

### SAP Connection Failed
```bash
curl -u user:pass https://sap.example.com/sap/opu/odata/sap/ZEWM_SRV
docker logs sap-bridge --tail 100
docker exec postgres psql -U postgres -c "SELECT count(*) FROM outbox WHERE status='pending';"
```

### MQTT Broker Down
```bash
docker ps | grep mqtt
docker-compose restart mqtt
mosquitto_sub -t "vda5050/+/+/connection" -v
```

### Safe-Mode Triggers
- Redis OOM (used_memory > 95% maxmemory)
- Node-RED unhealthy (3 consecutive failures)
- NTP clock drift > 30s
- Checkpoint stuck > 10000ms

## Quick Commands
```bash
docker-compose up -d                          # Start all services
mosquitto_sub -t "vda5050/+/+/connection" -v  # Check robot connections
curl http://localhost:1880/sap-bridge/health  # Verify SAP bridge
docker logs watchdog -f                       # Watchdog logs
docker exec postgres psql -U postgres -d ewm_db  # PostgreSQL shell
```
