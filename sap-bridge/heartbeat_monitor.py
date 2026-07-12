"""
Heartbeat Monitor — Tracks robot connection state via MQTT VDA5050 topics.
Stores state in Redis HASH with TTL expiry.
"""
import json
import logging
import os
import re
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from redis_client import redis_from_url

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "false").lower() == "true"
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD_FILE = os.getenv("MQTT_PASSWORD_FILE", "/run/secrets/mqtt_password")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")
MQTT_CLIENT_CERT = os.getenv("MQTT_CLIENT_CERT", "")
MQTT_CLIENT_KEY = os.getenv("MQTT_CLIENT_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

TOPIC_CONNECTION = "vda5050/+/+/connection"
TOPIC_STATE = "vda5050/+/+/state"
TOPIC_PATTERN = re.compile(r"^vda5050/([^/]+)/([^/]+)/(connection|state)$")

ROBOT_TTL = int(os.getenv("ROBOT_HEARTBEAT_TTL", "300"))  # 5 min


class HeartbeatMonitor:
    """Subscribes to VDA5050 connection/state topics and maintains Redis state."""

    def __init__(self):
        self.redis_client = redis_from_url(REDIS_URL, decode_responses=True)
        self.client = mqtt.Client(
            client_id="robot-platform-heartbeat-monitor",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            clean_session=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._running = False

    @staticmethod
    def _load_mqtt_password() -> str:
        """Read MQTT password from Docker secret, falling back to env var."""
        try:
            with open(MQTT_PASSWORD_FILE) as f:
                return f.read().strip()
        except FileNotFoundError:
            return MQTT_PASSWORD

    def start(self):
        if MQTT_USE_TLS:
            if MQTT_CA_CERT:
                self.client.tls_set(
                    ca_certs=MQTT_CA_CERT,
                    certfile=MQTT_CLIENT_CERT or None,
                    keyfile=MQTT_CLIENT_KEY or None,
                )
            else:
                self.client.tls_set()
            self.client.tls_insecure_set(False)
            logger.info("Heartbeat monitor MQTT TLS enabled")
        if MQTT_USERNAME:
            password = self._load_mqtt_password()
            self.client.username_pw_set(MQTT_USERNAME, password or None)

        self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.client.loop_start()
        self._running = True
        logger.info("Heartbeat monitor started")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        self._running = False
        logger.info("Heartbeat monitor stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Callbacks ──────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Heartbeat monitor connected to MQTT")
            client.subscribe(TOPIC_CONNECTION, qos=1)
            client.subscribe(TOPIC_STATE, qos=1)
            logger.info(f"Subscribed to {TOPIC_CONNECTION}, {TOPIC_STATE}")

    def _on_message(self, client, userdata, msg):
        match = TOPIC_PATTERN.match(msg.topic)
        if not match:
            return
        manufacturer, serial_number, topic_type = match.groups()
        robot_id = f"{manufacturer}-{serial_number}"
        redis_key = f"robot:connection:{robot_id}"

        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {msg.topic}")
            return

        now = datetime.now(UTC).isoformat()

        if topic_type == "connection":
            state = payload.get("connectionState", payload.get("state", "UNKNOWN"))
            self.redis_client.hset(redis_key, mapping={
                "state": state,
                "lastSeen": now,
                "manufacturer": manufacturer,
                "serialNumber": serial_number,
                "connectionState": state,
            })
            self.redis_client.expire(redis_key, ROBOT_TTL)
            logger.info(f"Robot {robot_id} connection: {state}")

        elif topic_type == "state":
            # VDA5050 state: derive vehicle state from driving+paused+errors+operatingMode
            driving = payload.get("driving", False)
            paused = payload.get("paused", False)
            errors = payload.get("errors", [])
            operating_mode = payload.get("operatingMode", "AUTOMATIC")
            battery_state = payload.get("batteryState", {})
            is_charging = (
                battery_state.get("charging", False)
                if isinstance(battery_state, dict)
                else False
            )

            if any(e.get("errorLevel") == "FATAL" for e in errors if isinstance(e, dict)):
                vehicle_state = "ERROR"
            elif operating_mode not in ("AUTOMATIC", "SEMIAUTOMATIC"):
                vehicle_state = "UNAVAILABLE"
            elif is_charging:
                vehicle_state = "CHARGING"
            elif driving:
                vehicle_state = "MOVING"
            elif paused:
                vehicle_state = "PAUSED"
            else:
                vehicle_state = "IDLE"

            battery = payload.get("batteryState", {}).get("batteryCharge", "")
            position = payload.get("agvPosition", payload.get("position", {}))

            self.redis_client.hset(redis_key, mapping={
                "state": vehicle_state,
                "lastSeen": now,
                "battery": str(battery) if battery != "" else "",
                "position_x": str(position.get("x", "")),
                "position_y": str(position.get("y", "")),
                "manufacturer": manufacturer,
                "serialNumber": serial_number,
                "driving": str(driving).lower(),
                "paused": str(paused).lower(),
                "operatingMode": operating_mode,
                "raw_state": json.dumps(payload),
            })
            self.redis_client.expire(redis_key, ROBOT_TTL)
