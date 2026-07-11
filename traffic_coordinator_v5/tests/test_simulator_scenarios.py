"""Integration scenario tests for the VDA5050 simulator + v5 coordinator.

These tests drive ``FleetSimulator.tick_once`` and
``RobotPlatformCoordinator.tick`` in lockstep without a real MQTT broker.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.config import CoreConfig, WormConfig
from core.coordinator import RobotPlatformCoordinator
from core.messages import ActionPrimitive
from core.orders import Order
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.traffic_light_controller import LightPhase
from traffic_coordinator_v5.bootstrap import _create_generic_adapter
from traffic_coordinator_v5.simulator.fleet import FleetSimulator
from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.robot import RobotConfig, SimulatedRobot, SimRobotMode


class CoordinatorHarness:
    """Offline harness that wires a FleetSimulator to a RobotPlatformCoordinator."""

    def __init__(self, fmap: FixedLaneMap, brand: str = "generic", lane_positions: dict[str, tuple[float, float]] | None = None) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        worm_cfg = WormConfig(sink_dir=self._tmp.name)
        config = CoreConfig(worm=worm_cfg)
        self.coordinator = RobotPlatformCoordinator(config=config, fmap=fmap)
        self.adapter = _create_generic_adapter(brand)
        self.coordinator.register_adapter(self.adapter)
        self.fleet = FleetSimulator(
            lane_graph=LaneGraph(fmap, node_positions=lane_positions),
            brand=brand,
            mqtt_client=None,
            publish_interval=0.5,
        )
        self.now = 0.0
        self.dt = 0.5
        self.skip_ingestion: set[str] = set()

    def cleanup(self) -> None:
        """Explicit cleanup for temporary resources. Safe to call multiple times."""
        try:
            if hasattr(self, "_tmp"):
                self._tmp.cleanup()
        except Exception:
            pass

    def __del__(self):
        self.cleanup()

    def add_robot(
        self,
        robot_id: str,
        start_lane: str,
        battery: float = 80.0,
        max_speed: float = 1.0,
    ) -> SimulatedRobot:
        return self.fleet.add_robot(
            robot_id=robot_id,
            start_lane=start_lane,
            battery=battery,
            config=RobotConfig(max_speed=max_speed),
        )

    def submit_order(self, order_id: str, origin_lane: str, destination_lane: str) -> None:
        order = Order(
            order_id=order_id,
            origin_lane=origin_lane,
            destination_lane=destination_lane,
            actions=[ActionPrimitive.MOVE],
        )
        self.coordinator.submit_order(order)

    def tick(self, count: int = 1):
        last_result = None
        for _ in range(count):
            self.now += self.dt
            reached_by_robot = self.fleet.tick_once(self.dt)
            self._ingest_states()
            for rid, lanes in reached_by_robot.items():
                for lane in lanes:
                    self.coordinator.report_progress(rid, lane, self.now)
            result = self.coordinator.tick(self.now)
            self._apply_result(result)
            last_result = result
        return last_result

    def _ingest_states(self) -> None:
        for rid, robot in self.fleet._robots.items():
            if rid in self.skip_ingestion:
                continue
            payload = robot.state_payload()
            self.coordinator.ingest_uplink(self.fleet._brand, payload, self.now)

    def _apply_result(self, result) -> None:
        held_ids: set[str] = set()
        for cmd in result.commands:
            robot = self.fleet.get_robot(cmd.robot_id)
            if robot is None:
                continue
            if cmd.action == "HOLD":
                robot.hold(cmd.reason)
                held_ids.add(cmd.robot_id)
            elif cmd.action == "RETREAT":
                robot.hold(f"retreat:{cmd.reason}")
                held_ids.add(cmd.robot_id)
            elif cmd.action == "SPEED_CAP":
                robot.set_speed_cap(cmd.metres)

        # Coordinator sends HOLD every tick while the condition persists.
        # Absence of HOLD in the current tick means the robot is free to move.
        # This mirrors real robot behaviour: hold when told, resume when not.
        for robot_id, robot in self.fleet._robots.items():
            if robot_id not in held_ids and robot.held:
                robot.resume()

        for robot_id, assignment in result.assignments:
            order = {
                "orderId": assignment.task_id,
                "nodes": [
                    {"nodeId": lid, "sequenceId": i, "released": True}
                    for i, lid in enumerate(assignment.path)
                ],
            }
            self.fleet._route_order(robot_id, order)

    def robot_state(self, robot_id: str):
        return self.coordinator._robot_states.get(robot_id)


@pytest.fixture
def demo_map():
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
    fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
    return fmap


class TestScenarios:
    def test_basic_order_completion(self, demo_map):
        """One robot moves from A to C via B and the coordinator sees completion."""
        harness = CoordinatorHarness(demo_map)
        harness.add_robot("R-001", "L_A_B")
        harness.submit_order("o1", "L_A_B", "L_B_C")
        harness.tick(60)

        state = harness.robot_state("R-001")
        assert state is not None
        assert state.mode.name == "IDLE"
        assert len(harness.coordinator._active_assignments) == 0

    def test_intersection_conflict(self):
        """3 robots converge at a single intersection; traffic light gates entry."""
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_A_B", "A", "B", length=2.0, max_speed=1.5, intersection_id="X1", direction=0))
        fmap.add_lane(Lane("L_X_B", "X", "B", length=20.0, max_speed=1.5, intersection_id="X1", direction=0))
        fmap.add_lane(Lane("L_Y_B", "Y", "B", length=30.0, max_speed=1.5, intersection_id="X1", direction=1))
        fmap.add_lane(Lane("L_B_Z1", "B", "Z1", length=20.0, max_speed=1.5))
        fmap.add_lane(Lane("L_B_Z2", "B", "Z2", length=20.0, max_speed=1.5))
        fmap.add_lane(Lane("L_B_Z3", "B", "Z3", length=20.0, max_speed=1.5))

        positions = {
            "A": (0.0, 0.0),
            "X": (0.0, 30.0),
            "Y": (55.0, 30.0),
            "B": (10.0, 0.0),
            "Z1": (30.0, 0.0),
            "Z2": (30.0, 10.0),
            "Z3": (30.0, -10.0),
        }
        harness = CoordinatorHarness(fmap, lane_positions=positions)
        harness.coordinator.register_intersection("X1")
        # Start with direction 0 green so the two direction-0 robots clear first.
        it = harness.coordinator.traffic.get("X1")
        it.phase = LightPhase.GREEN
        it.current_direction = 0
        it.phase_started_at = 0.0

        harness.add_robot("R-001", "L_A_B")
        harness.add_robot("R-002", "L_X_B")
        harness.add_robot("R-003", "L_Y_B")
        harness.submit_order("o1", "L_A_B", "L_B_Z1")
        harness.submit_order("o2", "L_X_B", "L_B_Z2")
        harness.submit_order("o3", "L_Y_B", "L_B_Z3")

        collision_holds = 0
        intersection_holds = 0
        for _ in range(240):
            result = harness.tick(1)
            if result is not None:
                collision_holds += sum(1 for e in result.events if e.startswith("COLLISION_HOLD"))
                intersection_holds += sum(1 for e in result.events if e.startswith("INTERSECTION_HOLD"))

        # All robots should eventually be IDLE (no active assignments left).
        assert all(
            r.mode == SimRobotMode.IDLE for r in harness.fleet._robots.values()
        )
        assert len(harness.coordinator._active_assignments) == 0
        assert collision_holds == 0
        # At least one robot was held at the red intersection.
        assert intersection_holds > 0

    def test_charger_stampede(self):
        """5 low-battery robots, 2 charger bays: only 2 get charge tasks."""
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_A_B", "A", "B", length=5.0, max_speed=1.5))
        fmap.add_lane(Lane("L_B_CHG1", "B", "CHG1", length=5.0, max_speed=1.5, charger=True))
        fmap.add_lane(Lane("L_B_CHG2", "B", "CHG2", length=5.0, max_speed=1.5, charger=True))

        harness = CoordinatorHarness(fmap)
        harness.coordinator.register_charger("CHG1")
        harness.coordinator.register_charger("CHG2")
        for i in range(1, 6):
            harness.add_robot(f"R-{i:03d}", "L_A_B", battery=21.0, max_speed=0.5)
            harness.submit_order(f"o{i}", "L_A_B", "L_B_CHG1")

        charge_tasks_created = 0
        min_battery = 100.0
        for _ in range(200):
            harness.tick(1)
            queue_ids = [t.task_id for t in harness.coordinator._task_queue]
            charge_tasks_created = max(
                charge_tasks_created,
                sum(1 for tid in queue_ids if tid.startswith("charge:")),
            )
            for robot in harness.fleet._robots.values():
                min_battery = min(min_battery, robot.battery_percent)

        # Only 2 charge tasks can exist at once (one per bay).
        assert charge_tasks_created <= 2
        assert min_battery > 0.0

    def test_fault_recovery(self, demo_map):
        """Robot faults mid-task; after manual recover it returns to IDLE."""
        harness = CoordinatorHarness(demo_map)
        harness.add_robot("R-001", "L_A_B")
        harness.submit_order("o1", "L_A_B", "L_B_C")

        # Tick until the robot has progressed onto the path.
        for _ in range(5):
            harness.tick(1)
            if harness.coordinator._active_assignments:
                break

        robot = harness.fleet.get_robot("R-001")
        robot.inject_error("ERR_SENSOR_DEGRADED")
        # Stop reporting so the coordinator's failover marks the robot degraded/offline
        # and requeues the active assignment.
        harness.skip_ingestion.add("R-001")
        harness.tick(10)
        harness.skip_ingestion.discard("R-001")
        # Ingest one tick so the coordinator observes the degraded/error state.
        harness.tick(1)

        assert robot.mode == SimRobotMode.ERROR

        # After fault, the robot should no longer have an active assignment.
        assert "R-001" not in harness.coordinator._active_assignments

        harness.coordinator.manual_recover("R-001", harness.now)
        robot.clear_errors()
        harness.tick(10)

        # The robot should be out of ERROR/DEGRADED and the task should have
        # been requeued or reassigned to it.
        state = harness.robot_state("R-001")
        assert state is not None
        assert not state.degraded
        assert state.mode.name != "ERROR"
        assert any(t.task_id == "o1-0" for t in harness.coordinator._task_queue) or \
            any(a.task_id == "o1-0" for a in harness.coordinator._active_assignments.values())

    def test_safe_distance(self):
        """Following robot is SPEED_CAP'd by the coordinator before colliding."""
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_A_B", "A", "B", length=50.0, max_speed=2.0))
        fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=2.0))

        harness = CoordinatorHarness(fmap)
        r1 = harness.add_robot("R-001", "L_A_B", max_speed=1.0)
        r2 = harness.add_robot("R-002", "L_A_B", max_speed=0.5)

        # Drive the robots manually so the initial offset is not reset by a
        # coordinator-assigned order.
        path_order = {
            "orderId": "o1",
            "nodes": [
                {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
                {"nodeId": "L_B_C", "sequenceId": 1, "released": True},
            ],
        }
        r1.assign_order(path_order)
        r2.assign_order(path_order)
        # Place R-002 5 metres ahead of R-001 on the same lane.
        r2.distance_along_lane = 5.0

        speed_cap_seen = False
        collision_holds = 0
        for _ in range(80):
            result = harness.tick(1)
            if result is not None:
                if any(cmd.action == "SPEED_CAP" for cmd in result.commands):
                    speed_cap_seen = True
                collision_holds += sum(1 for e in result.events if e.startswith("COLLISION_HOLD"))

        assert speed_cap_seen
        assert collision_holds == 0

    def test_deadlock_break(self):
        """Two robots face each other on a corridor; deadlock breaker fires."""
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5, intersection_id="X1", direction=0))
        fmap.add_lane(Lane("L_B_A", "B", "A", length=10.0, max_speed=1.5, intersection_id="X1", direction=1))

        harness = CoordinatorHarness(fmap)
        harness.coordinator.register_intersection("X1")
        r1 = harness.add_robot("R-001", "L_A_B")
        r2 = harness.add_robot("R-002", "L_B_A")

        harness.submit_order("o1", "L_A_B", "L_A_B")
        harness.submit_order("o2", "L_B_A", "L_B_A")

        # Let the coordinator assign orders, then place the robots close enough
        # that their footprints overlap and neither can pass.
        harness.tick(1)
        r1.distance_along_lane = 4.9
        r2.distance_along_lane = 4.9

        deadlock_breaks = 0
        for _ in range(80):
            result = harness.tick(1)
            if result is not None:
                deadlock_breaks += len(result.deadlocks)

        assert deadlock_breaks > 0
