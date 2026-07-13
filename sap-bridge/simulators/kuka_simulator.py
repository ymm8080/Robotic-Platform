"""
KUKA KMR iiwa simulator.
VDA5050 v2.0.0 — standard behavior with lift action simulation.
"""

import random

from .base_simulator import BaseRobotSimulator


class KukaSimulator(BaseRobotSimulator):
    """Simulates a KUKA KMR iiwa robot."""

    def __init__(self, serial_number: str = "KMR-001", mqtt_broker: str = "localhost", mqtt_port: int = 1883):
        super().__init__(
            manufacturer="KUKA",
            serial_number=serial_number,
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            version="2.0.0",
            interval=2.0,
        )
        # KUKA-specific state
        self._lift_height = 0  # mm
        self._has_lift = True

    def _simulate_step(self):
        """KUKA simulation: standard move + optional lift cycles."""
        super()._simulate_step()

        if self._state["driving"] and not self._state["paused"]:
            # Standard 2D movement
            pos = self._state["agvPosition"]
            pos["x"] += random.uniform(0.3, 1.2)
            pos["y"] += random.uniform(-0.2, 0.2)

            # Simulate lift action occasionally
            if self._has_lift and random.random() < 0.1:
                self._lift_height = random.choice([100, 200, 300])
                self._state["actionStates"] = [
                    {
                        "actionId": f"lift-{self._header_id}",
                        "actionType": "lift",
                        "actionStatus": "RUNNING",
                        "actionParameters": [{"key": "height", "value": str(self._lift_height)}],
                    }
                ]
            elif self._lift_height > 0 and random.random() < 0.3:
                self._lift_height = 0
                self._state["actionStates"] = [
                    {
                        "actionId": f"lift-{self._header_id}",
                        "actionType": "lift",
                        "actionStatus": "FINISHED",
                    }
                ]
