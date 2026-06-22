# VDA5050_State_Machine

## Trigger
Activate this skill when writing AGV/robot scheduling logic, fleet management code, or VDA5050 protocol implementations.

## Core Requirements

### 1. VDA5050 State Machine Enforcement
**STRICT STATE TRANSITIONS ONLY** - The following state machine must be enforced:

```
Idle → Executing → Idle (normal completion)
Idle → Executing → Fault → Idle (after error recovery)
Idle → Charging → Idle (when battery sufficient)
Executing → Fault (on error detection)
Executing → Charging (on low battery, critical priority)
Charging → Idle (when charging complete)
Fault → Idle (after manual/automatic recovery)
```

**DENY ILLEGAL TRANSITIONS:**
```python
# ILLEGAL STATE JUMPS - MUST RAISE EXCEPTION
ILLEGAL_TRANSITIONS = {
    ("Idle", "Fault"),        # Must go through Executing or explicit error
    ("Fault", "Executing"),   # Must recover to Idle first
    ("Charging", "Executing"), # Must be Idle before executing
    ("Executing", "Idle", "skip_error_check"),  # Must validate no errors
}

class AGVStateMachine:
    ALLOWED_STATES = {"Idle", "Executing", "Fault", "Charging"}
    
    VALID_TRANSITIONS = {
        "Idle": {"Executing", "Charging"},
        "Executing": {"Idle", "Fault", "Charging"},
        "Fault": {"Idle"},
        "Charging": {"Idle"},
    }
    
    def __init__(self, initial_state: str = "Idle"):
        if initial_state not in self.ALLOWED_STATES:
            raise ValueError(f"Invalid initial state: {initial_state}")
        self.state = initial_state
        self.transition_history = []
    
    def transition_to(self, new_state: str, reason: str = "") -> bool:
        """Validate and execute state transition."""
        if new_state not in self.ALLOWED_STATES:
            raise ValueError(f"Invalid state: {new_state}")
        
        if new_state not in self.VALID_TRANSITIONS.get(self.state, set()):
            raise IllegalStateTransitionError(
                f"Illegal transition: {self.state} → {new_state}. "
                f"Allowed: {self.VALID_TRANSITIONS.get(self.state, set())}"
            )
        
        self.transition_history.append({
            "from": self.state,
            "to": new_state,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.state = new_state
        return True

class IllegalStateTransitionError(Exception):
    """Raised when AGV attempts illegal state transition."""
    pass
```

### 2. VDA5050 Order JSON Structure
```python
# VDA5050 Order Message (MQTT topic: <manufacturer>/<series>/<serialNumber>/order)
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class ActionState(str, Enum):
    WAITING = "waiting"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"

class OrderNode(BaseModel):
    nodeId: str
    sequenceId: int
    released: bool = True
    nodePosition: Optional[dict] = None  # {x, y, theta, mapId}
    actions: List[dict] = Field(default_factory=list)

class VDA5050Order(BaseModel):
    orderId: str
    orderUpdateId: int
    nodes: List[OrderNode]
    edges: List[dict] = Field(default_factory=list)
    horizon: Optional[str] = None

# VDA5050 State Message (MQTT topic: <manufacturer>/<series>/<serialNumber>/state)
class VDA5050State(BaseModel):
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str
    serialNumber: str
    orderId: Optional[str] = None
    orderUpdateId: Optional[int] = None
    lastNodeId: Optional[str] = None
    driving: bool = False
    lifting: bool = False
    agvPosition: dict = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "theta": 0.0})
    batteryState: dict = Field(default_factory=lambda: {
        "batteryCharge": 100.0,
        "batteryVoltage": 48.0,
        "charging": False
    })
    errors: List[dict] = Field(default_factory=list)
    actionStates: List[dict] = Field(default_factory=list)
```

