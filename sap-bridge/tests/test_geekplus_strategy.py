"""Tests for Geek+ robot strategy — dual protocol (IOP REST + VDA5050)."""

import pytest

from strategies.geekplus import GeekPlusStrategy


@pytest.fixture
def strategy():
    return GeekPlusStrategy()


class TestGeekPlusStrategy:
    """Geek+ strategy tests covering both IOP and VDA5050 protocols."""

    def test_brand(self, strategy):
        assert strategy.brand == "GeekPlus"

    def test_supported_versions(self, strategy):
        assert "2.0.0" in strategy.supported_versions

    # ── Protocol routing ────────────────────────────────

    def test_get_adapter_p_series(self):
        assert GeekPlusStrategy.get_adapter("P-Series") == "iop"
        assert GeekPlusStrategy.get_adapter("P800") == "iop"

    def test_get_adapter_s_series(self):
        assert GeekPlusStrategy.get_adapter("S-Series") == "iop"
        assert GeekPlusStrategy.get_adapter("S200") == "iop"

    def test_get_adapter_m_series(self):
        assert GeekPlusStrategy.get_adapter("M-Series") == "vda5050"
        assert GeekPlusStrategy.get_adapter("M600") == "vda5050"

    def test_get_adapter_r_series(self):
        assert GeekPlusStrategy.get_adapter("R-Series") == "vda5050"
        assert GeekPlusStrategy.get_adapter("R1000") == "vda5050"

    def test_get_adapter_empty(self):
        assert GeekPlusStrategy.get_adapter("") == "iop"

    def test_get_adapter_unknown(self):
        assert GeekPlusStrategy.get_adapter("UNKNOWN") == "iop"

    def test_supports_vda5050(self):
        assert GeekPlusStrategy.supports_vda5050("M600") is True
        assert GeekPlusStrategy.supports_vda5050("R1000") is True
        assert GeekPlusStrategy.supports_vda5050("P800") is False
        assert GeekPlusStrategy.supports_vda5050("S200") is False

    # ── IOP state mapping ───────────────────────────────

    def test_handle_iop_state_idle(self, strategy):
        state = {"robotModel": "P800", "status": "IDLE", "batteryLevel": 85}
        result = strategy.handle_state(state)
        assert result.status == "IDLE"
        assert result.battery.percent == 85.0

    def test_handle_iop_state_moving(self, strategy):
        state = {"robotModel": "P800", "status": "MOVING", "battery": 60}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"
        assert result.driving is True

    def test_handle_iop_state_working(self, strategy):
        state = {"robotModel": "S200", "taskStatus": "WORKING", "batteryLevel": 90}
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_handle_iop_state_fault(self, strategy):
        state = {
            "robotModel": "P800",
            "status": "FAULT",
            "batteryLevel": 50,
            "faults": [
                {"faultCode": "E001", "level": "ERROR", "message": "Pick timeout"},
            ],
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"
        assert len(result.errors) == 1
        assert result.errors[0]["errorType"] == "E001"

    def test_handle_iop_state_charging(self, strategy):
        state = {"robotModel": "P800", "status": "CHARGING", "batteryLevel": 95}
        result = strategy.handle_state(state)
        assert result.status == "CHARGING"

    def test_handle_iop_with_location_string(self, strategy):
        state = {"robotModel": "P800", "status": "IDLE", "location": "STAGING-01", "batteryLevel": 80}
        result = strategy.handle_state(state)
        assert result.position["locationCode"] == "STAGING-01"

    def test_handle_iop_with_mission_id(self, strategy):
        state = {"robotModel": "S200", "taskStatus": "WORKING", "missionId": "M-001", "batteryLevel": 75}
        result = strategy.handle_state(state)
        assert result.order_id == "M-001"

    def test_handle_iop_load_weight(self, strategy):
        state = {"robotModel": "P800", "status": "WORKING", "loadWeight": 500, "batteryLevel": 70}
        result = strategy.handle_state(state)
        assert result.load is not None
        assert result.load["weight"] == 500

    # ── VDA5050 state mapping ───────────────────────────

    def test_handle_vda5050_state_driving(self, strategy):
        state = {"robotModel": "M600", "driving": True, "batteryState": {"batteryCharge": 80}}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"
        assert result.driving is True

    def test_handle_vda5050_state_executing(self, strategy):
        state = {
            "robotModel": "M600",
            "driving": False,
            "actionStates": [{"actionStatus": "RUNNING"}],
            "batteryState": {"batteryCharge": 75},
        }
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_handle_vda5050_state_error(self, strategy):
        state = {
            "robotModel": "M600",
            "driving": False,
            "errors": [{"errorType": "HARDWARE", "errorLevel": "FATAL", "errorDescription": "Motor stall"}],
            "batteryState": {"batteryCharge": 50},
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"

    def test_handle_vda5050_state_order_id(self, strategy):
        state = {
            "robotModel": "R1000",
            "driving": True,
            "orderId": "ORDER-123",
            "batteryState": {"batteryCharge": 90},
        }
        result = strategy.handle_state(state)
        assert result.order_id == "ORDER-123"

    # ── Battery normalization ───────────────────────────

    def test_normalize_battery_percent(self, strategy):
        info = strategy.normalize_battery(85)
        assert info.percent == 85.0

    def test_normalize_battery_dict(self, strategy):
        info = strategy.normalize_battery({"batteryCharge": 75, "percentage": 80})
        assert info.percent == 75.0

    def test_normalize_battery_clamps(self, strategy):
        info = strategy.normalize_battery(150)
        assert info.percent == 100.0

    def test_normalize_battery_zero(self, strategy):
        info = strategy.normalize_battery(0)
        assert info.percent == 0.0

    # ── Quirks ──────────────────────────────────────────

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        names = [q.name for q in quirks]
        assert "iop-mission-polling" in names
        assert "series-split" in names
        assert "battery-percentage-only" in names
        assert len(quirks) >= 4

    # ── Edge cases ──────────────────────────────────────

    def test_empty_state(self, strategy):
        result = strategy.handle_state({})
        # Empty state defaults to IOP adapter with IDLE status (safe fallback)
        assert result.status == "IDLE"
        assert result.battery.percent == 0.0

    def test_iop_with_missing_fields(self, strategy):
        state = {"robotModel": "P800"}
        result = strategy.handle_state(state)
        assert result.status in ("IDLE", "UNKNOWN")
        assert isinstance(result.errors, list)

    def test_vda5050_with_missing_fields(self, strategy):
        state = {"robotModel": "M600"}
        result = strategy.handle_state(state)
        assert result.status in ("IDLE", "UNKNOWN")

    def test_model_prefix_detection(self, strategy):
        """Robot model like 'M600-01' should still route to VDA5050."""
        state = {"robotModel": "M600-01", "driving": True, "batteryState": {"batteryCharge": 50}}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"
