"""
Heartbeat Monitor — Tracks robot connection state via MQTT VDA5050 topics.
Stores state in Redis HASH with TTL expiry.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
import redis

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

TOPIC_CONNECTION = "vda5050/+/+/connection"
TOPIC_STATE = "vda5050/+/+/state"
TOPIC_PATTERN = re.compile(r"^vda5050/([^/]+)/([^/]+)/(connection|state)$")

ROBOT_TTL = int(os.getenv("ROBOT_HEARTBEAT_TTL", "300"))  # 5 min


class HeartbeatMonitor:
    """Subscribes to VDA5050 connection/state topics and maintains Redis state."""

    def __init__(self):
        self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        self.client = mqtt.Client(
            client_id="robot-platform-heartbeat-monitor",
            clean_session=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._running = False

    def start(self):
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

    def _on_connect(self, client, userdata, flags, rc):
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

        now = datetime.now(timezone.utc).isoformat()

        if topic_type == "connection":
            state = payload.get("state", "UNKNOWN")
            self.redis_client.hset(redis_key, mapping={
                "state": state,
                "lastSeen": now,
                "manufacturer": manufacturer,
                "serialNumber": serial_number,
            })
            self.redis_client.expire(redis_key, ROBOT_TTL)
            logger.info(f"Robot {robot_id} connection: {state}")

        elif topic_type == "state":
            state = payload.get("orderState", payload.get("drivingState", "UNKNOWN"))
            battery = payload.get("batteryState", {}).get("batteryCharge", "")
            position = payload.get("position", {})

            self.redis_client.hset(redis_key, mapping={
                "state": state,
                "lastSeen": now,
                "battery": str(battery) if battery else "",
                "position_x": str(position.get("x", "")),
                "position_y": str(position.get("y", "")),
                "manufacturer": manufacturer,
                "serialNumber": serial_number,
            })
            self.redis_client.expire(redis_key, ROBOT_TTL)
