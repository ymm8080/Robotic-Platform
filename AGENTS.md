# AI Agent Configuration

## Workspace Rules

These rules apply to ALL AI agents working in this workspace (Cursor, Qoder, or any other IDE).

## Core Behaviors

### 1. Verification Before Completion

**CRITICAL**: NEVER claim "done" without evidence

Before claiming task completion, you MUST:
1. Run actual verification commands
2. Show the output to the user
3. Confirm the result matches requirements
4. Only THEN claim completion

**Wrong**: "I've installed all the skills. Done!"  
**Correct**: "Installation complete. Verification: [shows command output] DONE"

See: `.cursor/rules/verify-before-done.md` and `.qoder/rules/verify-before-done.md`

### 2. Memory Management

**At Session Start**:
- Read `PROJECT_CONTEXT.md` for project context
- Read `MEMORY.md` for cross-session learnings
- Check last update timestamps
- Reference relevant patterns before implementing

**At Session End**:
- Update `MEMORY.md` with new patterns, pitfalls, decisions, workflows
- Update `PROJECT_CONTEXT.md` if architecture changed
- Date-stamp all new entries
- Verify files updated successfully

**During Session**:
- Reference existing patterns before creating new solutions
- Check pitfalls before debugging known issues
- Follow documented workflows for repeated tasks
- Update memory when user says "remember this"

### 3. Dual IDE Synchronization

This workspace uses BOTH Cursor and Qoder. Always:
- Create files in `.cursor/<type>/` AND `.qoder/<type>/` simultaneously
- Verify both files exist after creation
- Verify content matches (file hashes should be identical)
- Update `CLAUDE.md` skills count when adding new skills

**Verification Command**:
```powershell
Test-Path .cursor/skills/new-file.md
Test-Path .qoder/skills/new-file.md
Get-FileHash .cursor/skills/new-file.md
Get-FileHash .qoder/skills/new-file.md
```

### 4. Communication Style

Use compressed/caveman mode by default:
- ✅ Facts over stories
- ✅ Code over description
- ✅ Bullet points over paragraphs
- ✅ Evidence over assertions
- ❌ No greetings, sign-offs, or filler words

See: `.cursor/skills/caveman.md` and `.qoder/skills/caveman.md`

### 5. Architecture Decisions

**Before Making Changes**:
1. Check if ADR exists for this area (`10_adr/`)
2. If no ADR, create one documenting the decision
3. Update `CLAUDE.md` with summary if architecture changed
4. Update `MEMORY.md` if pattern/pitfall discovered

**Never**:
- Modify VDA5050 message schemas without ADR
- Bypass outbox pattern for SAP calls
- Hardcode robot-specific logic (use strategy pattern)
- Deploy without updating runbooks

## Project Context

### System Overview
SAP EWM integration with VDA5050 robot dispatch platform
- Microservices on Docker Compose
- MQTT for robot communication
- Redis for session state
- PostgreSQL for persistence
- Node-RED for orchestration
- SAP Bridge for EWM integration

### Active Development
- Multi-brand robot support (KUKA, MiR, OTTO)
- SAP EWM warehouse task synchronization
- Rescue dashboard offline capabilities
- Watchdog predictive failure detection

### Key Files
- `PROJECT_CONTEXT.md` - Project context and architecture
- `MEMORY.md` - Cross-session learnings (patterns, pitfalls, decisions)
- `docker-compose.yml` - Service definitions
- `01_architecture/` - System design documents
- `10_adr/` - Architecture Decision Records

### Service Ports
- MQTT: 1883
- Node-RED: 1880
- Redis: 6379
- PostgreSQL: 5432
- Nginx (Rescue): 8080

## Development Standards

### Code
- TypeScript for all new services
- Conventional Commits for git messages
- Test coverage minimum: 80%
- Zero linting errors on commit
- Strategy pattern for multi-brand logic

### Documentation
- Update inline with code changes
- ADR required for architecture changes
- Runbooks updated before deployment
- Memory files updated every session

