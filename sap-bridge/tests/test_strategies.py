"""Tests for robot brand strategies."""
import json
import pytest
from strategies.base import BaseStrategy, RobotState, BatteryInfo, BrandQuirk
from strategies.kuka import KukaStrategy
from strategies.mir import MirStrategy
from strategies.otto import OttoStrategy
from strategies.registry import StrategyRegistry


class TestBaseStrategy:
    """Base class behavior."""

    def test_cannot_instantiate_abstract(self):
        """BaseStrategy should not be instantiable directly."""
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_validate_state_transition_valid(self):
        """Valid VDA5050 state transitions."""
        strategy = KukaStrategy()
        assert strategy.validate_state_transition("IDLE", "MOVING") is True
        assert strategy.validate_state_transition("MOVING", "EXECUTING") is True
        assert strategy.validate_state_transition("EXECUTING", "IDLE") is True
        assert strategy.validate_state_transition("ERROR", "IDLE") is True

    def test_validate_state_transition_invalid(self):
        """Invalid state transitions."""
        strategy = KukaStrategy()
        assert strategy.validate_state_transition("IDLE", "ERROR") is True   # ERROR from IDLE is valid
        assert strategy.validate_state_transition("IDLE", "EXECUTING") is False  # Must go MOVING first
        assert strategy.validate_state_transition("MOVING", "CHARGING") is False

    def test_map_connection_state(self):
        strategy = KukaStrategy()
        assert strategy.map_connection_state({"connectionState": "ONLINE"}) == "ONLINE"
        assert strategy.map_connection_state({"connectionState": "OFFLINE"}) == "OFFLINE"
        assert strategy.map_connection_state({"connectionState": "CONNECTIONBROKEN"}) == "OFFLINE"
        assert strategy.map_connection_state({}) == "UNKNOWN"


class TestKukaStrategy:
    """KUKA KMR iiwa specific behavior."""

    @pytest.fixture
    def strategy(self):
        return KukaStrategy()

    def test_brand_properties(self, strategy):
        assert strategy.brand == "KUKA"
        assert strategy.supported_versions == ["2.0.0"]

    def test_handle_idle_state(self, strategy):
        """KUKA idle state."""
        state = {
            "driving": False,
            "paused": False,
            "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 85.0, "batteryVoltage": 48.0},
            "agvPosition": {"x": 10.0, "y": 5.0, "theta": 90.0, "lastNodeId": "NODE-01", "positionInitialized": True},
            "errors": [],
            "orderId": "",
        }
        result = strategy.handle_state(state)
        assert result.status == "IDLE"
        assert result.battery.percent == 85.0
        assert result.battery.voltage == 48.0
        assert result.position["x"] == 10.0
        assert result.position["y"] == 5.0

    def test_handle_driving_state(self, strategy):
        """KUKA moving state."""
        state = {
            "driving": True,
            "paused": False,
            "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 80.0},
            "agvPosition": {"x": 20.0, "y": 10.0, "theta": 0.0, "lastNodeId": "NODE-02", "positionInitialized": True},
            "errors": [],
            "orderId": "ORDER-001",
        }
        result = strategy.handle_state(state)
        assert result.status == "MOVING"
        assert result.driving is True
        assert result.order_id == "ORDER-001"

    def test_handle_paused_state(self, strategy):
        state = {
            "driving": False, "paused": True, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 75.0},
            "agvPosition": {"x": 0, "y": 0, "theta": 0, "lastNodeId": "", "positionInitialized": False},
            "errors": [],
        }
        result = strategy.handle_state(state)
        assert result.status == "PAUSED"

    def test_handle_fatal_error(self, strategy):
        state = {
            "driving": False, "paused": False, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 50.0},
            "agvPosition": {"x": 0, "y": 0, "theta": 0, "lastNodeId": "", "positionInitialized": False},
            "errors": [{"errorType": "DRIVE_FAILURE", "errorLevel": "FATAL", "errorDescription": "Motor stall"}],
        }
        result = strategy.handle_state(state)
        assert result.status == "ERROR"
        assert len(result.errors) == 1
        assert result.errors[0]["errorType"] == "DRIVE_FAILURE"

    def test_handle_executing_state(self, strategy):
        state = {
            "driving": False, "paused": False, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 70.0},
            "agvPosition": {"x": 0, "y": 0, "theta": 0, "lastNodeId": "", "positionInitialized": False},
            "errors": [],
            "actionStates": [{"actionId": "ACT-01", "actionType": "lift", "actionStatus": "RUNNING"}],
        }
        result = strategy.handle_state(state)
        assert result.status == "EXECUTING"

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        assert len(quirks) >= 1
        assert any(q.name == "lift-action-requires-pre-navigate" for q in quirks)


