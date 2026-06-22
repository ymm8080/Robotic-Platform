---
name: state-machine
description: Implement state machine patterns for robot lifecycle management (CREATED, DISPATCHED, EXECUTING, COMPLETED, FAILED), state transitions, persistence, and recovery. Use when designing robot state workflows, implementing state persistence, handling state transitions, building recovery logic, or managing AGV task lifecycle.
---

# State Machine Design

## Robot Lifecycle States

### Core States
```
CREATED → DISPATCHED → EXECUTING → COMPLETED
                         ↓
                       FAILED → RECOVERING → EXECUTING
```

### State Definitions

| State | Description | Trigger | Persistence |
|-------|-------------|---------|-------------|
| `CREATED` | Task assigned, not yet dispatched | SAP order creation | Redis + PostgreSQL |
| `DISPATCHED` | Sent to robot, awaiting acknowledgment | MQTT publish to `ewm/robots/{id}/task` | Redis (TTL: 30s) |
| `EXECUTING` | Robot actively executing task | MQTT ack from robot | PostgreSQL (audit log) |
| `COMPLETED` | Task finished successfully | MQTT completion callback | PostgreSQL + SAP callback |
| `FAILED` | Task execution failed | MQTT error callback / timeout | PostgreSQL + alert |
| `RECOVERING` | Human intervention or auto-retry | Watchdog detection | PostgreSQL + Node-RED |

## Implementation Pattern

### 1. State Transition Table

```python
TRANSITIONS = {
    'CREATED': ['DISPATCHED', 'FAILED'],
    'DISPATCHED': ['EXECUTING', 'FAILED', 'CREATED'],  # retry on timeout
    'EXECUTING': ['COMPLETED', 'FAILED', 'RECOVERING'],
    'FAILED': ['RECOVERING', 'CREATED'],  # recreate or recover
    'RECOVERING': ['EXECUTING', 'FAILED'],
    'COMPLETED': []  # terminal state
}
```

### 2. State Persistence Strategy

**Redis (Hot State)**:
- Key: `robot:{id}:state`
- TTL: 5 minutes (refreshed on transition)
- Payload: `{state, task_id, timestamp, retries}`

**PostgreSQL (Audit Log)**:
```sql
CREATE TABLE robot_state_history (
    id UUID PRIMARY KEY,
    robot_id VARCHAR(64),
    task_id VARCHAR(64),
    from_state VARCHAR(32),
    to_state VARCHAR(32),
    triggered_by VARCHAR(64),  -- 'mqtt', 'watchdog', 'manual'
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);
```

### 3. Transition Guard Clauses

```python
def validate_transition(current_state: str, next_state: str) -> bool:
    """Validate state transition before execution."""
    allowed = TRANSITIONS.get(current_state, [])
    if next_state not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition {current_state} → {next_state}"
        )
    return True

def execute_transition(robot_id: str, next_state: str, **metadata):
    """Execute state transition with persistence."""
    current = get_current_state(robot_id)
    validate_transition(current, next_state)
    
    # Atomic transition with Redis LOCK
    with redis.lock(f"robot:{robot_id}:lock", timeout=10):
        # Verify no concurrent transition
        if get_current_state(robot_id) != current:
            raise ConcurrentTransitionError("State changed during lock")
        
        # Persist to Redis
        redis.set(f"robot:{robot_id}:state", json.dumps({
            'state': next_state,
            'task_id': metadata.get('task_id'),
            'timestamp': time.time(),
            'retries': metadata.get('retries', 0)
        }), ex=300)
        
        # Audit log to PostgreSQL
        db.execute("""
            INSERT INTO robot_state_history 
            (robot_id, from_state, to_state, triggered_by, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """, (robot_id, current, next_state, metadata.get('source'), metadata))
```

## Recovery Patterns