### Testing
- Unit tests for all new functions
- Integration tests for SAP calls
- E2E tests for critical workflows
- VDA5050 compliance tests per robot brand

## Memory Hierarchy

**Tier 1: Always Load** (PROJECT_CONTEXT.md - ~8K tokens)
- Current architecture
- Active decisions
- Critical protocols
- Verification rules

**Tier 2: Load When Relevant** (MEMORY.md sections - ~12K tokens)
- Patterns (when implementing similar features)
- Pitfalls (when working in affected areas)
- Workflows (when trigger conditions match)

**Tier 3: Search On Demand** (Full MEMORY.md)
- Session history
- Older decisions
- Environment context

**Total Memory Budget**: 32K tokens (25% of 128K context)

## Skills (23 total)

Both IDEs have synchronized skills:
1. verify-before-done - Enforce evidence-based completion
2. memory-manager - Manage AI memory systems
3. careful - Destructive command safety
4. grill-me - Plan stress-testing
5. grill-with-docs - Documentation-sync grilling
6. llm-models - Model selection guide
7. llm-wiki - Knowledge base creation
8. llm-skill - Skill reference
9. caveman - Compressed communication
10. improve-codebase-architecture - Architecture refactoring
11. to-issues - PRD to GitHub issues
12. Plus 12 more (see skills directories)

## Anti-Patterns

❌ Don't claim done without verification  
❌ Don't update one IDE without syncing the other  
❌ Don't write memory entries without code examples  
❌ Don't keep workarounds for fixed bugs  
❌ Don't exceed memory token budget without pruning  
❌ Don't modify VDA5050 schemas without ADR  
❌ Don't bypass outbox pattern for SAP calls  
❌ Don't hardcode robot-specific logic  
❌ Don't ignore Redis memory growth alerts  
❌ Don't deploy without updating runbooks  

## Token Efficiency

Memory management and verification cost ~250 tokens per session but save 800-1500 tokens per rediscovered solution or false "done" claim. This is a 3.2-6x efficiency gain.

**Optimization Rules**:
- Use code examples over prose
- Use bullet points over paragraphs
- Include verification commands
- Date-stamp all entries
- Prune obsolete entries monthly

## Session Workflow

### Start Session
1. Read `CLAUDE.md` (project context)
2. Read `MEMORY.md` (cross-session learnings)
3. Check for relevant patterns/pitfalls
4. Reference documented workflows if applicable

### During Session
1. Follow verification-before-done rules
2. Reference existing patterns before creating new solutions
3. Use compressed communication
4. Create ADRs for architecture decisions
5. Sync both IDEs for all config changes

### End Session
1. Update `MEMORY.md` with new learnings
2. Update `CLAUDE.md` if architecture changed
3. Verify both files updated successfully
4. Date-stamp all new entries

## Emergency Procedures

### Redis Memory Critical
```bash
# Check memory usage
docker exec redis redis-cli INFO memory

# Flush if critical (>90% of 8GB)
docker exec redis redis-cli FLUSHALL

# Restart Node-RED to rebuild sessions
docker-compose restart nodered
```

### SAP Connection Failed
```bash
# Test SAP connectivity
curl -u user:pass https://sap.example.com/sap/opu/odata/sap/ZEWM_SRV

# Check SAP bridge logs
docker logs sap-bridge --tail 100

# Verify outbox queue
docker exec postgres psql -U postgres -c "SELECT count(*) FROM outbox WHERE status='pending';"
```

### MQTT Broker Down
```bash
# Check broker status
docker ps | grep mqtt

# Restart broker
docker-compose restart mqtt

# Verify robot connections
mosquitto_sub -t "vda5050/+/+/connection" -v
```

## Contact

- **SAP Basis Team**: For OData/RFC issues
- **Robot Vendors**: For VDA5050 protocol deviations
- **Platform Team Lead**: For architecture decisions

## Version

**Last Updated**: 2026-06-17  
**Format**: AGENTS.md v1.0  
**Applies To**: All AI agents (Cursor, Qoder, other IDEs)
