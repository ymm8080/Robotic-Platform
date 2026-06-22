# Cross-Session Memory

**Last Updated**: 2026-06-17  
**Next Review**: 2026-06-24 (7 days)

## How This Works

This file stores durable knowledge that persists across AI sessions. It's automatically read at session start to restore context.

### Memory Categories
- **Patterns**: Proven solutions to recurring problems
- **Pitfalls**: Mistakes to avoid (with workarounds)
- **Decisions**: Why we chose X over Y
- **Workflows**: Step-by-step procedures that work
- **Context**: Environment-specific knowledge

---

## Patterns

### Pattern 001: VDA5050 State Machine Synchronization
**Discovered**: 2026-06-15  
**Applies To**: Multi-brand robot dispatch  
**Pattern**: Use strategy pattern per robot brand, not if-else chains

```typescript
// WRONG: Brand-specific logic tangled
if (robot.manufacturer === 'KUKA') {
  handleKukaState(robot);
} else if (robot.manufacturer === 'MiR') {
  handleMiRState(robot);
}

// CORRECT: Strategy pattern
interface RobotStrategy {
  handleState(state: VDA5050State): void;
}

class KukaStrategy implements RobotStrategy { ... }
class MirStrategy implements RobotStrategy { ... }

const strategies = {
  'KUKA': new KukaStrategy(),
  'MiR': new MirStrategy()
};

strategies[robot.manufacturer].handleState(state);
```

**Why**: 12+ robot brands planned; if-else unmaintainable  
**Trade-off**: More files upfront, but each brand isolated for testing

### Pattern 002: SAP Outbox Reliability
**Discovered**: 2026-06-14  
**Applies To**: All SAP EWM integrations  
**Pattern**: Write to outbox table first, then async process

```sql
-- Step 1: Atomic transaction
BEGIN;
INSERT INTO warehouse_tasks (...) VALUES (...);
INSERT INTO outbox (event_type, payload, status) 
VALUES ('sap_sync', '{...}', 'pending');
COMMIT;

-- Step 2: Background worker picks up outbox
-- Retries with exponential backoff on SAP errors
```

**Why**: SAP OData rate limits + network failures; outbox guarantees eventual consistency  
**Trade-off**: Slightly higher latency, but zero lost transactions

### Pattern 003: Redis Session Cleanup
**Discovered**: 2026-06-16  
**Applies To**: Long-running robot sessions  
**Pattern**: Set TTL on all session keys, use Redis keyspace notifications for cleanup

```redis
SET session:robot:KUKA-001:data "{...}" EX 3600
SET session:robot:KUKA-001:heartbeat PING EX 60

# Keyspace notification triggers cleanup on expiry
CONFIG SET notify-keyspace-events KEA
```

**Why**: Redis memory grew 4GB/day without TTL; crashed on day 3  
**Trade-off**: Must handle session renewal gracefully

---

## Pitfalls

### Pitfall 001: MQTT Message Ordering
**Date**: 2026-06-15  
**Symptom**: Robot state updates arrive out of order  
**Root Cause**: MQTT QoS 0 + network latency = reordered messages  
**Fix**: Use QoS 1 + sequence numbers in payload

```typescript
// WRONG: Rely on arrival order
mqttClient.on('message', (topic, message) => {
  updateRobotState(message);
});

// CORRECT: Use sequence numbers
mqttClient.on('message', (topic, message) => {
  const state = parseState(message);
  if (state.sequenceNumber > lastSequence[topic]) {
    updateRobotState(state);
    lastSequence[topic] = state.sequenceNumber;
  }
});
```

**Lesson**: Never assume message ordering with QoS 0  
**Prevention**: Always include sequence numbers in VDA5050 payloads

### Pitfall 002: SAP OData Rate Limiting
**Date**: 2026-06-14  
**Symptom**: 429 Too Many Requests under load  
**Root Cause**: SAP limits to 100 requests/minute per user  
**Fix**: Implement token bucket rate limiter + request batching

```typescript
const rateLimiter = new TokenBucket({
  tokensPerInterval: 100,
  interval: 60000, // 1 minute
});

async function callSapOData(endpoint: string) {
  await rateLimiter.removeTokens(1);
  return sapClient.get(endpoint);
}
```

