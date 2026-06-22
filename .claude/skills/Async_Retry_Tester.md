# Async_Retry_Tester

## Trigger
Activate this skill when writing tests for the system, especially tests involving SAP integration, AGV communication, or network reliability.

## Core Requirements

### 1. Test Framework Setup
```python
# tests/conftest.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientSession, ClientTimeout, ClientError
import pytest_asyncio

@pytest.fixture
def event_loop():
    """Create instance of event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def aiohttp_session():
    """Provide aiohttp session for tests."""
    async with ClientSession() as session:
        yield session

@pytest.fixture
def mock_sap_response_success():
    """Mock successful SAP OData response."""
    return {
        "d": {
            "results": [
                {"OrderID": "ORD001", "Status": "Active"},
                {"OrderID": "ORD002", "Status": "Completed"}
            ]
        }
    }

@pytest.fixture
def mock_vda5050_state():
    """Mock VDA5050 AGV state message."""
    return {
        "headerId": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "version": "2.0.0",
        "manufacturer": "TestAGV",
        "serialNumber": "AGV001",
        "batteryState": {
            "batteryCharge": 85.0,
            "batteryVoltage": 48.0,
            "charging": False
        }
    }
```

### 2. SAP Timeout Simulation Tests
```python
# tests/test_sap_retry.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from aiohttp import ClientError, ClientTimeout
from tenacity import RetryError

@pytest.mark.asyncio
async def test_sap_call_retries_on_timeout(aiohttp_session):
    """Test that SAP calls retry on timeout with exponential backoff."""
    from your_module import sap_odata_call
    
    call_count = 0
    
    async def mock_timeout(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise asyncio.TimeoutError("Connection timeout")
        # Return success on 3rd attempt
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch.object(aiohttp_session, 'get', side_effect=mock_timeout):
        result = await sap_odata_call(aiohttp_session, "http://sap-test/odata")
        
        assert call_count == 3, "Should retry 3 times before success"
        assert result["success"] is True

@pytest.mark.asyncio
async def test_sap_call_exhausts_retries(aiohttp_session):
    """Test that SAP call fails after exhausting all retries."""
    from your_module import sap_odata_call
    
    async def mock_always_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Persistent timeout")
    
    with patch.object(aiohttp_session, 'get', side_effect=mock_always_timeout):
        with pytest.raises(RetryError):
            await sap_odata_call(
                aiohttp_session,
                "http://sap-test/odata",
                max_retries=3  # Override default for faster test
            )

@pytest.mark.asyncio
async def test_sap_call_retries_on_503(aiohttp_session):
    """Test retry on SAP service unavailable (503)."""
    from your_module import sap_odata_call
    
    call_count = 0
    
    async def mock_503_then_success(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_response = AsyncMock()
        
        if call_count < 2:
            mock_response.status = 503
            mock_response.raise_for_status.side_effect = Exception("Service Unavailable")
        else:
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"recovered": True})
            mock_response.raise_for_status = MagicMock()
        
        return mock_response
    
    with patch.object(aiohttp_session, 'get', side_effect=mock_503_then_success):
        result = await sap_odata_call(aiohttp_session, "http://sap-test/odata")
        assert result["recovered"] is True
        assert call_count == 2
```

### 3. AGV Communication Failure Tests
```python
# tests/test_agv_communication.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_agv_heartbeat_timeout_triggers_fault():
    """Test that AGV transitions to Fault on heartbeat timeout."""
    from your_module import HeartbeatMonitor, AGVStateMachine
    
    sm = AGVStateMachine(initial_state="Executing")
    monitor = HeartbeatMonitor(timeout_seconds=2)
    
    fault_triggered = False
    fault_reason = ""
    
    async def on_fault(agv_id, reason):
        nonlocal fault_triggered, fault_reason
        fault_triggered = True
        fault_reason = reason
        sm.transition_to("Fault", reason)
    
    monitor.on_heartbeat_timeout(on_fault)
    monitor.record_heartbeat("AGV001")
    
    # Start monitoring in background
    monitor_task = asyncio.create_task(monitor.start_monitoring())
    
    # Wait for timeout
    await asyncio.sleep(3)
    
    assert fault_triggered is True
    assert "Heartbeat timeout" in fault_reason
    assert sm.state == "Fault"
    
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

@pytest.mark.asyncio
async def test_low_battery_triggers_auto_return():
    """Test that low battery initiates auto-return to charging station."""
    from your_module import BatteryManager, AGVStateMachine
    
    sm = AGVStateMachine(initial_state="Executing")
    battery_mgr = BatteryManager("AGV001", sm)
    
    # Test low battery (15%)
    decision = await battery_mgr.check_battery_and_decide(
        battery_charge=15.0,
        current_node="NODE_005"
    )
    
    assert decision["action"] == "complete_then_charge"
    assert "Low battery" in decision["reason"]
    assert decision["target_node"] == "CHARGE_001"
    
    # Test critical battery (8%)
    decision = await battery_mgr.check_battery_and_decide(
        battery_charge=8.0,
        current_node="NODE_005"
    )
    
    assert decision["action"] == "interrupt_and_charge"
    assert "Critical battery" in decision["reason"]

@pytest.mark.asyncio
async def test_agv_rejects_illegal_state_transition():
    """Test that AGV rejects illegal state transitions."""
    from your_module import AGVStateMachine, IllegalStateTransitionError
    
    sm = AGVStateMachine(initial_state="Idle")
    
    # Legal transition
    sm.transition_to("Executing", "Start order")
    assert sm.state == "Executing"
    
    # Illegal: Executing → Charging (should go through Fault or complete first)
    # Actually this is legal in VDA5050, let's test Fault → Executing
    sm.transition_to("Fault", "Error detected")
    assert sm.state == "Fault"
    
    # Illegal: Fault → Executing (must go through Idle)
    with pytest.raises(IllegalStateTransitionError) as exc_info:
        sm.transition_to("Executing", "Resume order")
    
    assert "Illegal transition" in str(exc_info.value)
    assert "Fault → Executing" in str(exc_info.value)
```

