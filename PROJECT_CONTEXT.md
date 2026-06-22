# SAP EWM → Multi-Brand Robot Dispatch Platform

## Project Context

**Current Date**: June 2026  
**Platform**: SAP EWM integration with VDA5050 robot dispatch  
**Architecture**: Microservices on Docker Compose with Node-RED, MQTT, Redis, PostgreSQL  
**IDEs**: Cursor, Qoder, and other AI assistants (synchronized configuration)

**Note**: This file is IDE-agnostic. Works with Cursor, Qoder, Claude Code, GitHub Copilot, or any AI assistant.

## System Architecture

### Core Components
- **MQTT Broker**: Mosquitto (port 1883) - VDA5050 message routing
- **Redis**: Caching, pub/sub, session state (port 6379)
- **Node-RED**: Visual orchestration, SAP bridge logic (port 1880)
- **PostgreSQL**: Persistent storage, outbox pattern (port 5432)
- **SAP Bridge**: OData/RFC integration to SAP EWM
- **Watchdog**: Health monitoring, auto-recovery
- **Rescue Dashboard**: Offline-capable monitoring (Nginx)

### Key Directories
```
01_architecture/     - System design, components, ADRs
02_deployment/       - Environment configs, checklists
03_operations/       - Runbooks, maintenance procedures
04_development/      - API specs, standards, workflows
05_reference/        - Protocol docs, SAP integration guides
10_adr/             - Architecture Decision Records
sap-bridge/          - SAP EWM integration code
watchdog/            - Health monitoring service
mqtt/                - Mosquitto configuration
```

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

### Code Conventions
- TypeScript for all new services
- Conventional Commits for git messages
- ADR required for architecture changes
- Test coverage minimum: 80%
- Zero linting errors on commit

### Verification Before Completion
**CRITICAL RULE**: NEVER claim "done" without evidence
- Run verification commands
- Show output to user
- Confirm result matches requirements
- Only THEN claim completion

See `.cursor/rules/verify-before-done.md` and `.qoder/rules/verify-before-done.md`

## Memory Management

### How to Use This File
1. Read this file at session start for project context (all AI assistants)
2. Update when architecture changes
3. Reference ADRs for decision history
4. Check `MEMORY.md` for cross-session learnings

### For AI Assistants
- **Cursor**: Reads this automatically at session start
- **Qoder**: Reads this automatically at session start
- **Claude Code**: Reads this as PROJECT_CONTEXT.md
- **GitHub Copilot**: Context available via workspace
- **Other AI**: Load this file for project context

### Memory Update Triggers
Update this file when:
- New microservice added
- SAP integration pattern changes
- VDA5050 protocol version update
- Database schema migration
- Infrastructure change (ports, services)
- New critical workflow discovered

## Key Decisions (Summary)

See `10_adr/` for full records:
- ADR-001: MQTT for robot communication (not HTTP polling)
- ADR-002: Node-RED for orchestration (not custom state machine)
- ADR-003: Outbox pattern for SAP sync reliability
- ADR-004: Redis for session state (not PostgreSQL)
- ADR-005: Watchdog for auto-recovery (not manual intervention)

## Active Development Areas

### Current Focus
1. Multi-brand robot support (KUKA, MiR, OTTO)
2. SAP EWM warehouse task synchronization
3. Rescue dashboard offline capabilities
4. Watchdog predictive failure detection

### Known Challenges
- VDA5050 state machine complexity across brands
- SAP OData rate limiting under high load
- MQTT message ordering guarantees
- Redis memory growth with long sessions

## Skills & Tools

### Installed Skills (22 total)
Both `.cursor/skills` and `.qoder/skills` are synchronized with:
- `verify-before-done` - Enforce evidence-based completion
- `careful` - Destructive command safety
- `grill-me` - Plan stress-testing
- `grill-with-docs` - Documentation-sync grilling
- `llm-models` - Model selection guide
- `llm-wiki` - Knowledge base creation
- `llm-skill` - Skill reference
- `caveman` - Compressed communication
- `improve-codebase-architecture` - Architecture refactoring
- `to-issues` - PRD to GitHub issues
- Plus 12 more (see skills directories)

### MCP Servers
- `browser-use` - Web automation
- `genui` - UI guidelines
- See `mcp-config.json` for configuration

## Quick Reference

### Service Ports
- MQTT: 1883
- Node-RED: 1880
- Redis: 6379
- PostgreSQL: 5432
- Nginx (Rescue): 8080

### Critical Commands
```bash
# Start all services
docker-compose up -d

# Check robot connections
mosquitto_sub -t "vda5050/+/+/connection" -v

# Verify SAP bridge
curl http://localhost:1880/sap-bridge/health

# Watchdog logs
docker logs watchdog -f
```

### Emergency Contacts
- SAP Basis Team: For OData/RFC issues
- Robot Vendors: For VDA5050 protocol deviations
- Platform Team Lead: For architecture decisions

## Anti-Patterns to Avoid

❌ Don't modify VDA5050 message schemas without ADR  
❌ Don't bypass outbox pattern for SAP calls  
❌ Don't claim done without running verification  
❌ Don't update one IDE's config without syncing the other  
❌ Don't hardcode robot-specific logic (use strategy pattern)  
❌ Don't ignore Redis memory growth alerts  
❌ Don't deploy without updating runbooks  

## Token Efficiency

This project uses compressed communication by default (see `caveman` skill).
- Facts over stories
- Code over description
- Bullets over paragraphs
- Evidence over assertions

Verification costs ~50 tokens but saves 300-500 per false "done" claim.
