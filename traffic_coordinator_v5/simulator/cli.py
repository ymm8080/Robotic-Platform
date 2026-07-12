"""Command-line interface for the VDA5050 mock robot simulator."""

from __future__ import annotations

import argparse
import logging
import random
import signal
import sys
import threading
import time

from core.platform.fixed_lane_map import FixedLaneMap
from traffic_coordinator_v5.simulator.fleet import FleetSimulator
from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.mqtt_client import MqttVDAClient
from traffic_coordinator_v5.simulator.robot import RobotConfig, SimulatedRobot

logger = logging.getLogger(__name__)

DEFAULT_MAP = "traffic_coordinator_v5/maps/facility_map.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traffic_coordinator_v5.simulator",
        description="VDA5050 mock robot simulator for the v5 traffic coordinator.",
    )
    parser.add_argument(
        "-n", "--count", type=int, default=1, help="Number of robots to simulate"
    )
    parser.add_argument(
        "-b", "--brand", type=str, default="generic", help="VDA5050 manufacturer segment"
    )
    parser.add_argument(
        "-p", "--serial-prefix", type=str, default="R", help="Robot id prefix"
    )
    parser.add_argument(
        "-m", "--map", type=str, default=DEFAULT_MAP, help="Lane graph YAML path"
    )
    parser.add_argument(
        "-B", "--broker", type=str, default="localhost", help="MQTT broker host"
    )
    parser.add_argument(
        "-P", "--port", type=int, default=1883, help="MQTT broker port"
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=0.5, help="State publish interval (seconds)"
    )
    parser.add_argument(
        "-s", "--speed", type=float, default=1.0, help="Default max speed (m/s)"
    )
    parser.add_argument(
        "--drain", type=float, default=0.5, help="Battery drain per metre moved"
    )
    parser.add_argument(
        "--charge", type=float, default=5.0, help="Battery charge per second while charging"
    )
    parser.add_argument(
        "--initial-battery", type=float, default=80.0, help="Starting battery %%"
    )
    parser.add_argument(
        "--start-node", type=str, default="", help="Initial node id (default: first node)"
    )
    parser.add_argument(
        "--fault-prob", type=float, default=0.0, help="Probability of injected fault per tick"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        choices=["intersection", "charger", "fault", "deadlock", "safe_distance"],
        help="Named scenario to run (overrides --count and --start-node)",
    )
    parser.add_argument(
        "--duration", type=float, default=60.0, help="Scenario duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Run without connecting to an MQTT broker"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    return parser


def _robot_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def _start_lane_for_node(lane_graph: LaneGraph, node_id: str) -> str | None:
    for lane in lane_graph.all_lanes():
        if lane.from_node == node_id:
            return lane.lane_id
    logger.warning("Node %s has no outgoing lanes, falling back to first lane", node_id)
    return lane_graph.first_lane()


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.scenario:
        return _run_scenario(args)

    lane_graph = LaneGraph.from_yaml(args.map)
    if not lane_graph.all_lanes():
        logger.error("Map %s contains no lanes; cannot start simulator", args.map)
        return 1

    config = RobotConfig(
        max_speed=args.speed,
        battery_drain_per_metre=args.drain,
        battery_charge_per_second=args.charge,
    )

    mqtt_client: MqttVDAClient | None = None
    if not args.offline:
        mqtt_client = MqttVDAClient(
            broker_host=args.broker,
            broker_port=args.port,
            brand=args.brand,
        )

    fleet = FleetSimulator(
        lane_graph=lane_graph,
        brand=args.brand,
        mqtt_client=mqtt_client,
        publish_interval=args.interval,
    )

    start_lane: str | None = None
    if args.start_node:
        start_lane = _start_lane_for_node(lane_graph, args.start_node)

    for i in range(args.count):
        fleet.add_robot(
            robot_id=_robot_id(args.serial_prefix, i + 1),
            start_lane=start_lane,
            battery=args.initial_battery,
            config=config,
        )

    # Publish initial connection messages before any tick.
    if mqtt_client is not None:
        mqtt_client.connect()
        for rid in fleet.robot_ids:
            mqtt_client.publish_connection(rid, "ONLINE")

    # Graceful shutdown on SIGINT/SIGTERM.
    shutdown_requested = False

    def _signal_handler(_signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("Shutdown requested")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    fleet.start()
    logger.info(
        "Simulator running: %d robot(s), brand=%s, broker=%s:%d",
        args.count,
        args.brand,
        args.broker if not args.offline else "offline",
        args.port,
    )

    try:
        while not shutdown_requested:
            time.sleep(0.1)
            if args.fault_prob > 0:
                for rid in fleet.robot_ids:
                    if random.random() < args.fault_prob:
                        if fleet.inject_fault(rid, "ERR_INJECTED_FAULT"):
                            logger.warning("Injected fault into %s", rid)
    finally:
        fleet.stop()
        logger.info("Simulator stopped")

    return 0


# ── Scenario runner ──────────────────────────────────────────────────────────


def _run_scenario(args: argparse.Namespace) -> int:
    """Run a named test scenario via ``FleetSimulator.load_scenario()``."""
    logger.info("Running scenario: %s (duration=%.1fs)", args.scenario, args.duration)

    # Build an empty lane graph that ``load_scenario()`` will populate.
    lane_graph = LaneGraph(FixedLaneMap())

    mqtt_client: MqttVDAClient | None = None
    if not args.offline:
        mqtt_client = MqttVDAClient(
            broker_host=args.broker,
            broker_port=args.port,
            brand=args.brand,
        )

    fleet = FleetSimulator(
        lane_graph=lane_graph,
        brand=args.brand,
        mqtt_client=mqtt_client,
        publish_interval=args.interval,
    )

    robot_ids = fleet.load_scenario(args.scenario)
    logger.info(
        "Scenario '%s' loaded: %d robot(s) — %s",
        args.scenario, len(robot_ids), ", ".join(robot_ids),
    )

    _assign_scenario_orders(fleet, args.scenario)

    # Publish initial connection messages before any tick.
    if mqtt_client is not None:
        mqtt_client.connect()
        for rid in fleet.robot_ids:
            mqtt_client.publish_connection(rid, "ONLINE")

    # Graceful shutdown on SIGINT/SIGTERM.
    shutdown_event = threading.Event()

    def _signal_handler(_signum: int, _frame: object) -> None:
        shutdown_event.set()
        logger.info("Scenario interrupted")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    fleet.start()
    logger.info(
        "Scenario %s started with %d robot(s)",
        args.scenario,
        len(fleet.robot_ids),
    )

    start_time = time.monotonic()
    fault_injected = False

    try:
        while not shutdown_event.is_set():
            elapsed = time.monotonic() - start_time
            remaining = args.duration - elapsed
            if remaining <= 0:
                break

            # Scenario-specific mid-run actions.
            if args.scenario == "fault" and not fault_injected and elapsed >= 3.0:
                robot = fleet.get_robot("R-001")
                if robot is not None:
                    robot.inject_error("ERR_SENSOR_DEGRADED")
                    logger.warning("Injected ERR_SENSOR_DEGRADED into R-001")
                    fault_injected = True

            shutdown_event.wait(min(0.1, remaining))
    finally:
        fleet.stop()

    _report_scenario_results(fleet, args.scenario)
    return 0


def _assign_scenario_orders(fleet: FleetSimulator, scenario: str) -> None:
    """Assign initial paths (VDA5050 orders) to robots per scenario."""
    if scenario == "intersection":
        _assign_order(fleet.get_robot("R-001"), ["L_A_B", "L_B_Z1"])
        _assign_order(fleet.get_robot("R-002"), ["L_X_B", "L_B_Z2"])
        _assign_order(fleet.get_robot("R-003"), ["L_Y_B", "L_B_Z3"])
    elif scenario == "charger":
        for i in range(1, 6):
            rid = f"R-{i:03d}"
            charger = "L_B_CHG1" if (i - 1) % 2 == 0 else "L_B_CHG2"
            _assign_order(fleet.get_robot(rid), ["L_A_B", charger])
    elif scenario == "fault":
        _assign_order(fleet.get_robot("R-001"), ["L_A_B", "L_B_C"])
    elif scenario == "deadlock":
        _assign_order(fleet.get_robot("R-001"), ["L_A_B"])
        _assign_order(fleet.get_robot("R-002"), ["L_B_A"])
    elif scenario == "safe_distance":
        _assign_order(fleet.get_robot("R-001"), ["L_A_B", "L_B_C"])
        _assign_order(fleet.get_robot("R-002"), ["L_A_B", "L_B_C"])


def _assign_order(robot: SimulatedRobot | None, lane_ids: list[str]) -> None:
    """Craft a minimal VDA5050 order dict and assign it to *robot*."""
    if robot is None:
        logger.warning("Cannot assign order — robot is None")
        return
    order = {
        "orderId": f"SCENARIO-{robot.robot_id}",
        "nodes": [{"nodeId": lid} for lid in lane_ids],
    }
    robot.assign_order(order)
    logger.debug("Robot %s assigned order %s", robot.robot_id, order["orderId"])


def _report_scenario_results(fleet: FleetSimulator, scenario: str) -> None:
    """Log final state of every robot after the scenario run."""
    logger.info("═" * 50)
    logger.info("Scenario %s results:", scenario)
    logger.info("═" * 50)
    for rid in fleet.robot_ids:
        robot = fleet.get_robot(rid)
        if robot is None:
            continue
        path_done = not robot.path
        logger.info(
            "  %s: mode=%s battery=%.1f%% velocity=%.3f path_done=%s lane=%s errors=%s",
            rid,
            robot.mode.value,
            robot.battery_percent,
            robot.velocity,
            path_done,
            robot.current_lane_id,
            robot.errors or "[]",
        )


if __name__ == "__main__":
    sys.exit(run())
