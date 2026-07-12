"""MQTT → v5 core bridge (灰犀牛 #7: 版本泥潭).

Subscribes to VDA5050 MQTT topics from the v4.1 fabric (Node-RED / robot
adapters), translates messages via VersionRouter (v4.x → v5.0), and
forwards to the traffic coordinator HTTP API.

This is the one-way ingest bridge. The reverse path (v5 commands → MQTT)
will be added when the coordinator emits outbound events.

Topic pattern: vda5050/{manufacturer}/{serialNumber}/state
  → POST http://tc:8000/ingest/{manufacturer}
  body = VersionRouter.normalise(VersionedMessage(version="4.1", body=msg))

Env vars:
  MQTT_BROKER          — broker host (default: mqtt)
  MQTT_PORT            — broker port (default: 1883)
  TC_HTTP_URL          — traffic coordinator URL (default: http://traffic-coordinator:8000)
  BRIDGE_CLIENT_ID     — MQTT client ID (default: v5-mqtt-bridge)
"""
from __future__ import annotations

import json
import logging
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

from core.config import CoreConfig
from core.survival.version_router import VersionedMessage, VersionRouter

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("BRIDGE_CLIENT_ID", "v5-mqtt-bridge")
TC_HTTP_URL = os.getenv("TC_HTTP_URL", "http://traffic-coordinator:8000").rstrip("/")

# vda5050/{manufacturer}/{serialNumber}/state
_TOPIC_RE = re.compile(r"^vda5050/([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)/state$")

# VDA5050 version detection: header.versionId or default to 4.1
_VDA5050_DEFAULT_VERSION = "4.1"

_router = VersionRouter(CoreConfig())


def _post_ingest(brand: str, body: dict) -> None:
    """POST a normalised state message to the traffic coordinator."""
    url = f"{TC_HTTP_URL}/ingest/{brand}"
    data = json.dumps(body).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                logger.warning("TC ingest returned %d for brand=%s", resp.status, brand)
    except URLError as e:
        logger.error("Failed to reach TC at %s: %s", url, e)


def _on_message(
    _client: mqtt.Client,
    _userdata: None,
    msg: mqtt.MQTTMessage,
) -> None:
    """Parse VDA5050 state, translate v4→v5, forward to TC HTTP."""
    match = _TOPIC_RE.match(msg.topic)
    if not match:
        return
    brand = match.group(1)
    try:
        raw = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON on topic %s", msg.topic)
        return

    version = raw.get("header", {}).get("versionId", _VDA5050_DEFAULT_VERSION)
    try:
        normalised = _router.normalise(VersionedMessage(version=version, body=raw))
    except ValueError:
        logger.warning("Unsupported version %s on topic %s", version, msg.topic)
        return

    _post_ingest(brand, normalised.body)


def create_bridge() -> mqtt.Client:
    """Create and configure the MQTT bridge client (does not connect)."""
    client = mqtt.Client(client_id=MQTT_CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    client = create_bridge()
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.subscribe("vda5050/+/+/state", qos=1)
    logger.info("v5 MQTT bridge connected to %s:%d, forwarding to %s", MQTT_BROKER, MQTT_PORT, TC_HTTP_URL)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down bridge...")
        client.disconnect()


if __name__ == "__main__":
    main()
