"""
SAP EWM Robot Dispatch Platform — MQTT Publisher Module
Provides VDA5050-compliant MQTT publishing with:
- QoS 1 delivery guarantees
- Automatic sequence numbering (via Redis INCR per topic)
- Last-will-and-testament support
- Reconnect handling
"""
import json
import logging
import os
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
import redis

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "robot-platform-sap-bridge")
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")

VDA5050_VERSION = "2.0.0"

# ──────────────────────────────────────────────
# MQTT Client
# ──────────────────────────────────────────────

class VDA5050Publisher:
    """VDA5050-compliant MQTT publisher with auto sequence numbering."""

    def __init__(self):
        self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        self.client = mqtt.Client(
            client_id=MQTT_CLIENT_ID,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self._connected = False

    def connect(self):
        """Connect to MQTT broker with LWT."""
        # Last Will & Testament
        self.client.will_set(
            topic=f"vda5050/{MQTT_CLIENT_ID}/connection",
            payload=json.dumps({"state": "DISCONNECTED", "timestamp": self._iso_now()}),
            qos=1,
            retain=True,
        )
        self.client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        self.client.loop_start()
        logger.info(f"MQTT connecting to {MQTT_BROKER}:{MQTT_PORT} as {MQTT_CLIENT_ID}")

    def disconnect(self):
        """Disconnect gracefully."""
        self.client.loop_stop()
        self.client.disconnect()
        self._connected = False

    def publish(
        self,
        manufacturer: str,
        serial_number: str,
        topic_suffix: str,
        payload: dict,
        qos: int = 1,
        retain: bool = False,
    ) -> int | None:
        """
        Publish a VDA5050 message with auto-incrementing sequence number.

        Args:
            manufacturer: Robot manufacturer (e.g., "KUKA")
            serial_number: Robot serial number (e.g., "KMR-001")
            topic_suffix: One of: connection, state, order, instantActions, visualization
            payload: Message payload (sequenceNumber is auto-added)
            qos: MQTT QoS level (default 1)
            retain: Retain flag

        Returns:
            MQTT message ID on success, None on failure
        """
        topic = f"vda5050/{manufacturer}/{serial_number}/{topic_suffix}"

        # Auto-increment sequence number per topic
        seq_key = f"mqtt:seq:{topic}"
        sequence_number = self.redis_client.incr(seq_key)
        self.redis_client.expire(seq_key, 86400)  # 24h TTL

        # Build VDA5050 envelope
        message = {
            "headerId": sequence_number,
            "timestamp": self._iso_now(),
            "version": VDA5050_VERSION,
            "manufacturer": manufacturer,
            "serialNumber": serial_number,
            **payload,
        }

        result = self.client.publish(topic, json.dumps(message), qos=qos, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Published seq={sequence_number} to {topic}")
            return result.mid
        else:
            logger.error(f"Publish failed (rc={result.rc}) to {topic}")
            return None

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Callbacks ──────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected successfully")
            # Announce self as connected
            self.publish(
                "SYSTEM", "sap-bridge", "connection",
                {"state": "ONLINE"}, retain=True
            )
        else:
            self._connected = False
            logger.error(f"MQTT connection failed (rc={rc})")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc})")

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        logger.debug(f"MQTT publish confirmed (mid={mid})")

    # ── Helpers ────────────────────────────────

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(UTC).isoformat()


# ── Singleton ──────────────────────────────────
_publisher: VDA5050Publisher | None = None


def get_publisher() -> VDA5050Publisher:
    global _publisher
    if _publisher is None:
        _publisher = VDA5050Publisher()
    return _publisher
