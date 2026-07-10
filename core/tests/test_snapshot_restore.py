"""Tests for coordinator snapshot/restore — state persistence."""

import json
from unittest.mock import MagicMock

import pytest

from core.adapter.fleet_adapter import FleetAdapter
from core.coordinator import RobotPlatformCoordinator
from core.infra.state_store import RedisStateStore
from core.messages import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    HealthStatus,
    Pose,
    RobotMode,
    SensorHealth,
    TaskAssignment,
)
from core.orders import Order, OrderStatus
from core.scheduling.task_allocator import Task


def _make_robot(robot_id="R1", mode=RobotMode.IDLE, battery=80.0):
    return FleetState(
        robot_id=robot_id,
        boot_id="boot-001",
        pose=Pose(x=1.0, y=2.0, theta=0.5, last_node_id="A"),
        battery_percent=battery,
        mode=mode,
        errors=[],
        sensor_health=SensorHealth(
            velocity_sensor=HealthStatus.HEALTHY,
            lidar=HealthStatus.DEGRADED,
            camera=HealthStatus.HEALTHY,
            time_sync=HealthStatus.HEALTHY,
        ),
        velocity=0.5,
        capability=CapabilityVector(
            payload_kg=50.0,
            max_speed=1.5,
            supported_models=["AMR"],
            action_primitives={ActionPrimitive.MOVE, ActionPrimitive.PICK},
            env=EnvConstraints(max_grade=0.1, floor_threshold=0.02),
            supports_reverse=True,
        ),
        degraded=False,
    )


@pytest.fixture
def redis_mock():
    return MagicMock()


@pytest.fixture
def redis_store(redis_mock):
    return RedisStateStore(redis_mock)


class TestSnapshot:
    def test_empty_coordinator_snapshot(self):
        coord = RobotPlatformCoordinator()
        snap = coord.snapshot()
        assert snap["robot_states"] == {}
        assert snap["active_assignments"] == {}
        assert snap["task_queue"] == []
        assert snap["order_plans"] == {}

    def test_snapshot_is_json_serializable(self):
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot()
        snap = coord.snapshot()
        raw = json.dumps(snap)
        decoded = json.loads(raw)
        assert "R1" in decoded["robot_states"]

    def test_snapshot_captures_robot_state(self):
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot(battery=42.5)
        snap = coord.snapshot()
        rs = snap["robot_states"]["R1"]
        assert rs["robot_id"] == "R1"
        assert rs["battery_percent"] == 42.5
        assert rs["mode"] == int(RobotMode.IDLE)
        assert rs["pose"]["x"] == 1.0
        assert rs["sensor_health"]["lidar"] == int(HealthStatus.DEGRADED)
        assert 0 in rs["capability"]["action_primitives"]
        assert 1 in rs["capability"]["action_primitives"]
        assert rs["capability"]["supports_reverse"] is True

    def test_snapshot_captures_task_queue(self):
        coord = RobotPlatformCoordinator()
        coord._task_queue.append(Task(task_id="T1", start_lane="A", end_lane="B", priority=5))
        snap = coord.snapshot()
        assert len(snap["task_queue"]) == 1
        assert snap["task_queue"][0]["task_id"] == "T1"

    def test_snapshot_captures_order_plan(self):
        coord = RobotPlatformCoordinator()
        order = Order(order_id="O1", origin_lane="A", destination_lane="B")
        plan = coord.sequencer.plan(order)
        coord._order_plans["O1"] = plan
        snap = coord.snapshot()
        assert "O1" in snap["order_plans"]
        assert snap["order_plans"]["O1"]["order"]["order_id"] == "O1"
        assert snap["order_plans"]["O1"]["order"]["status"] == "PLANNED"

    def test_snapshot_captures_active_assignment(self):
        coord = RobotPlatformCoordinator()
        coord._active_assignments["R1"] = TaskAssignment(
            task_id="T1", path=["L_A_B", "L_B_C"], max_speed=1.2,
        )
        snap = coord.snapshot()
        assert snap["active_assignments"]["R1"]["task_id"] == "T1"
        assert snap["active_assignments"]["R1"]["path"] == ["L_A_B", "L_B_C"]

    def test_snapshot_captures_simple_maps(self):
        coord = RobotPlatformCoordinator()
        coord._task_order["T1"] = "O1"
        coord._order_completion["O1"] = {"T1"}
        coord._task_retries["T1"] = 2
        coord._robot_lane["R1"] = "L_A_B"
        snap = coord.snapshot()
        assert snap["task_order"] == {"T1": "O1"}
        assert snap["order_completion"] == {"O1": ["T1"]}
        assert snap["task_retries"] == {"T1": 2}
        assert snap["robot_lane"] == {"R1": "L_A_B"}