class TestMirStrategy:
    """MiR250 specific quirks."""

    @pytest.fixture
    def strategy(self):
        return MirStrategy()

    def test_brand_properties(self, strategy):
        assert strategy.brand == "MiR"
        assert strategy.supported_versions == ["1.1.0"]

    def test_driving_state_mapped_to_moving(self, strategy):
        """MiR reports DRIVING, we map to MOVING."""
        state = {
            "driving": True, "paused": False, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 80.0, "batteryVoltage": 48.0},
            "agvPosition": {"x": 5.0, "y": 5.0, "theta": 0.0, "lastNodeId": "HOME", "positionInitialized": True},
            "errors": [],
            "drivingState": "DRIVING",
        }
        result = strategy.handle_state(state)
        assert result.status == "MOVING"

    def test_waiting_before_idle(self, strategy):
        """MiR sends WAITING before IDLE — grace counter."""
        # First WAITING report
        state1 = {
            "driving": False, "paused": False, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 60.0},
            "agvPosition": {"x": 10.0, "y": 10.0, "theta": 0.0, "lastNodeId": "NODE-05", "positionInitialized": True},
            "errors": [],
            "drivingState": "WAITING",
        }
        result1 = strategy.handle_state(state1)
        assert result1.status == "IDLE"  # Grace period: treat as IDLE

        # Another round should also be IDLE (we've consumed the counter)
        result2 = strategy.handle_state(state1)
        assert result2.status == "IDLE"

    def test_mir_battery_percentage(self, strategy):
        """MiR reports percentage directly."""
        bat = strategy.normalize_battery({"batteryCharge": 65.0, "batteryVoltage": 48.0, "charging": False})
        assert bat.percent == 65.0
        assert bat.voltage == 48.0
        assert bat.charging is False

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        names = [q.name for q in quirks]
        assert "driving-vs-moving" in names
        assert "waiting-before-idle" in names
        assert "vda5050-v1.1-legacy" in names


class TestOttoStrategy:
    """OTTO 1500 specific behavior (millivolt battery)."""

    @pytest.fixture
    def strategy(self):
        return OttoStrategy()

    def test_brand_properties(self, strategy):
        assert strategy.brand == "OTTO"
        assert strategy.supported_versions == ["2.0.0"]

    def test_battery_millivolt_conversion_full(self, strategy):
        """54600mV → ~100%."""
        bat = strategy.normalize_battery({"batteryVoltage": 54600, "charging": False})
        assert bat.percent > 99.0
        assert bat.voltage == 54.6

    def test_battery_millivolt_conversion_empty(self, strategy):
        """48000mV → ~0%."""
        bat = strategy.normalize_battery({"batteryVoltage": 48000, "charging": False})
        assert bat.percent < 1.0
        assert bat.voltage == 48.0

    def test_battery_millivolt_mid(self, strategy):
        """~51300mV → ~50%."""
        bat = strategy.normalize_battery({"batteryVoltage": 51300})
        assert 40.0 < bat.percent < 60.0

    def test_charging_detected_via_flag(self, strategy):
        bat = strategy.normalize_battery({"batteryVoltage": 52000, "charging": True})
        assert bat.charging is True

    def test_charging_detected_via_voltage(self, strategy):
        """Voltage > 53500 → likely charging."""
        bat = strategy.normalize_battery({"batteryVoltage": 54000, "charging": False})
        assert bat.charging is True

    def test_otto_charging_state(self, strategy):
        """OTTO reports CHARGING via battery flag."""
        state = {
            "driving": False, "paused": False, "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryVoltage": 54000, "charging": True},
            "agvPosition": {"x": 0, "y": 0, "theta": 0, "lastNodeId": "", "positionInitialized": False},
            "errors": [],
        }
        result = strategy.handle_state(state)
        assert result.status == "CHARGING"

    def test_get_quirks(self, strategy):
        quirks = strategy.get_quirks()
        names = [q.name for q in quirks]
        assert "battery-millivolt" in names
        assert "charging-state-format" in names


