"""
OTTO 1500 simulator.
VDA5050 v2.0.0 — simulates:
- Battery in millivolts (not percentage)
- Custom CHARGING state via batteryState.charging flag
"""

import random

from .base_simulator import BaseRobotSimulator


class OttoSimulator(BaseRobotSimulator):
    """Simulates an OTTO 1500 robot with millivolt battery."""

    # OTTO battery ranges: 48000mV (empty) → 54600mV (full)
    _MV_FULL = 54600
    _MV_EMPTY = 48000
    _MV_RANGE = _MV_FULL - _MV_EMPTY

    def __init__(self, serial_number: str = "OTTO-001", mqtt_broker: str = "localhost", mqtt_port: int = 1883):
        super().__init__(
            manufacturer="OTTO",
            serial_number=serial_number,
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            version="2.0.0",
            interval=1.5,  # OTTO reports more frequently
        )
        # Start at ~60% charge
        self._current_mv = self._MV_EMPTY + int(self._MV_RANGE * 0.6)
        self._charging = False

    def _simulate_step(self):
        """OTTO simulation: millivolt battery, auto-charge at low battery."""
        if self._state["driving"] and not self._state["paused"]:
            pos = self._state["agvPosition"]
            pos["x"] += random.uniform(0.8, 1.8)
            pos["y"] += random.uniform(-0.3, 0.3)

            # Drain battery in millivolts
            drain = random.uniform(20, 80)
            self._current_mv = max(self._MV_EMPTY, self._current_mv - drain)

            # Auto-charge when battery gets low
            if self._current_mv < (self._MV_EMPTY + int(self._MV_RANGE * 0.15)):
                self._charging = True
                self._state["driving"] = False

        if self._charging:
            # Charge battery
            self._current_mv = min(self._MV_FULL, self._current_mv + random.uniform(100, 300))
            if self._current_mv >= self._MV_FULL:
                self._charging = False

        # Update batteryState with millivolt format
        self._state["batteryState"] = {
            "batteryVoltage": self._current_mv,  # Millivolts!
            "batteryCharge": 0,  # OTTO may report 0 for charge
            "charging": self._charging,
        }
