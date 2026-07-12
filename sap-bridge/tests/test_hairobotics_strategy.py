"""Tests for Hai Robotics robot strategy — HAIQ-ESS REST + VDA5050."""
import pytest
from strategies.hairobotics import HaiRoboticsStrategy


@pytest.fixture
def strategy():
    return HaiRoboticsStrategy()


class TestHaiRoboticsStrategy:
    """Hai Robotics strategy tests covering HAIQ and VDA5050 protocols."""

    def test_brand(self, strategy):
        assert strategy.brand == "HaiRobotics"

    def test_supported_versions(self, strategy):
        assert "2.0.0" in strategy.supported_versions

    # ── Protocol routing ────────────────────────────────

    def test_get_adapter_acr(self):
        assert HaiRoboticsStrategy.get_adapter("HaiPick ACR") == "haiq"

    def test_get_adapter_haiport(self):
        assert HaiRoboticsStrategy.get_adapter("HaiPort") == "vda5050"

    def test_get_adapter_haiflex(self):
        assert HaiRoboticsStrategy.get_adapter("HaiFlex") == "vda5050"

    def test_get_adapter_empty(self):
        assert HaiRoboticsStrategy.get_adapter("") == "haiq"

    def test_get_adapter_unknown(self):
        assert HaiRoboticsStrategy.get_adapter("Unknown") == "haiq"

    def test_supports_vda5050(self):
        assert HaiRoboticsStrategy.supports_vda5050("HaiPort") is True
        assert HaiRoboticsStrategy.supports_vda5050("HaiFlex") is True
        assert HaiRoboticsStrategy.supports_vda5050("HaiPick ACR") is False

    # ── HAIQ state mapping ──────────────────────────────

    def test_haiq_state_idle(self, strategy):
        state = {"robotType": "HaiPick ACR", "status": "IDLE", "batteryLevel": 90}
        result = strategy.handle_state(state)
        assert result.status == "IDLE"
        assert result.battery.percent == 90.0

    def test_haiq_state_retrieving(self, strategy):
        state = {"robotType": "HaiPick ACR", "taskStatus": "RETRIEVING", "batteryLevel": 85}
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_haiq_state_storing(self, strategy):
        state = {"robotType": "HaiPick ACR", "taskStatus": "STORING", "batteryLevel": 80}
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_haiq_state_fault(self, strategy):
        state = {
            "robotType": "HaiPick ACR",
            "taskStatus": "FAULT",
            "batteryLevel": 50,
            "faults": [{"faultCode": "ACR-001", "severity": "ERROR", "message": "Tote jam"}],
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"
        assert len(result.errors) == 1
        assert result.errors[0]["errorType"] == "ACR-001"

    def test_haiq_state_with_tote_id(self, strategy):
        state = {
            "robotType": "HaiPick ACR",
            "taskStatus": "WORKING",
            "batteryLevel": 75,
            "toteId": "TOTE-A123",
            "loadStatus": "loaded",
        }
        result = strategy.handle_state(state)
        assert result.load is not None
        assert result.load["toteId"] == "TOTE-A123"
        assert result.load["loadStatus"] == "loaded"

    def test_haiq_state_with_request_id(self, strategy):
        state = {"robotType": "HaiPick ACR", "taskStatus": "WORKING", "requestId": "REQ-001", "batteryLevel": 70}
        result = strategy.handle_state(state)
        assert result.order_id == "REQ-001"

    def test_haiq_state_3d_position(self, strategy):
        state = {
            "robotType": "HaiPick ACR",
            "taskStatus": "MOVING",
            "batteryLevel": 80,
            "currentLocation": {"aisle": "A01", "column": "C05", "height": 8.5},
        }
        result = strategy.handle_state(state)
        assert result.position["aisle"] == "A01"
        assert result.position["column"] == "C05"
        assert result.position["z"] == 8.5

    # ── VDA5050 state mapping ───────────────────────────

    def test_vda5050_state_driving(self, strategy):
        state = {"robotType": "HaiPort", "driving": True, "batteryState": {"batteryCharge": 85}}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"

    def test_vda5050_state_executing(self, strategy):
        state = {
            "robotType": "HaiFlex",
            "driving": False,
            "actionStates": [{"actionStatus": "RUNNING"}],
            "batteryState": {"batteryCharge": 70},
        }
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    # ── Battery ─────────────────────────────────────────

    def test_normalize_battery_percent(self, strategy):
        info = strategy.normalize_battery(85)
        assert info.percent == 85.0

    def test_normalize_battery_dict(self, strategy):
        info = strategy.normalize_battery({"batteryCharge": 75})
        assert info.percent == 75.0

    def test_normalize_battery_zero(self, strategy):
        info = strategy.normalize_battery(0)
        assert info.percent == 0.0

    # ── Quirks ──────────────────────────────────────────

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        names = [q.name for q in quirks]
        assert "tote-level-tracking" in names
        assert "haiq-callback-completion" in names
        assert "acr-no-vda5050" in names
        assert len(quirks) >= 4

    # ── Edge cases ──────────────────────────────────────

    def test_empty_state(self, strategy):
        result = strategy.handle_state({})
        assert result.status == "IDLE"
        assert result.battery.percent == 0.0

    def test_haiq_missing_fields(self, strategy):
        state = {"robotType": "HaiPick ACR"}
        result = strategy.handle_state(state)
        assert isinstance(result.errors, list)
