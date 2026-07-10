"""Tests for the coordinator adapter bootstrap module."""

import pytest

from core.adapter.fleet_adapter import FleetAdapter
from core.coordinator import RobotPlatformCoordinator
from traffic_coordinator_v5.bootstrap import (
    SUPPORTED_BRANDS,
    _create_generic_adapter,
    bootstrap_adapters,
)


class TestSupportedBrands:
    """Tests for the SUPPORTED_BRANDS constant."""

    def test_has_seven_brands(self):
        assert len(SUPPORTED_BRANDS) == 7

    def test_includes_all_expected_brands(self):
        expected = {"mir", "otto", "kuka", "geekplus", "hairobotics", "quicktron", "generic"}
        assert set(SUPPORTED_BRANDS) == expected

    def test_all_brands_are_strings(self):
        for brand in SUPPORTED_BRANDS:
            assert isinstance(brand, str)


class TestCreateGenericAdapter:
    """Tests for the _create_generic_adapter factory."""

    def test_returns_fleet_adapter(self):
        adapter = _create_generic_adapter("mir")
        assert isinstance(adapter, FleetAdapter)

    def test_brand_is_set(self):
        adapter = _create_generic_adapter("kuka")
        assert adapter.brand == "kuka"

    def test_different_brands_produce_different_adapters(self):
        a1 = _create_generic_adapter("mir")
        a2 = _create_generic_adapter("otto")
        assert a1 is not a2
        assert a1.brand == "mir"
        assert a2.brand == "otto"

    def test_map_vendor_state_passthrough(self):
        """The pass-through mapper should return a FleetState from a dict."""
        from core.messages import FleetState, HealthStatus, SensorHealth

        adapter = _create_generic_adapter("generic")
        raw = {
            "robot_id": "test-001",
            "x": 3.0,
            "y": 4.0,
            "theta": 0.0,
            "velocity": 0.5,
            "battery_percent": 92.0,
            "mode": "IDLE",
            "sensorHealth": {
                "velocity_sensor": "HEALTHY",
                "lidar": "DEGRADED",
                "camera": "HEALTHY",
                "time_sync": "HEALTHY",
            },
        }
        state = adapter.map_vendor_state(raw)
        assert isinstance(state, FleetState)
        assert state.robot_id == "test-001"
        assert state.pose.x == 3.0
        assert state.pose.y == 4.0
        assert state.velocity == 0.5
        assert state.battery_percent == 92.0
        assert isinstance(state.sensor_health, SensorHealth)
        assert state.sensor_health.lidar == HealthStatus.DEGRADED
        assert state.sensor_health.degraded is True

    def test_passthrough_minimal_payload(self):
        """Minimal payload should get sensible defaults."""
        from core.messages import FleetState, SensorHealth

        adapter = _create_generic_adapter("generic")
        state = adapter.map_vendor_state({})
        assert isinstance(state, FleetState)
        assert state.robot_id == "unknown"
        assert state.pose.x == 0.0
        assert state.battery_percent == 100.0
        assert isinstance(state.sensor_health, SensorHealth)
        assert state.sensor_health.velocity_sensor.name == "HEALTHY"

    def test_passthrough_capability_vector(self):
        """Capability fields should be parsed into a CapabilityVector."""
        from core.messages import ActionPrimitive, CapabilityVector, FleetState

        adapter = _create_generic_adapter("generic")
        raw = {
            "robot_id": "test-002",
            "capability": {
                "payload_kg": 50.0,
                "max_speed": 1.2,
                "supported_models": ["AMR"],
                "action_primitives": ["MOVE", "PICK"],
                "supports_reverse": True,
            },
        }
        state = adapter.map_vendor_state(raw)
        assert isinstance(state, FleetState)
        assert isinstance(state.capability, CapabilityVector)
        assert state.capability.payload_kg == 50.0
        assert state.capability.max_speed == 1.2
        assert state.capability.supported_models == ["AMR"]
        assert ActionPrimitive.MOVE in state.capability.action_primitives
        assert ActionPrimitive.PICK in state.capability.action_primitives
        assert state.capability.supports_reverse is True

    def test_passthrough_with_errors(self):
        adapter = _create_generic_adapter("generic")
        raw = {"errors": ["NAV_FAIL", "BAT_LOW"]}
        state = adapter.map_vendor_state(raw)
        assert state.errors == ["NAV_FAIL", "BAT_LOW"]

    def test_passthrough_position_initialized(self):
        adapter = _create_generic_adapter("generic")
        raw = {"position_initialized": True, "last_node_id": "node-5"}
        state = adapter.map_vendor_state(raw)
        assert state.pose.position_initialized is True
        assert state.pose.last_node_id == "node-5"


class TestBootstrapAdapters:
    """Tests for the bootstrap_adapters function."""

    @pytest.fixture
    def coordinator(self):
        return RobotPlatformCoordinator()

    def test_registers_all_brands_by_default(self, coordinator):
        adapters = bootstrap_adapters(coordinator)
        assert len(adapters) == 7
        for brand in SUPPORTED_BRANDS:
            assert brand in adapters
            assert isinstance(adapters[brand], FleetAdapter)
            assert adapters[brand].brand == brand

    def test_registers_subset_when_brands_specified(self, coordinator):
        adapters = bootstrap_adapters(coordinator, brands=["mir", "kuka"])
        assert len(adapters) == 2
        assert "mir" in adapters
        assert "kuka" in adapters
        assert "otto" not in adapters

    def test_adapters_are_registered_with_coordinator(self, coordinator):
        """After bootstrap, each adapter should be registered on the coordinator."""
        adapters = bootstrap_adapters(coordinator, brands=["mir"])
        assert "mir" in adapters
        # The adapter was registered via coordinator.register_adapter()
        assert isinstance(adapters["mir"], FleetAdapter)

    def test_empty_brands_list_falls_back_to_all(self, coordinator):
        """bootstrap_adapters treats empty list [] as falsy → falls back to all brands."""
        adapters = bootstrap_adapters(coordinator, brands=[])
        assert len(adapters) == 7  # [] is falsy, so brands = SUPPORTED_BRANDS

    def test_unknown_brand_still_creates_adapter(self, coordinator):
        """Even unknown brands get a generic adapter — no brand check happens."""
        adapters = bootstrap_adapters(coordinator, brands=["tesla_bot"])
        assert "tesla_bot" in adapters
        assert isinstance(adapters["tesla_bot"], FleetAdapter)

    def test_duplicate_brands_raises(self, coordinator):
        """register_adapter raises ValueError when a brand is registered twice."""
        with pytest.raises(ValueError, match="already registered"):
            bootstrap_adapters(coordinator, brands=["mir", "mir"])

    def test_result_adapters_can_map_state(self, coordinator):
        """All bootstrapped adapters should be able to map a vendor state."""
        from core.messages import FleetState

        adapters = bootstrap_adapters(coordinator, brands=["mir", "kuka", "generic"])
        for brand, adapter in adapters.items():
            state = adapter.map_vendor_state({"robot_id": f"{brand}-001"})
            assert isinstance(state, FleetState), f"{brand} adapter failed"
            assert state.robot_id == f"{brand}-001"