### Watchdog Detection
```python
# Node-RED flow: detect stale EXECUTING state
def check_stale_tasks():
    """Detect tasks stuck in EXECUTING > 10 minutes."""
    stale = db.query("""
        SELECT robot_id, task_id, timestamp
        FROM robot_state_history
        WHERE to_state = 'EXECUTING'
          AND timestamp < NOW() - INTERVAL '10 minutes'
          AND robot_id NOT IN (
              SELECT robot_id FROM robot_state_history
              WHERE timestamp > NOW() - INTERVAL '10 minutes'
          )
    """)
    
    for task in stale:
        transition_to_recovery(task.robot_id, reason='timeout')
```

### Auto-Recovery Logic
```python
def attempt_recovery(robot_id: str, max_retries: int = 3):
    """Attempt automatic recovery with exponential backoff."""
    state = get_current_state(robot_id)
    retries = state.get('retries', 0)
    
    if retries >= max_retries:
        transition_to(robot_id, 'FAILED', reason='max_retries_exceeded')
        send_alert(f"Robot {robot_id} failed after {max_retries} retries")
        return
    
    # Exponential backoff: 30s, 60s, 120s
    backoff = 30 * (2 ** retries)
    time.sleep(backoff)
    
    # Transition to RECOVERING
    transition_to(robot_id, 'RECOVERING', retries=retries + 1)
    
    # Attempt restart
    if restart_task(robot_id):
        transition_to(robot_id, 'EXECUTING', retries=retries + 1)
    else:
        attempt_recovery(robot_id, max_retries)
```

## MQTT Integration

### State Change Events
```python
# Publish state changes to MQTT for real-time monitoring
def publish_state_change(robot_id: str, from_state: str, to_state: str):
    mqtt.publish(f"ewm/robots/{robot_id}/state", json.dumps({
        'robot_id': robot_id,
        'from_state': from_state,
        'to_state': to_state,
        'timestamp': time.time()
    }), qos=1)
```

### Topic Hierarchy
```
ewm/robots/{id}/state        # State change events
ewm/robots/{id}/task         # Task dispatch commands
ewm/robots/{id}/ack          # Robot acknowledgment
ewm/robots/{id}/complete     # Task completion
ewm/robots/{id}/error        # Task failure
```

## Anti-Patterns to Avoid

1. **Direct State Mutation**: Never set state directly; always use `execute_transition()`
2. **Missing Audit Log**: Every transition must be logged to PostgreSQL
3. **No Timeout Handling**: EXECUTING state must have watchdog monitoring
4. **Concurrent Transitions**: Always use Redis LOCK for atomic transitions
5. **Lost Recovery State**: RECOVERING → FAILED transition must alert humans

## Testing Strategy

```python
def test_lifecycle_happy_path():
    """Test CREATED → DISPATCHED → EXECUTING → COMPLETED."""
    robot_id = "test-robot-001"
    
    transition_to(robot_id, 'CREATED', task_id='task-001')
    assert get_current_state(robot_id)['state'] == 'CREATED'
    
    transition_to(robot_id, 'DISPATCHED', task_id='task-001')
    assert get_current_state(robot_id)['state'] == 'DISPATCHED'
    
    transition_to(robot_id, 'EXECUTING', task_id='task-001')
    assert get_current_state(robot_id)['state'] == 'EXECUTING'
    
    transition_to(robot_id, 'COMPLETED', task_id='task-001')
    assert get_current_state(robot_id)['state'] == 'COMPLETED'

def test_recovery_flow():
    """Test EXECUTING → FAILED → RECOVERING → EXECUTING."""
    robot_id = "test-robot-002"
    
    transition_to(robot_id, 'EXECUTING', task_id='task-002')
    transition_to(robot_id, 'FAILED', reason='connection_lost')
    transition_to(robot_id, 'RECOVERING', retries=1)
    transition_to(robot_id, 'EXECUTING', retries=1)
    
    assert get_current_state(robot_id)['retries'] == 1
```