class TestStrategyRegistry:

    @pytest.fixture
    def registry(self):
        return StrategyRegistry()

    def test_registered_brands(self, registry):
        brands = registry.list_brands()
        assert "KUKA" in brands
        assert "MIR" in brands
        assert "OTTO" in brands

    def test_get_strategy(self, registry):
        kuka = registry.get("KUKA")
        assert kuka is not None
        assert kuka.brand == "KUKA"

        mir = registry.get("MIR")
        assert mir is not None
        assert mir.brand == "MiR"

    def test_get_case_insensitive(self, registry):
        assert registry.get("kuka") is not None
        assert registry.get("mir") is not None
        assert registry.get("OtTo") is not None

    def test_get_unknown_brand(self, registry):
        assert registry.get("NONEXISTENT") is None

    def test_get_or_fallback_unknown(self, registry):
        """Unknown brand should fall back to KUKA."""
        strategy = registry.get_or_fallback("UNKNOWN_BRAND")
        assert strategy is not None
        assert strategy.brand == "KUKA"

    def test_register_custom(self, registry):
        """Can register custom strategies."""
        from strategies.base import BaseStrategy, RobotState, BatteryInfo

        class CustomStrategy(BaseStrategy):
            @property
            def brand(self): return "CUSTOM"
            @property
            def supported_versions(self): return ["2.0.0"]
            def handle_state(self, state): return RobotState(status="IDLE", battery=BatteryInfo(percent=100), position={})
            def normalize_battery(self, raw): return BatteryInfo(percent=100)

        registry.register(CustomStrategy())
        assert registry.get("CUSTOM") is not None

    def test_count(self, registry):
        assert registry.count() == 6

    def test_get_or_fallback_returns_strategy(self, registry):
        fallback = registry.get_or_fallback("UNKNOWN_999")
        assert fallback is not None
        assert fallback.brand in ("KUKA", "CUSTOM")

    def test_double_register_same_brand(self, registry):
        count = registry.count()
        from strategies.base import BaseStrategy, RobotState, BatteryInfo
        class DupStrategy(BaseStrategy):
            @property
            def brand(self): return "KUKA"
            @property
            def supported_versions(self): return ["2.0.0"]
            def handle_state(self, state): return RobotState(status="IDLE", battery=BatteryInfo(percent=100), position={})
            def normalize_battery(self, raw): return BatteryInfo(percent=100)
        registry.register(DupStrategy())
        assert registry.count() == count


class TestBaseStrategyUtils:
    """BaseStrategy utility methods."""

    @pytest.fixture
    def kuka(self):
        from strategies.kuka import KukaStrategy
        return KukaStrategy()

    def test_connection_state_online(self, kuka):
        assert kuka.map_connection_state({"connectionState": "ONLINE"}) == "ONLINE"

    def test_connection_state_offline(self, kuka):
        assert kuka.map_connection_state({"connectionState": "OFFLINE"}) == "OFFLINE"

    def test_connection_state_broken(self, kuka):
        assert kuka.map_connection_state({"connectionState": "CONNECTIONBROKEN"}) == "OFFLINE"

    def test_connection_state_empty(self, kuka):
        assert kuka.map_connection_state({}) == "UNKNOWN"

    def test_operating_mode_automatic(self, kuka):
        assert kuka.map_operating_mode("AUTOMATIC") == "AUTOMATIC"

    def test_operating_mode_manual(self, kuka):
        assert kuka.map_operating_mode("MANUAL") == "MANUAL"

    def test_operating_mode_fallback(self, kuka):
        assert kuka.map_operating_mode("UNKNOWN") == "MANUAL"

    def test_validate_idle_to_moving(self, kuka):
        assert kuka.validate_state_transition("IDLE", "MOVING") is True

    def test_validate_init_to_idle(self, kuka):
        assert kuka.validate_state_transition("INIT", "IDLE") is True

    def test_validate_invalid(self, kuka):
        assert kuka.validate_state_transition("INIT", "MOVING") is False

    def test_extract_position_normal(self, kuka):
        pos = kuka.extract_position({"agvPosition": {"x": 1.0, "y": 2.0, "theta": 3.0, "lastNodeId": "N1", "positionInitialized": True}})
        assert pos["x"] == 1.0

    def test_extract_position_empty(self, kuka):
        pos = kuka.extract_position({})
        assert pos["x"] == 0.0

    def test_extract_position_fallback(self, kuka):
        pos = kuka.extract_position({"position": {"x": 5.0}})
        assert pos["x"] == 5.0

    def test_extract_errors_empty(self, kuka):
        assert kuka.extract_errors({}) == []

    def test_extract_errors_with_data(self, kuka):
        errs = kuka.extract_errors({"errors": [{"errorType": "E1", "errorLevel": "FATAL", "errorDescription": "Bad"}]})
        assert len(errs) == 1

    def test_extract_errors_malformed(self, kuka):
        assert kuka.extract_errors({"errors": "bad"}) == []
