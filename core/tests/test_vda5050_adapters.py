"""Tests for VDA5050 fleet adapter and brand adapter factories.

The adapter layer uses duck typing — strategy objects are passed at
construction time.  The tests use a mock strategy so they do NOT depend
on the sap-bridge package.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter
from core.messages import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    Pose,
    RobotMode,
)


# ── Mock strategy (simulates a sap-bridge BaseStrategy) ────────────


@dataclass
class MockBattery:
    percent: float = 85.0


@dataclass
class MockRobotState:
    status: str = "IDLE"
    battery: MockBattery = field(default_factory=MockBattery)
    position: dict = field(default_factory=lambda: {
        "x": 1.0, "y": 2.0, "theta": 0.5,
        "lastNodeId": "A", "positionInitialized": True,
    })
    errors: list = field(default_factory=list)
    raw: dict | None = None


class MockStrategy:
    """A duck-typed strategy that satisfies the _StrategyLike protocol."""

    brand = "mock_brand"

    def handle_state(self, state: dict) -> MockRobotState:
        return MockRobotState(
            status=state.get("status", "IDLE"),
            position={
                "x": float(state.get("x", 0)),
                "y": float(state.get("y", 0)),
                "theta": float(state.get("theta", 0)),
                "lastNodeId": state.get("lastNodeId", ""),
                "positionInitialized": True,
            },
            raw=state,
        )

    def to_fleet_state(self, robot_state: MockRobotState) -> FleetState:
        pos = robot_state.position
        return FleetState(
            robot_id=robot_state.raw.get("serialNumber", "mock-001") if robot_state.raw else "mock-001",
            boot_id="",
            pose=Pose(
                x=pos["x"], y=pos["y"], theta=pos["theta"],
                last_node_id=pos.get("lastNodeId", ""),
                position_initialized=pos.get("positionInitialized", True),
            ),
            battery_percent=robot_state.battery.percent,
            mode=RobotMode.IDLE,
            velocity=0.0,
        )

    def to_capability_vector(self) -> CapabilityVector:
        return CapabilityVector(
            payload_kg=500.0,
            max_speed=1.5,
            supported_models=[],
            action_primitives={ActionPrimitive.MOVE, ActionPrimitive.DOCK},
            env=EnvConstraints(max_grade=0.05, floor_threshold=0.01),
            supports_reverse=True,
        )

    def extract_errors(self, state: dict) -> list[dict]:
        errors = state.get("errors", [])
        if not isinstance(errors, list):
            return []
        return errors

    def dispatch(self, order: dict) -> Any:
        return {"success": True, "order_id": order.get("orderId", "")}


# ── Tests ─────────────────────────────────────────────────────────


class TestVDA5050FleetAdapter:
    """Tests for the VDA5050FleetAdapter wrapping layer."""

    def test_construction(self):
        """Adapter is created with a strategy and inherits FleetAdapter."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        assert adapter.brand == "mock_brand"
        assert isinstance(adapter, FleetAdapter)
        assert adapter.strategy is strategy

    def test_map_vendor_state_delegates_to_strategy(self):
        """map_vendor_state calls strategy.handle_state then to_fleet_state."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        raw = {"serialNumber": "mock-001", "x": 3.0, "y": 4.0, "theta": 1.57}
        state = adapter.map_vendor_state(raw)
        assert isinstance(state, FleetState)
        assert state.robot_id == "mock-001"
        assert state.pose.x == 3.0
        assert state.pose.y == 4.0
        assert state.pose.theta == 1.57
        assert state.mode == RobotMode.IDLE

    def test_map_vendor_state_handles_minimal_payload(self):
        """map_vendor_state works with a minimal raw dict."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        state = adapter.map_vendor_state({})
        assert state.robot_id == "mock-001"
        assert state.pose.x == 0.0

    def test_map_vendor_errors_delegates(self):
        """map_vendor_errors calls strategy.extract_errors and formats output."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        result = adapter.map_vendor_errors([
            {"errorType": "NAVIGATION", "errorLevel": "WARNING", "errorDescription": "lost"},
        ])
        assert len(result) == 1
        assert "NAVIGATION" in result[0]
        assert "lost" in result[0]

    def test_map_vendor_errors_empty(self):
        """Empty errors produce empty output."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        assert adapter.map_vendor_errors([]) == []

    def test_ingest_native_state_produces_events(self):
        """ingest_native_state (from FleetAdapter base) returns state + events."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        raw = {"serialNumber": "mock-001", "x": 1.0, "y": 0.0}
        state, events = adapter.ingest_native_state(raw, now=100.0)
        assert state.robot_id == "mock-001"
        assert isinstance(events, list)

    def test_ingest_state_twice_detects_boot_drift(self):
        """Second ingest with different boot_id triggers BOOT_TAKEOVER."""
        from copy import deepcopy

        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        raw = {"serialNumber": "mock-001", "x": 0.0, "y": 0.0}
        # First ingest — stores state with empty boot_id in _last_state
        state1, _ = adapter.ingest_native_state(raw, now=100.0)
        # Second ingest with a different boot_id (use deepcopy to get a
        # new object, since _last_state holds a reference to the old one)
        state2 = deepcopy(state1)
        state2.boot_id = "new-boot-456"
        events = adapter.ingest_state(state2, now=110.0)
        assert any("BOOT_TAKEOVER" in e for e in events), f"events={events}"

    def test_command_sequencing(self):
        """Each command gets a unique sequence number."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        cmd1 = adapter.request_hold("mock-001", "test1", now=0.0)
        cmd2 = adapter.request_hold("mock-001", "test2", now=0.0)
        assert cmd2.seq == cmd1.seq + 1

    def test_speed_cap_command(self):
        """request_speed_cap generates a SPEED_CAP command."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        cmd = adapter.request_speed_cap("mock-001", 0.5, "test", now=0.0)
        assert cmd.action == "SPEED_CAP"
        assert cmd.metres == 0.5

    def test_fallback_with_reverse_support(self):
        """Robots with reverse support get RETREAT; without get HOLD."""
        strategy = MockStrategy()
        adapter = VDA5050FleetAdapter(strategy=strategy)
        # Register a robot with reverse support
        state = FleetState(robot_id="mock-001", boot_id="b1", battery_percent=85.0,
                           pose=Pose(x=0, y=0, theta=0),
                           capability=CapabilityVector(supports_reverse=True))
        adapter._last_state["mock-001"] = state
        adapter._registry["mock-001"] = type("Reg", (), {"supports_reverse": True, "active_path": [], "next_waypoint_idx": 0})()
        cmd = adapter.request_fallback("mock-001", "test", now=0.0)
        assert cmd.action == "RETREAT"

        # Robot without reverse support
        adapter._registry["mock-002"] = type("Reg", (), {"supports_reverse": False, "active_path": [], "next_waypoint_idx": 0})()
        cmd2 = adapter.request_fallback("mock-002", "test", now=0.0)
        assert cmd2.action == "HOLD"


class TestBrandAdapterFactories:
    """Test that brand adapter factories can be imported and produce adapters."""

    def test_brand_factories_dict(self):
        """BRAND_FACTORIES maps all 6 brand names to callables."""
        from core.adapter.brands import BRAND_FACTORIES

        assert set(BRAND_FACTORIES.keys()) == {
            "mir", "otto", "kuka", "geekplus", "hairobotics", "quicktron",
        }
        for brand, factory in BRAND_FACTORIES.items():
            assert callable(factory), f"{brand} factory is not callable"

    def test_create_mir_adapter(self):
        """create_mir_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_mir_adapter

        adapter = create_mir_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "MiR"

    def test_create_otto_adapter(self):
        """create_otto_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_otto_adapter

        adapter = create_otto_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "OTTO"

    def test_create_kuka_adapter(self):
        """create_kuka_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_kuka_adapter

        adapter = create_kuka_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "KUKA"

    def test_create_geekplus_adapter(self):
        """create_geekplus_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_geekplus_adapter

        adapter = create_geekplus_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "GeekPlus"

    def test_create_hairobotics_adapter(self):
        """create_hairobotics_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_hairobotics_adapter

        adapter = create_hairobotics_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "HaiRobotics"

    def test_create_quicktron_adapter(self):
        """create_quicktron_adapter produces a VDA5050FleetAdapter."""
        from core.adapter.brands import create_quicktron_adapter

        adapter = create_quicktron_adapter()
        assert isinstance(adapter, VDA5050FleetAdapter)
        assert adapter.brand == "Quicktron"

    def test_all_adapters_can_map_state(self):
        """All 6 brand adapters can map a minimal vendor state."""
        from core.adapter.brands import BRAND_FACTORIES

        raw = {"serialNumber": "test-001", "x": 1.0, "y": 2.0, "theta": 0.0}
        for brand, factory in BRAND_FACTORIES.items():
            adapter = factory()
            state = adapter.map_vendor_state(raw)
            assert isinstance(state, FleetState), f"{brand} adapter did not return FleetState"
            assert state.robot_id, f"{brand} adapter: robot_id is empty"


