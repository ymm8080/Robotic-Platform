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
import re
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from redis_client import redis_from_url

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "robot-platform-sap-bridge")
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "false").lower() == "true"
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD_FILE = os.getenv("MQTT_PASSWORD_FILE", "/run/secrets/mqtt_password")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")
MQTT_CLIENT_CERT = os.getenv("MQTT_CLIENT_CERT", "")
MQTT_CLIENT_KEY = os.getenv("MQTT_CLIENT_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")

VDA5050_VERSION = "2.0.0"

# Allowed VDA5050 topic suffixes to prevent arbitrary topic publishes.
ALLOWED_TOPIC_SUFFIXES = {"connection", "state", "order", "instantActions", "visualization"}

# Safe topic path component (alphanumeric, underscore, hyphen, dot)
_TOPIC_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_\.\-]+$")

# ──────────────────────────────────────────────
# MQTT Client
# ──────────────────────────────────────────────

class VDA5050Publisher:
    """VDA5050-compliant MQTT publisher with auto sequence numbering."""

    def __init__(self):
        self.redis_client = redis_from_url(REDIS_URL, decode_responses=True)
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

    @staticmethod
    def _load_mqtt_password() -> str:
        """Read MQTT password from Docker secret, falling back to env var."""
        try:
            with open(MQTT_PASSWORD_FILE) as f:
                return f.read().strip()
        except FileNotFoundError:
            return MQTT_PASSWORD

    def connect(self):
        """Connect to MQTT broker with optional TLS, authentication, and LWT."""
        # Configure TLS if enabled
        if MQTT_USE_TLS:
            if MQTT_CA_CERT:
                self.client.tls_set(
                    ca_certs=MQTT_CA_CERT,
                    certfile=MQTT_CLIENT_CERT or None,
                    keyfile=MQTT_CLIENT_KEY or None,
                )
            else:
                self.client.tls_set()
            # Do not allow insecure TLS by default
            self.client.tls_insecure_set(False)
            logger.info("MQTT TLS enabled")

        # Configure username/password authentication
        if MQTT_USERNAME:
            password = self._load_mqtt_password()
            self.client.username_pw_set(MQTT_USERNAME, password or None)

        # Last Will & Testament
        self.client.will_set(
            topic=f"vda5050/{MQTT_CLIENT_ID}/connection",
            payload=json.dumps({"connectionState": "CONNECTIONBROKEN", "timestamp": self._iso_now()}),
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
        if topic_suffix not in ALLOWED_TOPIC_SUFFIXES:
            logger.error(f"MQTT publish rejected: invalid topic suffix {topic_suffix!r}")
            return None
        if not _TOPIC_COMPONENT_RE.match(manufacturer):
            logger.error(f"MQTT publish rejected: invalid manufacturer {manufacturer!r}")
            return None
        if not _TOPIC_COMPONENT_RE.match(serial_number):
            logger.error(f"MQTT publish rejected: invalid serial_number {serial_number!r}")
            return None

        topic = f"vda5050/{manufacturer}/{serial_number}/{topic_suffix}"

        # Auto-increment sequence number per topic
        seq_key = f"mqtt:seq:{topic}"
        sequence_number = self.redis_client.incr(seq_key)
        self.redis_client.expire(seq_key, 86400)  # 24h TTL

        # Build VDA5050 envelope (envelope fields must not be overridden by payload)
        message = {
            **payload,
            "headerId": sequence_number,
            "timestamp": self._iso_now(),
            "version": VDA5050_VERSION,
            "manufacturer": manufacturer,
            "serialNumber": serial_number,
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
                {"connectionState": "ONLINE"}, retain=True
            )
        else:
            self._connected = False
            logger.error(f"MQTT connection failed (rc={rc})")

    def _on_disconnect(self, client, userdata, flags, reason_code=0, properties=None):
        self._connected = False
        if reason_code != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={reason_code})")

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
