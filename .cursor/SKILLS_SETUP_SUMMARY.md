# Qoder Custom Skills Setup - Complete ✅

## Summary

Three custom agent skills have been successfully configured for Qoder in the `.qoder/skills/` directory. These skills enforce domain-specific standards when generating code for the SAP-EWM Robotic Platform.

## Installed Skills

### 1. **SAP_OData_Handler** 
**Location**: `.qoder/skills/SAP_OData_Handler.md`  
**Size**: 4,623 bytes

**Purpose**: Enforces SAP OData integration standards

**Key Features**:
- ✅ OData V2/V4 protocol compliance
- ✅ X-CSRF-Token fetch-then-use pattern
- ✅ Safe `$filter` and `$expand` query builders
- ✅ **MANDATORY** exponential backoff retry logic (tenacity library)
- ✅ Async/await HTTP calls only (aiohttp)
- ✅ SAP error message parsing and correlation ID logging
- ✅ Circuit breaker pattern for SAP unavailability

**Trigger Keywords**: "SAP", "OData", "CSRF", "odata call", "SAP integration"

---

### 2. **VDA5050_State_Machine**
**Location**: `.qoder/skills/VDA5050_State_Machine.md`  
**Size**: 9,233 bytes

**Purpose**: Enforces strict VDA5050 AGV state machine and protocol standards

**Key Features**:
- ✅ **Strict state machine**: Idle → Executing → Fault → Charging
- ✅ **DENIES illegal transitions** (e.g., Fault → Executing)
- ✅ VDA5050 order/state JSON structures with Pydantic validation
- ✅ Heartbeat detection with configurable timeout (default: 10s)
- ✅ Low-battery auto-return logic:
  - 20% threshold: Complete task, then charge
  - 10% threshold: Interrupt immediately, return to charge
- ✅ State validation middleware decorator
- ✅ Transition history logging with timestamps

**Trigger Keywords**: "AGV", "robot", "VDA5050", "state machine", "fleet", "heartbeat"

---

### 3. **Async_Retry_Tester**
**Location**: `.qoder/skills/Async_Retry_Tester.md`  
**Size**: 14,159 bytes

**Purpose**: Enforces comprehensive async testing standards

**Key Features**:
- ✅ pytest + pytest-asyncio for all async tests
- ✅ Mock SAP endpoints to simulate:
  - Network timeouts
  - HTTP 503 (service unavailable)
  - Rate limiting (HTTP 429)
- ✅ Verify exponential backoff timing (increasing delays)
- ✅ Test AGV heartbeat timeout → Fault transition
- ✅ Test low-battery auto-return behavior
- ✅ Test illegal state transition rejection
- ✅ Integration tests with mock aiohttp servers
- ✅ Coverage thresholds:
  - SAP integration: **90%**
  - VDA5050 state machine: **95%**
  - Retry logic: **100%**

**Trigger Keywords**: "test", "pytest", "mock", "retry test", "timeout test"

---

## How to Use in Qoder

### Method 1: Explicit Reference
When prompting Qoder, explicitly reference the skill:

```
Use the SAP_OData_Handler skill to generate the SAP bridge API endpoints.
```

```
Apply VDA5050_State_Machine when writing the AGV fleet manager state logic.
```

```
Write comprehensive tests using Async_Retry_Tester to verify all retry mechanisms.
```

### Method 2: Automatic Triggering
Qoder will automatically detect and apply these skills based on context keywords in your prompts.

## Verification

Run the verification script to confirm skills are properly configured:

```bash
python verify_qoder_skills.py
```

**Expected Output**:
```
✅ SUCCESS: All Qoder custom skills are properly configured!
```

## File Structure

```
.qoder/
└── skills/
    ├── README.md                    # Skills documentation
    ├── SAP_OData_Handler.md         # SAP integration standards
    ├── VDA5050_State_Machine.md     # AGV state machine standards
    └── Async_Retry_Tester.md        # Testing standards
```

## Integration with Cursor MCPs

While **Cursor uses MCP servers** for live API access (PostgreSQL, Redis, filesystem), **Qoder uses these custom skills** as knowledge bases that enforce coding standards and patterns.

| Tool | Mechanism | Purpose |
|------|-----------|---------|
| **Cursor** | MCP JSON configuration | Live database/API access during code generation |
| **Qoder** | Custom skill markdown files | Domain-specific coding standards enforcement |

Both approaches complement each other:
- **Cursor MCPs**: Provide runtime context and data access
- **Qoder Skills**: Provide architectural patterns and code quality standards

## Next Steps

1. ✅ **Skills Created**: All 3 custom skills are in place
2. 🔄 **Usage**: Start using them in Qoder prompts
3. 📊 **Monitoring**: Verify generated code follows skill standards
4. 🔧 **Iteration**: Update skills as new patterns emerge

## References

- **SAP OData**: https://help.sap.com/docs/SAP_NETWEAVER_750
- **VDA 5050**: https://github.com/VDA5050/VDA5050
- **pytest-asyncio**: https://pytest-asyncio.readthedocs.io/
- **tenacity**: https://tenacity.readthedocs.io/
- **aiohttp**: https://docs.aiohttp.org/

---

**Setup Date**: 2026-06-17  
**Status**: ✅ Complete and Verified