**Lesson**: SAP rate limits are strict; no auto-scaling  
**Prevention**: Always rate-limit SAP calls; batch when possible

### Pitfall 003: Node-RED Context Memory Leak
**Date**: 2026-06-13  
**Symptom**: Node-RED OOM after 48 hours  
**Root Cause**: `flow.set()` without size limits on context storage  
**Fix**: Use file-based context with size limits, or Redis external store

```javascript
// WRONG: Unlimited in-memory context
flow.set('robotStates', hugeObjectArray);

// CORRECT: Externalize to Redis
const redis = require('redis');
const client = redis.createClient();
await client.set('nodred:robotStates', JSON.stringify(states), 'EX', 3600);
```

**Lesson**: Node-RED context is not designed for large datasets  
**Prevention**: Externalize state >1MB to Redis or PostgreSQL

---

## Decisions

### Decision 001: MQTT vs HTTP for Robot Communication
**Date**: 2026-06-10  
**ADR**: ADR-001  
**Decision**: MQTT over HTTP polling  
**Why**: 
- Lower latency (ms vs seconds)
- Better for real-time state streaming
- Native VDA5050 support
- Less network overhead

**Trade-offs**:
- ✅ Pro: Real-time, scalable, standard for IoT
- ❌ Con: Requires MQTT broker, message ordering concerns

**Alternatives Considered**:
- HTTP polling (rejected: too slow, high overhead)
- WebSockets (rejected: VDA5050 spec requires MQTT)

### Decision 002: Node-RED vs Custom State Machine
**Date**: 2026-06-11  
**ADR**: ADR-002  
**Decision**: Node-RED for orchestration  
**Why**:
- Visual flow editing for operations team
- Fast iteration on dispatch logic
- Built-in MQTT/Redis/SAP connectors
- Lower maintenance than custom code

**Trade-offs**:
- ✅ Pro: Ops team can modify flows without devs
- ❌ Con: Version control harder (JSON flows)