### 3. Heartbeat Detection
```python
import asyncio
from datetime import datetime, timedelta

class HeartbeatMonitor:
    """Monitor AGV heartbeat and trigger fault on timeout."""
    
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout = timedelta(seconds=timeout_seconds)
        self.last_heartbeat: dict[str, datetime] = {}
        self.callbacks: list = []
    
    def record_heartbeat(self, agv_id: str):
        """Record heartbeat from AGV."""
        self.last_heartbeat[agv_id] = datetime.utcnow()
    
    async def start_monitoring(self):
        """Start heartbeat monitoring loop."""
        while True:
            now = datetime.utcnow()
            for agv_id, last_hb in self.last_heartbeat.items():
                if now - last_hb > self.timeout:
                    await self._trigger_fault(agv_id, "Heartbeat timeout")
            await asyncio.sleep(1)
    
    async def _trigger_fault(self, agv_id: str, reason: str):
        """Transition AGV to Fault state on heartbeat loss."""
        for callback in self.callbacks:
            await callback(agv_id, reason)
    
    def on_heartbeat_timeout(self, callback):
        """Register callback for heartbeat timeout."""
        self.callbacks.append(callback)

# Usage:
# monitor = HeartbeatMonitor(timeout_seconds=10)
# monitor.on_heartbeat_timeout(lambda agv_id, reason: sm.transition_to("Fault", reason))
```

### 4. Low-Battery Auto-Return Logic
```python
class BatteryManager:
    """Manage AGV battery state and auto-return to charging station."""
    
    LOW_BATTERY_THRESHOLD = 20.0  # Percentage
    CRITICAL_BATTERY_THRESHOLD = 10.0  # Percentage
    
    def __init__(self, agv_id: str, state_machine: AGVStateMachine):
        self.agv_id = agv_id
        self.sm = state_machine
        self.charging_station_node_id = "CHARGE_001"
    
    async def check_battery_and_decide(self, battery_charge: float, current_node: str) -> dict:
        """Check battery level and decide if AGV should return to charge."""
        decision = {"action": "continue", "reason": ""}
        
        if battery_charge <= self.CRITICAL_BATTERY_THRESHOLD:
            # Critical: Interrupt current task immediately
            if self.sm.state == "Executing":
                decision = {
                    "action": "interrupt_and_charge",
                    "reason": f"Critical battery ({battery_charge}%)",
                    "target_node": self.charging_station_node_id
                }
        
        elif battery_charge <= self.LOW_BATTERY_THRESHOLD:
            # Low: Return to charge after current task
            if self.sm.state == "Executing":
                decision = {
                    "action": "complete_then_charge",
                    "reason": f"Low battery ({battery_charge}%)",
                    "target_node": self.charging_station_node_id
                }
        
        return decision
    
    async def initiate_auto_charge(self, charging_station_id: str) -> VDA5050Order:
        """Generate VDA5050 order to return to charging station."""
        return VDA5050Order(
            orderId=f"AUTO_CHARGE_{self.agv_id}_{datetime.utcnow().timestamp()}",
            orderUpdateId=1,
            nodes=[
                OrderNode(
                    nodeId=charging_station_id,
                    sequenceId=1,
                    actions=[{"actionType": "startCharging"}]
                )
            ]
        )
```

### 5. State Validation Middleware
```python
from functools import wraps

def validate_state_transition(required_states: set):
    """Decorator to validate AGV state before executing operation."""
    def decorator(func):
        @wraps(func)
        async def wrapper(agv_instance, *args, **kwargs):
            if agv_instance.sm.state not in required_states:
                raise InvalidStateError(
                    f"Operation {func.__name__} requires state in {required_states}, "
                    f"but AGV is in state: {agv_instance.sm.state}"
                )
            return await func(agv_instance, *args, **kwargs)
        return wrapper
    return decorator

# Usage:
# class AGV:
#     @validate_state_transition({"Idle", "Executing"})
#     async def move_to(self, node_id: str):
#         # Only allowed when Idle or Executing
#         pass
```

## Anti-Patterns (DENIED)
❌ Allowing direct Fault → Executing transitions
❌ Skipping heartbeat monitoring
❌ Ignoring low-battery warnings
❌ Not validating state before operations
❌ Using string comparisons instead of state machine validation
❌ Allowing multiple concurrent orders without queue management
❌ Not logging state transitions with timestamps and reasons

## References
- VDA 5050 Specification: https:// Verband der Automobilindustrie.de/vda-5050
- VDA 5050 GitHub: https://github.com/VDA5050/VDA5050
- MQTT Protocol for AGV: https://github.com/VDA5050/VDA5050/blob/master/MQTT.md