class TestStrategyToFleetState:
    """Test the to_fleet_state method on a real sap-bridge strategy.

    These tests require the sap-bridge package to be importable.
    """

    @pytest.mark.skipif(
        "sap-bridge" not in "".join(sys.path),
        reason="sap-bridge not on sys.path; add project root to PYTHONPATH",
    )
    def test_mir_strategy_to_fleet_state_idle(self):
        """MiR strategy converts an IDLE RobotState to FleetState."""
        import importlib
        mod = importlib.import_module("sap-bridge.strategies.mir")
        strategy = mod.MirStrategy()

        raw = {
            "serialNumber": "mir-001",
            "x": 1.5, "y": 2.5, "theta": 0.0,
            "positionInitialized": True,
            "lastNodeId": "B",
        }
        robot_state = strategy.handle_state(raw)
        fleet_state = strategy.to_fleet_state(robot_state)
        assert fleet_state.robot_id == "mir-001"
        assert fleet_state.pose.x == 1.5
        assert fleet_state.mode == RobotMode.IDLE
        assert fleet_state.battery_percent == 0.0  # MiR raw has no battery in test

    @pytest.mark.skipif(
        "sap-bridge" not in "".join(sys.path),
        reason="sap-bridge not on sys.path",
    )
    def test_strategy_to_capability_vector_defaults(self):
        """to_capability_vector returns a valid CapabilityVector."""
        import importlib
        mod = importlib.import_module("sap-bridge.strategies.mir")
        strategy = mod.MirStrategy()
        cap = strategy.to_capability_vector()
        assert isinstance(cap, CapabilityVector)
        assert cap.max_speed > 0
        assert cap.payload_kg > 0
