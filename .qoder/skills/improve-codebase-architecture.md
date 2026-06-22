---
name: improve-codebase-architecture
description: Identify architecture refactoring opportunities. Improve modularity, reduce coupling, enhance maintainability.
---

# Improve Codebase Architecture

Systematically analyze and improve codebase architecture. Focus on modularity, maintainability, and scalability for the SAP EWM → Robot Dispatch Platform.

## Analysis Framework

### 1. Identify Architectural Smells

**Coupling Issues**
- Direct imports between unrelated modules
- Shared mutable state across services
- Circular dependencies
- Tight coupling to SAP OData API responses

**Cohesion Problems**
- Files doing multiple unrelated things
- Classes with too many responsibilities
- Mixed abstraction levels in same module
- VDA5050 handlers also doing business logic

**Structural Issues**
- Deeply nested imports (>3 levels)
- God classes (>500 lines)
- Feature envy (using other module's data more than own)
- Missing abstraction layers

### 2. Apply SOLID Principles

**Single Responsibility**
- Each module does ONE thing well
- Separate: VDA5050 parsing, business logic, SAP integration, MQTT handling
- Example: Split `order_processor.py` into:
  - `order_validator.py`
  - `order_router.py`
  - `order_dispatcher.py`

**Open/Closed**
- Open for extension, closed for modification
- Use strategy pattern for robot brands
- Plugin architecture for new SAP operations
- Example: Add new robot type without changing dispatch logic

**Liskov Substitution**
- All robot brands implement same interface
- Base VDA5050 state machine extensible
- SAP OData handlers swappable
- Example: AGV and AMR use same dispatch interface

**Interface Segregation**
- Small, specific interfaces over fat ones
- Separate: `IRobotController`, `IRobotStatus`, `IRobotNavigation`
- Don't force implementations to support unused methods
- Example: Simple robots don't need navigation interface

**Dependency Inversion**
- Depend on abstractions, not concretions
- Inject SAP client, don't instantiate
- Use interfaces for MQTT broker, database, cache
- Example: Mock SAP client for testing

### 3. Refactoring Patterns

**Extract Module**
When: File >300 lines with multiple responsibilities
```python
# Before: monolithic
class OrderProcessor:
    def validate_order(self): ...
    def dispatch_to_robot(self): ...
    def update_sap(self): ...
    def handle_error(self): ...

# After: extracted modules
from .validator import OrderValidator
from .dispatcher import OrderDispatcher
from .sap_sync import SAPSync

class OrderProcessor:
    def __init__(self):
        self.validator = OrderValidator()
        self.dispatcher = OrderDispatcher()
        self.sap_sync = SAPSync()
```

**Introduce Adapter**
When: Tight coupling to external API (SAP OData)
```python
# Before: direct coupling
response = sap_client.get(f"/Orders('{order_id}')")
orders = response.json()['d']['results']

# After: adapter pattern
class SAPAdapter:
    def get_order(self, order_id: str) -> Order:
        response = self.client.get(f"/Orders('{order_id}')")
        return OrderMapper.from_sap(response.json())
```

**Add Facade**
When: Complex subsystem interactions
```python
# Before: caller knows too much
mqtt.publish(f"robot/{id}/cmd", start_cmd)
db.update_robot_status(id, "STARTING")
cache.set(f"robot:{id}:state", "starting")
sap.update_order_status(order_id, "DISPATCHED")

# After: facade hides complexity
class RobotDispatchFacade:
    def dispatch(self, robot_id, order_id):
        self.mqtt.send_start(robot_id)
        self.db.update_status(robot_id, "STARTING")
        self.cache.set_state(robot_id, "starting")
        self.sap.update_order(order_id, "DISPATCHED")
```

**Implement Strategy**
When: Multiple robot brands with different logic
```python
# Before: if-else hell
if robot.type == "KUKA":
    handle_kuka(robot)
elif robot.type == "MiR":
    handle_mir(robot)
elif robot.type == "OTTO":
    handle_otto(robot)

# After: strategy pattern
class RobotStrategy(ABC):
    def dispatch(self, robot): ...

class KUKAStrategy(RobotStrategy): ...
class MiRStrategy(RobotStrategy): ...

strategies = {"KUKA": KUKAStrategy(), "MiR": MiRStrategy()}
strategies[robot.type].dispatch(robot)
```

### 4. SAP EWM Specific Improvements

**Separate SAP Integration Layers**
```
sap_integration/
├── client/           # Low-level HTTP/OData
├── adapters/         # SAP-specific adapters
├── mappers/          # Data transformation
├── handlers/         # Business logic handlers
└── test_doubles/     # Mocks/stubs for testing
```

**VDA5050 Protocol Isolation**
```
vda5050/
├── protocol/         # Message schemas, validation
├── state_machine/    # State transitions
├── handlers/         # Command/state handlers
└── clients/          # MQTT communication
```

**Robot Fleet Abstraction**
```
fleet/
├── manager/          # Fleet orchestration
├── dispatcher/       # Order assignment
├── health/           # Robot health monitoring
└── strategies/       # Brand-specific logic
```

### 5. Quality Metrics

**Before Refactoring**
- Count lines per file
- Measure cyclomatic complexity
- Identify import depth
- Map dependencies

**After Refactoring**
- Files <300 lines
- Functions <50 lines
- Cyclomatic complexity <10
- Import depth ≤3
- Zero circular dependencies

### 6. Safe Refactoring Process

1. **Write Tests First**
   - Test current behavior
   - Ensure 100% coverage of code being refactored
   - Use TDD skill

2. **Small Incremental Changes**
   - One refactoring at a time
   - Run tests after each change
   - Commit frequently

3. **Preserve Behavior**
   - No feature changes during refactoring
   - External API stays same
   - Only internal structure changes

4. **Review & Validate**
   - Code review each refactoring
   - Performance testing if critical path
   - Integration tests with SAP

5. **Document Changes**
   - Update architecture docs
   - Record ADR for major changes
   - Update runbooks if operational impact

### 7. Red Flags - Don't Refactor

- ❌ Working code close to deadline
- ❌ Code with no tests
- ❌ Third-party generated code
- ❌ Code scheduled for replacement
- ✅ Code that hurts maintainability
- ✅ Code causing frequent bugs
- ✅ Code blocking new features
- ✅ Code team struggles to understand

## When to Use

- Before adding major features
- When bug frequency increases
- When onboarding new developers
- When build times slow down
- When tests become fragile
- Before SAP EWM version upgrades