**Alternatives Considered**:
- Custom Node.js state machine (rejected: ops team can't modify)
- Temporal/Cadence (rejected: overkill for current scale)

### Decision 003: Dual IDE Synchronization
**Date**: 2026-06-17  
**ADR**: Pending  
**Decision**: Keep `.cursor/` and `.qoder/` perfectly synchronized  
**Why**:
- Team uses both IDEs interchangeably
- Inconsistent rules cause different AI behavior
- Skills must work identically regardless of IDE

**Trade-offs**:
- ✅ Pro: Consistent AI behavior across team
- ❌ Con: Must remember to update both locations

**Implementation**: Always create files in BOTH directories simultaneously

---

## Workflows

### Workflow 001: Adding New Robot Brand
**Date**: 2026-06-15  
**Trigger**: New robot vendor onboarded  
**Steps**:
1. Create brand-specific strategy class in `sap-bridge/strategies/`
2. Implement VDA5050 state handlers per brand quirks
3. Add brand to strategy registry in `index.ts`
4. Create ADR for brand-specific decisions
5. Update `CLAUDE.md` manufacturer list
6. Test with vendor's simulator
7. Update runbook in `03_operations/runbooks/`

**Verification**:
```bash
# Run brand-specific tests
npm test -- --grep "KUKA|MiR|OTTO"

# Verify strategy registration
node -e "const s = require('./strategies'); console.log(Object.keys(s));"
```

**Estimated Time**: 2-3 days per brand

### Workflow 002: SAP Integration Change
**Date**: 2026-06-14  
**Trigger**: New EWM requirement or OData service change  
**Steps**:
1. Update OData service definition in `sap-bridge/services/`
2. Add/modify outbox handler in `sap-bridge/outbox/`
3. Update rate limiter configuration if needed
4. Add integration tests with mock SAP responses
5. Update SAP reference docs in `05_reference/sap/`
6. Test against SAP QA system
7. Deploy to prod during maintenance window

**Verification**:
```bash
# Test SAP connectivity
curl -u user:pass https://sap-qa.example.com/sap/opu/odata/sap/ZEWM_SRV

# Verify outbox processing
docker logs sap-bridge | grep "outbox"
```

**Estimated Time**: 1-2 weeks (depends on SAP team availability)

### Workflow 003: IDE Configuration Sync
**Date**: 2026-06-17  
**Trigger**: New skill, rule, or agent added  
**Steps**:
1. Create file in `.cursor/<type>/filename.md`
2. Create identical file in `.qoder/<type>/filename.md`
3. Verify both files exist:
   ```powershell
   Test-Path .cursor/skills/new-skill.md
   Test-Path .qoder/skills/new-skill.md
   ```
4. Verify content matches:
   ```powershell
   Get-FileHash .cursor/skills/new-skill.md
   Get-FileHash .qoder/skills/new-skill.md
   ```
5. Update `CLAUDE.md` skills count

**Verification**: Hashes must match exactly  
**Estimated Time**: 5 minutes

---

## Context

### Environment-Specific Knowledge

#### SAP EWM Version
- **Version**: SAP S/4HANA 2022 (embedded EWM)
- **OData Base URL**: `https://sap.example.com/sap/opu/odata/sap/`
- **Authentication**: Basic auth with CSRF token
- **Rate Limit**: 100 requests/minute per user
- **Known Issues**: 
  - Warehouse task creation fails if batch split not enabled
  - Order confirmation requires specific header format

#### Robot Brands (Active)
- **KUKA**: KMR iiwa (omnidirectional)
  - VDA5050 Version: 2.0.0
  - Quirk: Requires custom action for lifting mechanism
- **MiR**: MiR250 (differential drive)
  - VDA5050 Version: 1.1.0
  - Quirk: Navigation states differ from spec
- **OTTO**: OTTO 1500 (omnidirectional)
  - VDA5050 Version: 2.0.0
  - Quirk: Battery reporting in millivolts (not percentage)

#### Infrastructure Limits
- **MQTT Broker**: 1000 concurrent connections max
- **Redis**: 8GB memory limit (watch for growth)
- **PostgreSQL**: 100GB storage, daily backups at 02:00 UTC
- **Node-RED**: 2GB container memory limit

#### Team Preferences
- **Communication**: Compressed/caveman mode by default
- **Verification**: Evidence required before claiming done
- **Documentation**: Update inline with code changes
- **Code Review**: All changes require peer review
- **Deployment**: Friday deploys forbidden (except emergencies)

---

## Session History

### Recent Sessions
- **2026-06-17**: Installed verification-before-done enforcement rules
- **2026-06-17**: Installed 22 LLM skills (synchronized Cursor + Qoder)
- **2026-06-16**: Fixed Redis memory leak with TTL implementation
- **2026-06-15**: Implemented strategy pattern for multi-brand support
- **2026-06-14**: Added SAP OData rate limiter

### Lessons from Recent Work
1. Always verify file creation in BOTH IDE directories
2. SAP rate limiting is stricter than documented (use 80/min, not 100)
3. MQTT message ordering requires QoS 1 + sequence numbers
4. Node-RED flows need external state storage >1MB
5. VDA5050 state machines vary by brand despite spec

---

## Memory Maintenance

### Review Schedule
- **Weekly**: Add new patterns/pitfalls from sessions
- **Monthly**: Review and prune outdated entries
- **Quarterly**: Full audit of all memories for relevance

### Pruning Rules
Delete entries that are:
- ✅ Superseded by newer patterns
- ✅ Workarounds for fixed bugs
- ✅ Decisions reversed by later ADRs
- ✅ Context for decommissioned services

### Update Triggers
Add new entries when:
- 🔥 Discover non-obvious bug with workaround
- ✅ Find solution that works reliably
- 📝 Make architecture decision with trade-offs
- 🔄 Repeat same task 3+ times (create workflow)
- 💥 Encounter gotcha that costs >30 minutes

---

## Token Budget

This file is designed to be:
- **Concise**: ~8KB total (under 16K token context)
- **Actionable**: Every entry has code example or workflow
- **Current**: Dated entries with review schedule
- **Searchable**: Clear category sections for quick lookup

AI should:
1. Read this file at session start
2. Reference relevant patterns before implementing
3. Update with new learnings at session end
4. Prune obsolete entries during monthly review
