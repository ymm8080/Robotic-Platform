"""Unit tests for traffic_coordinator_v5.simulator.fleet."""

from __future__ import annotations

import pytest

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from traffic_coordinator_v5.simulator.fleet import FleetSimulator
from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.robot import RobotConfig, SimRobotMode


@pytest.fixture
def lane_graph():
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
    fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
    return LaneGraph(fmap)


@pytest.fixture
def fleet(lane_graph):
    return FleetSimulator(lane_graph=lane_graph, brand="generic", publish_interval=0.5)


class TestFleetSimulator:
    def test_add_robot(self, fleet):
        robot = fleet.add_robot("R-001")
        assert robot.robot_id == "R-001"
        assert "R-001" in fleet.robot_ids

    def test_tick_once_advances_all_robots(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        fleet.add_robot("R-002", battery=80.0)
        for robot in fleet._robots.values():
            robot.assign_order({
                "orderId": "o1",
                "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
            })
        reached = fleet.tick_once(1.0)
        assert "R-001" in reached
        assert "R-002" in reached
        for robot in fleet._robots.values():
            assert robot.velocity == 1.0

    def test_route_order(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        fleet._route_order("R-001", {
            "orderId": "o1",
            "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
        })
        robot = fleet.get_robot("R-001")
        assert robot is not None
        assert robot.mode == SimRobotMode.TASKING

    def test_route_order_unknown_robot_logs(self, fleet, caplog):
        with caplog.at_level("WARNING"):
            fleet._route_order("R-999", {"orderId": "o1"})
        assert "unknown robot" in caplog.text

    def test_instant_action_hold_and_resume(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        robot = fleet.get_robot("R-001")
        robot.assign_order({
            "orderId": "o1",
            "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
        })
        fleet._route_instant_actions("R-001", {
            "actions": [{"actionType": "stopPause", "actionId": "h1"}],
        })
        fleet.tick_once(1.0)
        assert robot.velocity == 0.0

        fleet._route_instant_actions("R-001", {
            "actions": [{"actionType": "resume", "actionId": "r1"}],
        })
        fleet.tick_once(1.0)
        assert robot.velocity == 1.0

    def test_instant_action_speed_cap(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        robot = fleet.get_robot("R-001")
        robot.assign_order({
            "orderId": "o1",
            "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
        })
        fleet._route_instant_actions("R-001", {
            "actions": [{
                "actionType": "instantVelocity",
                "actionId": "sc1",
                "actionParameters": [{"key": "max_speed", "value": 0.3}],
            }],
        })
        fleet.tick_once(1.0)
        assert robot.velocity == pytest.approx(0.3)

    def test_instant_action_cancel_order(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        robot = fleet.get_robot("R-001")
        robot.assign_order({
            "orderId": "o1",
            "nodes": [{"nodeId": "L_A_B", "sequenceId": 0, "released": True}],
        })
        fleet._route_instant_actions("R-001", {
            "actions": [{"actionType": "cancelOrder", "actionId": "c1"}],
        })
        assert robot.mode == SimRobotMode.IDLE
        assert robot.path == []

    def test_publish_all_states_without_mqtt_does_not_crash(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        fleet.publish_all_states()

    def test_start_stop_real_time_loop(self, fleet):
        fleet.add_robot("R-001", battery=80.0)
        fleet.start()
        assert fleet._running is True
        fleet.stop()
        assert fleet._running is False
