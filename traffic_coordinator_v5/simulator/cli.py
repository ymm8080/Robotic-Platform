"""Command-line interface for the VDA5050 mock robot simulator."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from traffic_coordinator_v5.simulator.fleet import FleetSimulator
from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.mqtt_client import MqttVDAClient
from traffic_coordinator_v5.simulator.robot import RobotConfig

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
    return lane_graph.first_lane()


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

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
                import random

                for rid, robot in fleet._robots.items():
                    if random.random() < args.fault_prob and robot.mode.name != "ERROR":
                        robot.inject_error("ERR_INJECTED_FAULT")
                        logger.warning("Injected fault into %s", rid)
    finally:
        fleet.stop()
        logger.info("Simulator stopped")

    return 0


if __name__ == "__main__":
    sys.exit(run())
