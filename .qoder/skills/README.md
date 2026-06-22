# Qoder Custom Skills

This directory contains custom agent skills for the EWM Robotic Platform project. These skills enforce domain-specific standards and patterns when generating code.

## Available Skills

### 1. SAP_OData_Handler
**Trigger**: Writing SAP integration code, OData API calls, or SAP-bridge communication logic

**Enforces**:
- OData V2/V4 standards compliance
- X-CSRF-Token validation for state-changing operations
- Proper `$filter` and `$expand` query building
- Exponential backoff retry logic on all SAP HTTP calls (MANDATORY)
- Async/await patterns (no synchronous HTTP calls)
- Proper SAP error message parsing and logging

**File**: `SAP_OData_Handler.md`

---

### 2. VDA5050_State_Machine
**Trigger**: Writing AGV/robot scheduling logic, fleet management code, or VDA5050 protocol implementations

**Enforces**:
- Strict VDA5050 state machine (Idle → Executing → Fault → Charging)
- **DENIES** illegal state transitions (e.g., Fault → Executing without recovery)
- VDA5050 order and state JSON structures with Pydantic validation
- Heartbeat detection with configurable timeout
- Low-battery auto-return logic (20% warning, 10% critical interrupt)
- State validation middleware for AGV operations

**File**: `VDA5050_State_Machine.md`

---

### 3. Async_Retry_Tester
**Trigger**: Writing tests for the system, especially SAP integration, AGV communication, or network reliability

**Enforces**:
- pytest and pytest-asyncio for all async tests
- Mock SAP and AGV endpoints to simulate network timeouts
- Verify exponential backoff mechanism triggers correctly
- Test heartbeat timeout scenarios
- Test low-battery auto-return behavior
- Test illegal state transition rejection
- Integration tests with mock servers
- Minimum coverage thresholds: SAP (90%), State Machine (95%), Retry Logic (100%)

**File**: `Async_Retry_Tester.md`

---

## How to Use

### In Qoder Prompts
When working with Qoder, reference these skills explicitly:

```
Use the SAP_OData_Handler skill to generate the SAP bridge API.
```

```
Apply VDA5050_State_Machine when writing the AGV fleet manager.
```

```
Write tests using Async_Retry_Tester to verify retry logic.
```

### Automatic Triggering
Qoder will automatically detect when to apply these skills based on:
- **SAP_OData_Handler**: Keywords like "SAP", "OData", "CSRF", "odata call"
- **VDA5050_State_Machine**: Keywords like "AGV", "robot", "VDA5050", "state machine", "fleet"
- **Async_Retry_Tester**: Keywords like "test", "pytest", "mock", "retry test"

## Skill Standards

All skills enforce:
1. **Type Safety**: Pydantic models, type hints
2. **Async-First**: No blocking I/O operations
3. **Error Handling**: Proper exception handling and logging
4. **Test Coverage**: Minimum 80% overall, higher for critical paths
5. **Documentation**: Docstrings, comments, references to specs

## References

- SAP OData: https://help.sap.com/docs/SAP_NETWEAVER_750
- VDA 5050: https://github.com/VDA5050/VDA5050
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- tenacity: https://tenacity.readthedocs.io/