class TestRestore:
    def test_restore_empty_snapshot(self):
        coord = RobotPlatformCoordinator()
        coord.restore({})
        assert len(coord._robot_states) == 0
        assert len(coord._task_queue) == 0

    def test_restore_robot_state(self):
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot()
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert "R1" in coord2._robot_states
        rs = coord2._robot_states["R1"]
        assert rs.robot_id == "R1"
        assert rs.battery_percent == 80.0
        assert rs.mode == RobotMode.IDLE
        assert rs.pose.x == 1.0
        assert rs.sensor_health.lidar == HealthStatus.DEGRADED
        assert ActionPrimitive.PICK in rs.capability.action_primitives
        assert rs.capability.supports_reverse is True

    def test_restore_preserves_fleet_state_version(self):
        """FleetState.version must survive snapshot-restore round-trip."""
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot()
        coord._robot_states["R1"].version = "5.1"
        snap = coord.snapshot()
        assert snap["robot_states"]["R1"]["version"] == "5.1"

        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert coord2._robot_states["R1"].version == "5.1"

    def test_snapshot_captures_robot_brands(self):
        coord = RobotPlatformCoordinator()
        coord.register_adapter(FleetAdapter(brand="mir"))
        coord._robot_states["R1"] = _make_robot()
        coord._robot_adapter["R1"] = coord._adapters["mir"]
        snap = coord.snapshot()
        assert snap["robot_brands"] == {"R1": "mir"}

    def test_restore_relinks_adapter(self):
        coord = RobotPlatformCoordinator()
        coord.register_adapter(FleetAdapter(brand="mir"))
        coord._robot_states["R1"] = _make_robot()
        coord._robot_adapter["R1"] = coord._adapters["mir"]
        snap = coord.snapshot()

        coord2 = RobotPlatformCoordinator()
        coord2.register_adapter(FleetAdapter(brand="mir"))
        coord2.restore(snap)
        assert "R1" in coord2._robot_adapter
        assert coord2._robot_adapter["R1"].brand == "mir"

    def test_restore_robot_state_without_registered_adapter(self):
        coord = RobotPlatformCoordinator()
        coord.register_adapter(FleetAdapter(brand="mir"))
        coord._robot_states["R1"] = _make_robot()
        coord._robot_adapter["R1"] = coord._adapters["mir"]
        snap = coord.snapshot()

        coord2 = RobotPlatformCoordinator()
        # no mir adapter registered
        coord2.restore(snap)
        assert "R1" in coord2._robot_states
        assert "R1" not in coord2._robot_adapter

    def test_restore_task_queue(self):
        coord = RobotPlatformCoordinator()
        coord._task_queue.append(Task(task_id="T1", start_lane="A", end_lane="B"))
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert len(coord2._task_queue) == 1
        assert coord2._task_queue[0].task_id == "T1"

    def test_restore_order_plan(self):
        coord = RobotPlatformCoordinator()
        order = Order(order_id="O1", origin_lane="A", destination_lane="B")
        plan = coord.sequencer.plan(order)
        coord._order_plans["O1"] = plan
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert "O1" in coord2._order_plans
        assert coord2._order_plans["O1"].order.order_id == "O1"
        assert coord2._order_plans["O1"].order.status == OrderStatus.PLANNED

    def test_restore_active_assignment(self):
        coord = RobotPlatformCoordinator()
        coord._active_assignments["R1"] = TaskAssignment(
            task_id="T1", path=["L1", "L2"], max_speed=1.0,
        )
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert "R1" in coord2._active_assignments
        assert coord2._active_assignments["R1"].task_id == "T1"
        assert coord2._active_assignments["R1"].path == ["L1", "L2"]
        assert coord2._active_assignments["R1"].version == "5.0"

    def test_restore_active_assignment_preserves_custom_version(self):
        coord = RobotPlatformCoordinator()
        coord._active_assignments["R1"] = TaskAssignment(
            task_id="T1", path=["L1"], max_speed=1.0, version="5.1",
        )
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert coord2._active_assignments["R1"].version == "5.1"

    def test_restore_simple_maps(self):
        coord = RobotPlatformCoordinator()
        coord._task_order["T1"] = "O1"
        coord._order_completion["O1"] = {"T1"}
        coord._task_retries["T1"] = 3
        coord._robot_lane["R1"] = "L1"
        snap = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap)
        assert coord2._task_order == {"T1": "O1"}
        assert coord2._order_completion == {"O1": {"T1"}}
        assert coord2._task_retries == {"T1": 3}
        assert coord2._robot_lane == {"R1": "L1"}


