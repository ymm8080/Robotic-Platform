"""
MiR250 simulator.
VDA5050 v1.1.0 — simulates known quirks:
- DRIVING reported instead of MOVING
- WAITING state before IDLE after job complete
"""

import random

from .base_simulator import BaseRobotSimulator


class MirSimulator(BaseRobotSimulator):
    """Simulates a MiR250 robot with known v1.1 quirks."""

    def __init__(self, serial_number: str = "MIR-001", mqtt_broker: str = "localhost", mqtt_port: int = 1883):
        super().__init__(
            manufacturer="MIR",
            serial_number=serial_number,
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            version="1.1.0",
            interval=2.5,  # MiR reports at slower interval
        )
        self._job_complete_counter = 0
        self._waiting_before_idle = True  # Simulate the WAITING quirk

    def _simulate_step(self):
        """MiR simulation: reports DRIVING (not MOVING), sends WAITING before IDLE."""
        if not self._state["driving"] or self._state["paused"]:
            return

        pos = self._state["agvPosition"]
        pos["x"] += random.uniform(0.5, 1.0)
        batt = self._state["batteryState"]
        batt["batteryCharge"] = max(0, batt["batteryCharge"] - random.uniform(0.2, 0.6))

        # Simulate job completion WAITING quirk
        if random.random() < 0.05:  # 5% chance per tick
            self._state["driving"] = False
            self._job_complete_counter = 3  # Will send WAITING for 3 ticks

        if self._job_complete_counter > 0:
            self._job_complete_counter -= 1
            # MiR reports DRIVING state as "WAITING" before going IDLE
            # This is handled in the MiR strategy via WAITING_GRACE_COUNT

    def _publish(self, msg_type: str, extra: dict):
        """Override to add MiR v1.1 specific fields to state messages."""
        if msg_type == "state":
            # MiR v1.1 reports drivingState as a separate field
            if self._state["driving"]:
                if self._job_complete_counter > 0:
                    extra["drivingState"] = "WAITING"  # Quirk: WAITING before IDLE
                else:
                    extra["drivingState"] = "DRIVING"  # Quirk: DRIVING not MOVING
            else:
                extra["drivingState"] = "IDLE"
        super()._publish(msg_type, extra)
