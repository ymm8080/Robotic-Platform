"""
Base VDA5050 robot simulator.
Emits state/connection messages on MQTT and responds to orders.
"""
import json
import logging
import random
import threading
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

VDA5050_TOPIC = "vda5050/{manufacturer}/{serialNumber}/{messageType}"


class BaseRobotSimulator:
    """Simulates a VDA5050 robot for testing.

    Publishes:
    - connection (QoS 1, retain): ONLINE/OFFLINE
    - state (QoS 0): position, battery, errors, action status
    Subscribes to:
    - order: receive dispatch commands
    - instantActions: receive cancel/pause/resume
    """

    def __init__(
        self,
        manufacturer: str = "Generic",
        serial_number: str = "R-001",
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        version: str = "2.0.0",
        interval: float = 2.0,  # State publish interval (seconds)
    ):
        self.manufacturer = manufacturer
        self.serial_number = serial_number
        self.version = version
        self.interval = interval

        # Internal state
        self._state = {
            "orderId": "",
            "orderUpdateId": 0,
            "driving": False,
            "paused": False,
            "newBaseRequest": False,
            "operatingMode": "AUTOMATIC",
            "batteryState": {"batteryCharge": 85.0, "batteryVoltage": 48.5, "batteryHealth": 95.0},
            "agvPosition": {"x": 0.0, "y": 0.0, "theta": 0.0, "lastNodeId": "HOME", "positionInitialized": True},
            "errors": [],
            "actionStates": [],
            "nodeStates": [],
            "edgeStates": [],
            "distanceSinceLastNode": 0.0,
            "safetyState": {"eStop": False, "fieldViolation": False},
        }
        self._connected = False
        self._running = False
        self._header_id = 0
        self._thread: threading.Thread | None = None

        # MQTT client
        self._client = mqtt.Client(
            client_id=f"sim-{manufacturer}-{serial_number}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            clean_session=False,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._mqtt_broker = mqtt_broker
        self._mqtt_port = mqtt_port

    # ── Public API ───────────────────────────────────────

    def start(self):
        """Connect to MQTT and start state publishing loop."""
        self._running = True
        self._connect_mqtt()
        self._announce_online()
        self._thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._thread.start()
        logger.info(f"Simulator started: {self.manufacturer}/{self.serial_number}")

    def stop(self):
        """Stop simulator and disconnect."""
        self._running = False
        self._announce_offline()
        if self._thread:
            self._thread.join(timeout=5)
        self._client.disconnect()
        logger.info(f"Simulator stopped: {self.manufacturer}/{self.serial_number}")

    def set_battery(self, percent: float, voltage: float | None = None):
        """Override battery level."""
        self._state["batteryState"]["batteryCharge"] = percent
        if voltage is not None:
            self._state["batteryState"]["batteryVoltage"] = voltage

    def set_position(self, x: float, y: float, theta: float = 0.0):
        """Override robot position."""
        self._state["agvPosition"]["x"] = x
        self._state["agvPosition"]["y"] = y
        self._state["agvPosition"]["theta"] = theta

    def add_error(self, error_type: str, level: str = "WARNING", description: str = ""):
        """Inject an error."""
        self._state["errors"].append({
            "errorType": error_type,
            "errorLevel": level,
            "errorDescription": description,
        })

    def clear_errors(self):
        """Clear all errors."""
        self._state["errors"] = []

    # ── Internal ─────────────────────────────────────────

    def _connect_mqtt(self):
        self._client.will_set(
            self._topic("connection"),
            payload=json.dumps({
                "headerId": 0,
                "timestamp": self._iso_now(),
                "version": self.version,
                "manufacturer": self.manufacturer,
                "serialNumber": self.serial_number,
                "connectionState": "CONNECTIONBROKEN",
            }),
            qos=1,
            retain=True,
        )
        self._client.connect(self._mqtt_broker, self._mqtt_port, 60)
        self._client.loop_start()

    def _announce_online(self):
        self._publish("connection", {
            "connectionState": "ONLINE",
        })

    def _announce_offline(self):
        self._publish("connection", {
            "connectionState": "OFFLINE",
        })

    def _publish(self, msg_type: str, extra: dict):
        self._header_id += 1
        payload = {
            "headerId": self._header_id,
            "timestamp": self._iso_now(),
            "version": self.version,
            "manufacturer": self.manufacturer,
            "serialNumber": self.serial_number,
            **extra,
        }
        qos = 1 if msg_type == "connection" else 0
        retain = msg_type == "connection"
        self._client.publish(self._topic(msg_type), json.dumps(payload), qos=qos, retain=retain)

    def _topic(self, msg_type: str) -> str:
        return VDA5050_TOPIC.format(
            manufacturer=self.manufacturer,
            serialNumber=self.serial_number,
            messageType=msg_type,
        )

    def _publish_loop(self):
        while self._running:
            self._simulate_step()
            self._publish("state", self._state)
            time.sleep(self.interval)

    def _simulate_step(self):
        """Override in subclass to add brand-specific behavior."""
        # Default: slowly move along X axis
        pos = self._state["agvPosition"]
        if self._state["driving"]:
            pos["x"] += random.uniform(0.5, 1.5)
            # Slowly drain battery while driving
            batt = self._state["batteryState"]
            batt["batteryCharge"] = max(0, batt["batteryCharge"] - random.uniform(0.1, 0.5))

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"[{self.serial_number}] MQTT connected")
            self._client.subscribe(self._topic("order"), qos=0)
            self._client.subscribe(self._topic("instantActions"), qos=0)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        logger.warning(f"[{self.serial_number}] MQTT disconnected (rc={rc})")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return

        if "order" in topic:
            self._handle_order(payload)
        elif "instantActions" in topic:
            self._handle_instant_actions(payload)

    def _handle_order(self, payload: dict):
        """Receive and execute an order."""
        order_id = payload.get("orderId", "")
        self._state["orderId"] = order_id
        self._state["orderUpdateId"] = payload.get("orderUpdateId", 0)
        self._state["driving"] = True
        self._state["actionStates"] = []
        logger.info(f"[{self.serial_number}] Executing order {order_id}")

    def _handle_instant_actions(self, payload: dict):
        """Handle cancel/pause/resume commands."""
        actions = payload.get("actions", [])
        for action in actions:
            action_type = action.get("actionType", "")
            if action_type == "cancelOrder":
                self._state["orderId"] = ""
                self._state["driving"] = False
                self._state["actionStates"] = []
            elif action_type == "startPause":
                self._state["paused"] = True
            elif action_type == "stopPause":
                self._state["paused"] = False

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(UTC).isoformat()
