"""Tests for Quicktron robot strategy — VDA5050 + proprietary fallback."""

import pytest

from strategies.quicktron import QuicktronStrategy


@pytest.fixture
def strategy():
    return QuicktronStrategy()


class TestQuicktronStrategy:
    """Quicktron strategy tests covering VDA5050 and proprietary protocols."""

    def test_brand(self, strategy):
        assert strategy.brand == "Quicktron"

    def test_supported_versions(self, strategy):
        assert "2.0.0" in strategy.supported_versions

    # ── Protocol routing ────────────────────────────────

    def test_get_adapter_default(self):
        assert QuicktronStrategy.get_adapter() == "vda5050"

    def test_get_adapter_proprietary(self):
        assert QuicktronStrategy.get_adapter("proprietary") == "proprietary"

    def test_get_adapter_mixed_case(self):
        assert QuicktronStrategy.get_adapter("Proprietary") == "proprietary"

    # ── VDA5050 state mapping ───────────────────────────

    def test_vda5050_state_idle(self, strategy):
        state = {"driving": False, "batteryState": {"batteryCharge": 90}}
        result = strategy.handle_state(state)
        assert result.status == "IDLE"

    def test_vda5050_state_driving(self, strategy):
        state = {"driving": True, "batteryState": {"batteryCharge": 85}}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"

    def test_vda5050_state_executing(self, strategy):
        state = {
            "driving": False,
            "actionStates": [{"actionStatus": "RUNNING"}],
            "batteryState": {"batteryCharge": 80},
        }
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_vda5050_state_error(self, strategy):
        state = {
            "driving": False,
            "errors": [{"errorType": "DRIVE", "errorLevel": "FATAL", "errorDescription": "Motor failure"}],
            "batteryState": {"batteryCharge": 75},
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"

    def test_vda5050_state_order_id(self, strategy):
        state = {"driving": True, "orderId": "ORD-001", "batteryState": {"batteryCharge": 70}}
        result = strategy.handle_state(state)
        assert result.order_id == "ORD-001"

    # ── Proprietary state mapping ───────────────────────

    def test_proprietary_state_idle(self, strategy):
        state = {"_protocol": "proprietary", "status": "IDLE", "battery": 90}
        result = strategy.handle_state(state)
        assert result.status == "IDLE"

    def test_proprietary_state_running(self, strategy):
        state = {"_protocol": "proprietary", "taskStatus": "RUNNING", "battery": 85}
        result = strategy.handle_state(state)
        assert result.status == "MOVING"

    def test_proprietary_state_fault(self, strategy):
        state = {
            "_protocol": "proprietary",
            "taskStatus": "FAULT",
            "battery": 50,
            "faults": [{"code": "ERR-01", "level": "ERROR", "message": "Sensor timeout"}],
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"
        assert len(result.errors) == 1

    def test_proprietary_state_with_coords(self, strategy):
        state = {
            "_protocol": "proprietary",
            "taskStatus": "RUNNING",
            "battery": 80,
            "coordinateX": 10.5,
            "coordinateY": 20.3,
            "angle": 90.0,
        }
        result = strategy.handle_state(state)
        assert result.position["x"] == 10.5
        assert result.position["y"] == 20.3
        assert result.position["theta"] == 90.0

    # ── Battery normalization ───────────────────────────

    def test_normalize_battery_percent(self, strategy):
        info = strategy.normalize_battery(85)
        assert info.percent == 85.0

    def test_normalize_battery_millivolts(self, strategy):
        """29V (29000 mV) should map to ~97.6%."""
        info = strategy.normalize_battery(29000)
        assert 97.0 < info.percent < 98.0

    def test_normalize_battery_24v_full(self, strategy):
        info = strategy.normalize_battery(29200)
        assert info.percent == 100.0

    def test_normalize_battery_24v_empty(self, strategy):
        info = strategy.normalize_battery(21000)
        assert info.percent == 0.0

    def test_normalize_battery_24v_mid(self, strategy):
        info = strategy.normalize_battery(25000)
        assert 40.0 < info.percent < 50.0

    def test_normalize_battery_dict_percent(self, strategy):
        info = strategy.normalize_battery({"batteryCharge": 75})
        assert info.percent == 75.0

    def test_normalize_battery_dict_millivolts(self, strategy):
        info = strategy.normalize_battery({"batteryVoltage": 26000})
        assert 60.0 < info.percent < 62.0

    def test_normalize_battery_zero(self, strategy):
        info = strategy.normalize_battery(0)
        assert info.percent == 0.0

    # ── Millivolts converter ────────────────────────────

    def test_millivolts_to_percent(self):
        assert QuicktronStrategy._millivolts_to_percent(29200) == 100.0
        assert QuicktronStrategy._millivolts_to_percent(21000) == 0.0
        assert QuicktronStrategy._millivolts_to_percent(25100) == 50.0

    # ── Quirks ──────────────────────────────────────────

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        names = [q.name for q in quirks]
        assert "vda5050-unconfirmed" in names
        assert "battery-format-unknown" in names
        assert len(quirks) >= 2

    # ── Edge cases ──────────────────────────────────────

    def test_empty_state(self, strategy):
        result = strategy.handle_state({})
        assert result.status == "IDLE"
        assert result.battery.percent == 0.0

    def test_vda5050_missing_fields(self, strategy):
        result = strategy.handle_state({"driving": False})
        assert result.status == "IDLE"
