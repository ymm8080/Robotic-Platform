"""Unit tests for traffic_coordinator_v5.simulator.robot."""

from __future__ import annotations

import pytest

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.robot import RobotConfig, SimRobotMode, SimulatedRobot


@pytest.fixture
def lane_graph():
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
    fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
    return LaneGraph(fmap)


@pytest.fixture
def robot(lane_graph):
    return SimulatedRobot(
        robot_id="R-001",
        brand="generic",
        lane_graph=lane_graph,
        current_lane_id="L_A_B",
        battery_percent=80.0,
        config=RobotConfig(max_speed=1.0, battery_drain_per_metre=0.5),
    )


class TestSimulatedRobotBasics:
    def test_initial_state(self, robot):
        assert robot.robot_id == "R-001"
        assert robot.mode == SimRobotMode.IDLE
        assert robot.velocity == 0.0
        assert robot.battery_percent == 80.0

    def test_default_lane_when_none_specified(self, lane_graph):
        robot = SimulatedRobot(
            robot_id="R-002",
            brand="generic",
            lane_graph=lane_graph,
        )
        assert robot.current_lane_id == "L_A_B"

    def test_assign_order_enters_tasking(self, robot):
        order = {
            "orderId": "o1",
            "nodes": [
                {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
                {"nodeId": "L_B_C", "sequenceId": 1, "released": True},
            ],
        }
        robot.assign_order(order)
        assert robot.mode == SimRobotMode.TASKING
        assert robot.path == ["L_A_B", "L_B_C"]

    def test_empty_order_is_ignored(self, robot):
        robot.assign_order({})
        assert robot.mode == SimRobotMode.IDLE
        assert robot.path == []

    def test_tick_moves_robot_and_drains_battery(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [
                    {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
                ],
            }
        )
        reached = robot.tick(1.0)
        assert len(reached) == 0
        assert robot.velocity == 1.0
        assert robot.battery_percent < 80.0

    def test_tick_reaches_end_of_lane(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [
                    {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
                    {"nodeId": "L_B_C", "sequenceId": 1, "released": True},
                ],
            }
        )
        reached = robot.tick(10.0)
        assert "L_A_B" in reached
        assert robot.current_lane_id == "L_B_C"

    def test_final_lane_reached_goes_idle(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [
                    {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
                ],
            }
        )
        robot.tick(10.0)
        assert robot.mode == SimRobotMode.IDLE
        assert robot.velocity == 0.0

    def test_inject_error_stops_robot(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
            }
        )
        robot.inject_error("ERR_SENSOR_DEGRADED")
        assert robot.mode == SimRobotMode.ERROR
        assert "ERR_SENSOR_DEGRADED" in robot.errors
        reached = robot.tick(5.0)
        assert reached == []
        assert robot.velocity == 0.0

    def test_clear_errors_returns_to_idle(self, robot):
        robot.inject_error("ERR_SENSOR_DEGRADED")
        robot.clear_errors()
        assert robot.mode == SimRobotMode.IDLE
        assert robot.errors == []

    def test_hold_and_resume(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
            }
        )
        robot.hold()
        robot.tick(5.0)
        assert robot.velocity == 0.0
        robot.resume()
        robot.tick(5.0)
        assert robot.velocity == 1.0

    def test_speed_cap_clamps_velocity(self, robot):
        robot.assign_order(
            {
                "orderId": "o1",
                "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
            }
        )
        robot.set_speed_cap(0.3)
        robot.tick(1.0)
        assert robot.velocity == pytest.approx(0.3)

    def test_state_payload_has_required_keys(self, robot):
        payload = robot.state_payload()
        assert payload["serialNumber"] == "R-001"
        assert payload["manufacturer"] == "generic"
        assert "batteryPercent" in payload
        assert "sensorHealth" in payload
        assert "mode" in payload

    def test_connection_payload(self, robot):
        payload = robot.connection_payload()
        assert payload["connectionState"] == "ONLINE"
        assert payload["bootId"] == robot.boot_id

    def test_charging_mode_raises_battery(self):
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_CHG", "A", "B", length=5.0, charger=True))
        graph = LaneGraph(fmap)
        robot = SimulatedRobot(
            robot_id="R-003",
            brand="generic",
            lane_graph=graph,
            current_lane_id="L_CHG",
            battery_percent=15.0,
            config=RobotConfig(battery_charge_per_second=10.0),
        )
        robot.mode = SimRobotMode.CHARGING
        robot.tick(2.0)
        assert robot.battery_percent == pytest.approx(35.0)
        assert robot.mode == SimRobotMode.CHARGING

    def test_idle_on_charger_with_low_battery_enters_charging(self):
        fmap = FixedLaneMap()
        fmap.add_lane(Lane("L_CHG", "A", "B", length=5.0, charger=True))
        graph = LaneGraph(fmap)
        robot = SimulatedRobot(
            robot_id="R-004",
            brand="generic",
            lane_graph=graph,
            current_lane_id="L_CHG",
            battery_percent=15.0,
            config=RobotConfig(charger_threshold=20.0),
        )
        robot.tick(0.1)
        assert robot.mode == SimRobotMode.CHARGING
