# CLAUDE.md

> SAP EWM -> Multi-Brand Robot Dispatch Platform (VDA5050)
> Project version: v3.4 | Last updated: 2026-06-21

## Project Identity

SAP EWM integration with VDA5050 robot dispatch platform.
Microservices on Docker Compose with Node-RED, MQTT, Redis, PostgreSQL.

## Global Response Standards (Anti-Sycophancy + Token Efficiency)

**Anti-sycophancy:**
1. Tag claims: `[KNOWN]` · `[COMPUTED]` · `[INFERRED]` · `[GUESS]` · `[COMMON]` · `[FRAME]`
2.CONFIDENCE: HIGH ≥80% · MED 50–80% · LOW 20–50% · VERY LOW <20% · UNKNOWN. [FRAME] real-world and [GUESS] cap at LOW.
3. Don't know? First line "I don't know." No fabricating.
4. Sycophancy red flags → cut specifics, add `[GUESS]`, or say "I don't know."
5. Post-hoc → mark `[INFERRED, post-hoc]`.
6. No fabricated citations.
7. Rules broken? Append `[RULES I BROKE]: which, where, why.`

**Token efficiency (applies everywhere):**
8. Be concise. No greetings, closings, or praising
9. No verbose disclaimers
10. One answer per question — no restating the question
12. Prefer Grep/Glob over reading entire files to locate relevant code first.

Applies globally to every response — research, analysis, problem-solving, code review, Q&A.

## Rules (20 files in `.claude/rules/`)

All Cursor rules synced. Key ones:

| Rule | Scope | alwaysApply |
|------|-------|-------------|
| `000-global-iron-rules.mdc` | Global iron laws | **true** |
| `karpathy-guidelines.mdc` | LLM coding best practices | **true** |
| `verify-before-done.md` | Evidence-based completion | **always** |
| `010-nodered-core.mdc` | Node-RED flows | context |
| `020-sap-bridge.mdc` | SAP bridge (Python) | context |
| `030-robot-device.mdc` | Robot drivers | context |
| `040-ops-rescue.mdc` | Ops rescue procedures | context |
| `050-state-machine.mdc` | State machine rules | context |
| `060-db-and-outbox.mdc` | DB & outbox pattern | context |
| `070-infra-and-rescue.mdc` | Infrastructure & rescue | context |
| `circuit-breaker.mdc` | Circuit breaker pattern | context |
| `idempotency-patterns.mdc` | Idempotency patterns | context |
| `mqtt-protocol.mdc` | MQTT protocol rules | context |
| `observability.mdc` | Logging/metrics/tracing | context |
| `080-enterprise-policies.mdc` | Notification matrix + compliance | context |
| `090-operational-limits.mdc` | Node-RED throttling + cost sentinel | context |
| `async-retry-tester.mdc` | Async retry test patterns | context |
| `dify-workflow.mdc` | Dify workflow integration | context |
| `ewm-state-machine.mdc` | EWM state machine rules | context |
| `sap-odata-handler.mdc` | SAP OData handler rules | context |
| `vda5050-state-machine.mdc` | VDA5050 state machine rules | context |

## Skills (129 items in `.claude/skills/`)

Full Cursor skills sync. Key custom skills:
- `SAP_OData_Handler.md` - SAP OData integration (CSRF token, retry, circuit breaker)
- `VDA5050_State_Machine.md` - AGV state machine (VDA5050 compliance)
- `Async_Retry_Tester.md` - Async retry testing (pytest-asyncio, mock SAP/AGV)
- `GSD.md` - Get Shit Done rapid dev workflow
- `Superpowers.md` - AI-assisted dev checklist
- `caveman.md` - Compressed communication mode
- `verify-before-done.md` - Evidence-based completion

105 GitHub-sourced skills covering: code review, testing, debugging, CI/CD, Docker, K8s, MQTT, state machines, circuit breakers, security, performance, accessibility, and more.

## Agents (6 in `.claude/agents/`)

- `_orchestrator.md` - Cross-domain coordination, conflict arbitration
- `dify-feishu-architect.md` - Dify workflows + Feishu/WeCom integration
- `node-red-core-builder.md` - Node-RED core (JS ES6+ only)
- `ops-rescuer.md` - 2AM ops rescue (safe-mode commands only)
- `robot-adapter-writer.md` - Hardware adapter (Node-RED Sub-flow, JS only)
- `sap-bridge-coder.md` - SAP bridge (Python 3.11+ only)

## System Architecture

### Core Components
- **MQTT Broker**: Mosquitto (port 1883) - VDA5050 message routing
- **Redis**: Caching, pub/sub, session state (port 6379)
- **Node-RED**: Visual orchestration, SAP bridge logic (port 1880)
- **PostgreSQL**: Persistent storage, outbox pattern (port 5432)
- **SAP Bridge**: OData/RFC integration to SAP EWM
- **Watchdog**: Health monitoring, auto-recovery
- **Rescue Dashboard**: Offline-capable monitoring (Nginx port 8080)

### Service Ports
- MQTT: 1883
- Node-RED: 1880
- Redis: 6379
- PostgreSQL: 5432
- Nginx (Rescue): 8080

## Critical Protocols

### VDA5050 Robot Protocol
- Order management (create, update, cancel)
- State reporting (position, battery, errors)
- Connection state tracking
- Action execution (pick, place, navigate)
- Topic hierarchy: `vda5050/{manufacturer}/{serialNumber}/...`

### SAP Integration
- OData services for EWM warehouse tasks
- RFC calls for synchronous operations
- IDoc for asynchronous batch processing
- Authentication: Basic auth + CSRF tokens

## Development Standards

### Code
- TypeScript for all new services
- Conventional Commits for git messages
- Test coverage minimum: 80%
- Zero linting errors on commit
- Strategy pattern for multi-brand logic

### Language Boundaries
- Node-RED: JavaScript ES6+ only
- SAP Bridge: Python 3.11+ only

### Documentation
- Update inline with code changes
- ADR required for architecture changes (see `10_adr/`)
- Runbooks updated before deployment
- Memory files updated every session

## Memory Hierarchy

**Tier 1: Always Load** (PROJECT_CONTEXT.md)
- Current architecture, active decisions, critical protocols

**Tier 2: Load When Relevant** (MEMORY.md sections)
- Patterns (when implementing similar features)
- Pitfalls (when working in affected areas)
- Workflows (when trigger conditions match)

**Tier 3: Search On Demand** (Full MEMORY.md)
- Session history, older decisions, environment context

## Session Workflow

### Start
1. Read this CLAUDE.md (project context)
2. Read MEMORY.md (cross-session learnings)
3. Check for relevant patterns/pitfalls

### During
1. Follow verification-before-done rules
2. Reference existing patterns before creating new solutions
3. Use compressed communication (caveman mode)
4. Create ADRs for architecture decisions

### End
1. Update MEMORY.md with new learnings
2. Update CLAUDE.md if architecture changed
3. Verify files updated successfully

## Anti-Patterns

- Don't modify VDA5050 message schemas without ADR
- Don't bypass outbox pattern for SAP calls
- Don't claim done without running verification
- Don't hardcode robot-specific logic (use strategy pattern)
- Don't ignore Redis memory growth alerts
- Don't deploy without updating runbooks

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

## Quick Commands
```bash
docker-compose up -d                          # Start all services
mosquitto_sub -t "vda5050/+/+/connection" -v  # Check robot connections
curl http://localhost:1880/sap-bridge/health  # Verify SAP bridge
docker logs watchdog -f                       # Watchdog logs
```