class TestRoundTrip:
    def test_snapshot_restore_snapshot_equivalence(self):
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot()
        coord._robot_states["R2"] = _make_robot("R2", mode=RobotMode.CHARGING, battery=15.0)
        coord._task_queue.append(Task(task_id="T1", start_lane="A", end_lane="B", priority=5))
        coord._active_assignments["R1"] = TaskAssignment(task_id="T1", path=["L1"], max_speed=1.0)
        coord._task_order["T1"] = "O1"
        coord._robot_lane["R1"] = "L1"

        snap1 = coord.snapshot()
        coord2 = RobotPlatformCoordinator()
        coord2.restore(snap1)
        snap2 = coord2.snapshot()

        assert snap1["robot_states"].keys() == snap2["robot_states"].keys()
        assert snap1["task_queue"] == snap2["task_queue"]
        assert snap1["active_assignments"] == snap2["active_assignments"]
        assert snap1["task_order"] == snap2["task_order"]
        assert snap1["robot_lane"] == snap2["robot_lane"]

    def test_json_roundtrip(self):
        coord = RobotPlatformCoordinator()
        coord._robot_states["R1"] = _make_robot()
        snap = coord.snapshot()
        raw = json.dumps(snap)
        decoded = json.loads(raw)
        coord2 = RobotPlatformCoordinator()
        coord2.restore(decoded)
        assert "R1" in coord2._robot_states
        assert coord2._robot_states["R1"].battery_percent == 80.0


class TestRedisStateStore:
    def test_set_get(self, redis_mock, redis_store):
        redis_mock.get.return_value = b'{"key": "value"}'
        assert redis_store.get("k") == {"key": "value"}

    def test_set_with_ttl(self, redis_mock, redis_store):
        redis_store.set("k", "v", ttl=60)
        redis_mock.setex.assert_called_once()

    def test_set_without_ttl(self, redis_mock, redis_store):
        redis_store.set("k", "v")
        redis_mock.set.assert_called_once()

    def test_delete(self, redis_mock, redis_store):
        redis_store.delete("k")
        redis_mock.delete.assert_called_once_with("k")

    def test_exists(self, redis_mock, redis_store):
        redis_mock.exists.return_value = 1
        assert redis_store.exists("k") is True

    def test_get_none(self, redis_mock, redis_store):
        redis_mock.get.return_value = None
        assert redis_store.get("missing") is None
