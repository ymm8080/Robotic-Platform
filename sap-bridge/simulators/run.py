#!/usr/bin/env python3
"""
VDA5050 Robot Simulator Runner.

Launches one or more simulated robots that publish VDA5050 state messages
via MQTT, for testing the dispatch platform without real hardware.

Usage:
    python simulators/run.py --brand KUKA --count 2
    python simulators/run.py --brand MIR --count 1 --broker 192.168.1.100
    python simulators/run.py --brand OTTO --broker localhost --interval 1.0
    python simulators/run.py --all  # Start one of each brand
"""
import argparse
import logging
import signal
import sys
import time

from simulators.base_simulator import BaseRobotSimulator
from simulators.kuka_simulator import KukaSimulator
from simulators.mir_simulator import MirSimulator
from simulators.otto_simulator import OttoSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sim-runner")

SIMULATORS = {
    "KUKA": KukaSimulator,
    "MIR": MirSimulator,
    "OTTO": OttoSimulator,
}


def create_simulators(brand: str, count: int, broker: str, port: int) -> list[BaseRobotSimulator]:
    """Create simulator instances for the given brand."""
    cls = SIMULATORS.get(brand.upper())
    if cls is None:
        logger.error(f"Unknown brand: {brand}. Available: {list(SIMULATORS.keys())}")
        sys.exit(1)

    serial_prefix = {
        "KUKA": "KMR",
        "MIR": "MIR",
        "OTTO": "OTTO",
    }.get(brand.upper(), "R")

    sims = []
    for i in range(1, count + 1):
        serial = f"{serial_prefix}-{i:03d}"
        sim = cls(serial_number=serial, mqtt_broker=broker, mqtt_port=port)
        sims.append(sim)
    return sims


def main():
    parser = argparse.ArgumentParser(description="VDA5050 Robot Simulator Runner")
    parser.add_argument("--brand", "-b", type=str, default="KUKA", help="Brand: KUKA, MIR, OTTO")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of robots to simulate")
    parser.add_argument("--broker", "-B", type=str, default="localhost", help="MQTT broker address")
    parser.add_argument("--port", "-P", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--all", "-a", action="store_true", help="Start one simulator per brand")
    args = parser.parse_args()

    simulators = []
    if args.all:
        for brand in SIMULATORS:
            simulators.extend(create_simulators(brand, 1, args.broker, args.port))
    else:
        simulators = create_simulators(args.brand, args.count, args.broker, args.port)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        logger.info("Shutting down simulators...")
        for sim in simulators:
            sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start all simulators
    logger.info(f"Starting {len(simulators)} simulator(s)...")
    for sim in simulators:
        sim.start()
        logger.info(f"  {sim.manufacturer}/{sim.serial_number} (VDA5050 v{sim.version})")

    logger.info("Simulators running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