### 4. Exponential Backoff Verification Tests
```python
# tests/test_backoff_timing.py
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, call

@pytest.mark.asyncio
async def test_exponential_backoff_timing():
    """Verify that retry timing follows exponential backoff pattern."""
    from your_module import sap_odata_call
    
    timestamps = []
    call_count = 0
    
    async def mock_failure_with_timing(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        timestamps.append(time.time())
        
        if call_count < 4:
            raise asyncio.TimeoutError(f"Timeout #{call_count}")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch.object(aiohttp_session, 'get', side_effect=mock_failure_with_timing):
        result = await sap_odata_call(aiohttp_session, "http://sap-test/odata")
        
        assert call_count == 4
        
        # Verify increasing delays between retries
        if len(timestamps) >= 3:
            delay_1 = timestamps[1] - timestamps[0]
            delay_2 = timestamps[2] - timestamps[1]
            delay_3 = timestamps[3] - timestamps[2]
            
            # Exponential: delay should increase (approximately)
            assert delay_2 > delay_1, "Delay 2 should be greater than delay 1"
            assert delay_3 > delay_2, "Delay 3 should be greater than delay 2"

@pytest.mark.asyncio
async def test_backoff_respects_max_wait():
    """Test that backoff doesn't exceed maximum wait time."""
    from your_module import sap_odata_call
    import tenacity
    
    call_count = 0
    wait_times = []
    
    def record_wait_time(retry_state):
        wait_times.append(retry_state.next_action.sleep)
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=record_wait_time
    )
    async def failing_call():
        nonlocal call_count
        call_count += 1
        raise ClientError("Persistent failure")
    
    with pytest.raises(RetryError):
        await failing_call()
    
    # Verify no wait time exceeds max (10 seconds)
    assert all(wt <= 10 for wt in wait_times), "Wait times should not exceed max"
```

### 5. Integration Test with Mock Servers
```python
# tests/test_integration.py
import pytest
import asyncio
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

class TestWithMockSAPServer(AioHTTPTestCase):
    """Integration tests with mock SAP server."""
    
    async def get_application(self):
        """Setup mock SAP OData server."""
        app = web.Application()
        app.router.add_get('/sap/opu/odata/EntitySet', self.handle_odata_request)
        app.router.add_post('/sap/opu/odata/EntitySet', self.handle_odata_post)
        return app
    
    async def handle_odata_request(self, request):
        """Mock SAP OData GET endpoint."""
        # Simulate slow response
        await asyncio.sleep(0.5)
        
        # Check CSRF token fetch
        if request.headers.get("X-CSRF-Token") == "Fetch":
            return web.json_response(
                {"d": {}},
                headers={"X-CSRF-Token": "mock-csrf-token-123"}
            )
        
        return web.json_response({
            "d": {
                "results": [
                    {"ID": "1", "Name": "Test Entity"}
                ]
            }
        })
    
    async def handle_odata_post(self, request):
        """Mock SAP OData POST endpoint."""
        # Validate CSRF token
        csrf_token = request.headers.get("X-CSRF-Token")
        if csrf_token != "mock-csrf-token-123":
            return web.json_response(
                {"error": "Invalid CSRF token"},
                status=403
            )
        
        payload = await request.json()
        return web.json_response({
            "d": {
                "ID": "2",
                "Name": payload.get("Name", "Created Entity")
            }
        }, status=201)
    
    @pytest.mark.asyncio
    async def test_full_odata_flow_with_csrf(self):
        """Test complete OData flow: fetch CSRF token → create entity."""
        from your_module import fetch_csrf_token, create_entity
        
        # Step 1: Fetch CSRF token
        csrf_token = await fetch_csrf_token(self.client, str(self.server.make_url('/')))
        assert csrf_token == "mock-csrf-token-123"
        
        # Step 2: Create entity with CSRF token
        result = await create_entity(
            self.client,
            str(self.server.make_url('/')),
            {"Name": "Test"},
            csrf_token
        )
        
        assert result["d"]["ID"] == "2"
        assert result["d"]["Name"] == "Created Entity"
```

### 6. Test Coverage Requirements
```bash
# Run tests with coverage
pytest tests/ \
  --cov=your_module \
  --cov-report=html \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -v

# Minimum coverage thresholds:
# - SAP integration code: 90%
# - VDA5050 state machine: 95%
# - Retry logic: 100%
# - Battery management: 85%
```

### 7. Pytest Configuration
```ini
# pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    sap: marks tests requiring SAP mock
    agv: marks tests for AGV logic
    integration: marks integration tests
addopts = 
    --verbose
    --tb=short
    --strict-markers
    --cov-config=.coveragerc
```

## Anti-Patterns (DENIED)
❌ Using time.sleep() in async tests (use asyncio.sleep())
❌ Not mocking external services (SAP, MQTT broker)
❌ Testing without asserting retry behavior
❌ Ignoring race conditions in concurrent AGV tests
❌ Not testing timeout scenarios
❌ Skipping CSRF token validation in tests
❌ Not verifying exponential backoff timing
❌ Tests that depend on execution order

## References
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- aiohttp testing: https://docs.aiohttp.org/en/stable/testing.html
- tenacity retry testing: https://tenacity.readthedocs.io/en/latest/testing.html
- VDA5050 testing: https://github.com/VDA5050/VDA5050/blob/master/TESTING.md
