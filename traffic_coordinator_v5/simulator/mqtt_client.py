"""paho-mqtt v2 wrapper for the VDA5050 simulator."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

ORDER_TOPIC = "vda5050/{manufacturer}/{serialNumber}/order"
INSTANT_ACTIONS_TOPIC = "vda5050/{manufacturer}/{serialNumber}/instantActions"
STATE_TOPIC = "vda5050/{manufacturer}/{serialNumber}/state"
CONNECTION_TOPIC = "vda5050/{manufacturer}/{serialNumber}/connection"


class MqttVDAClient:
    """MQTT client that publishes VDA5050 state/connection and subscribes to
    orders and instant actions for a fleet of simulated robots.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        brand: str = "generic",
        on_order: Callable[[str, dict], None] | None = None,
        on_instant_actions: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._brand = brand
        self._on_order = on_order
        self._on_instant_actions = on_instant_actions
        self._client: mqtt.Client | None = None
        self._connected: bool = False
        self._robot_ids: set[str] = set()

    def _client_id(self) -> str:
        return f"{self._brand}-sim-{uuid.uuid4().hex[:8]}"

    def set_callbacks(
        self,
        on_order: Callable[[str, dict], None] | None = None,
        on_instant_actions: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Set or update order/instant-action callbacks."""
        if on_order is not None:
            self._on_order = on_order
        if on_instant_actions is not None:
            self._on_instant_actions = on_instant_actions

    def add_robot(self, robot_id: str) -> None:
        """Register a robot so its topics are subscribed on connect."""
        self._robot_ids.add(robot_id)
        if self._client is not None and self._client.is_connected():
            self._subscribe_for(robot_id)
            self.publish_connection(robot_id, "ONLINE")

    def connect(self) -> None:
        """Connect to the broker and subscribe to robot topics."""
        self._client = mqtt.Client(
            client_id=self._client_id(),
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        # Last Will: if the simulator process dies, all robots appear broken.
        # Use a per-instance topic (includes a unique suffix) so that stale
        # retained messages from a previous crash do not confuse downstream
        # systems.  The stale LWT is also explicitly cleared on connect.
        self._lwt_topic = f"vda5050/{self._brand}/simulator/{self._client_id()}/connection"
        self._client.will_set(
            self._lwt_topic,
            json.dumps({"connectionState": "CONNECTIONBROKEN"}),
            qos=1,
            retain=True,
        )

        try:
            self._client.connect(self._broker_host, self._broker_port, keepalive=60)
            self._client.loop_start()
            logger.info(
                "Simulator MQTT connected to %s:%d", self._broker_host, self._broker_port
            )
        except (OSError, ConnectionError) as exc:
            logger.exception("Simulator failed to connect to MQTT broker: %s", exc)
            self._client = None

    def disconnect(self) -> None:
        """Publish offline for all robots and disconnect."""
        if self._client is None:
            return
        for robot_id in list(self._robot_ids):
            self.publish_connection(robot_id, "OFFLINE")
        # Clear the retained LWT so it does not linger after a clean shutdown.
        with contextlib.suppress(Exception):
            self._client.publish(self._lwt_topic, payload=b"", qos=1, retain=True)
        with contextlib.suppress(Exception):
            self._client.loop_stop()
            self._client.disconnect()
        self._client = None

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, rc: int, _props: Any = None) -> None:
        if rc == 0:
            self._connected = True
            # Clear any stale retained LWT from a previous crash so downstream
            # systems do not see a lingering CONNECTIONBROKEN message.
            with contextlib.suppress(Exception):
                client.publish(
                    f"vda5050/{self._brand}/simulator/connection",
                    payload=b"",
                    qos=1,
                    retain=True,
                )
            for robot_id in self._robot_ids:
                self._subscribe_for(robot_id)
                self.publish_connection(robot_id, "ONLINE")
            logger.info("Simulator subscribed to robot order/instantActions topics")
        else:
            logger.error("Simulator MQTT connection failed, rc=%s", rc)

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _rc: int, _props: Any = None) -> None:
        self._connected = False
        logger.warning("Simulator MQTT disconnected; will retry")

    def _subscribe_for(self, robot_id: str) -> None:
        if self._client is None:
            return
        order_topic = ORDER_TOPIC.format(manufacturer=self._brand, serialNumber=robot_id)
        action_topic = INSTANT_ACTIONS_TOPIC.format(
            manufacturer=self._brand, serialNumber=robot_id
        )
        self._client.subscribe(order_topic, qos=1)
        self._client.subscribe(action_topic, qos=1)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        parts = topic.split("/")
        if len(parts) < 4 or parts[0] != "vda5050" or parts[1] != self._brand:
            return
        robot_id = parts[2]
        suffix = parts[3]
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning("Simulator received invalid JSON on %s", topic)
            return

        if suffix == "order" and self._on_order is not None:
            self._on_order(robot_id, payload)
        elif suffix == "instantActions" and self._on_instant_actions is not None:
            self._on_instant_actions(robot_id, payload)

    def publish_state(self, robot_id: str, state: dict) -> None:
        """Publish a state message for ``robot_id``."""
        if self._client is None or not self._connected:
            return
        topic = STATE_TOPIC.format(manufacturer=self._brand, serialNumber=robot_id)
        try:
            self._client.publish(topic, json.dumps(state), qos=0)
        except (OSError, ConnectionError) as exc:
            logger.exception("Simulator failed to publish state for %s: %s", robot_id, exc)

    def publish_connection(self, robot_id: str, state: str) -> None:
        """Publish a connection message for ``robot_id`` (retained, QoS 1)."""
        if self._client is None:
            return
        topic = CONNECTION_TOPIC.format(manufacturer=self._brand, serialNumber=robot_id)
        try:
            self._client.publish(
                topic,
                json.dumps({"connectionState": state}),
                qos=1,
                retain=True,
            )
        except (OSError, ConnectionError) as exc:
            logger.exception("Simulator failed to publish connection for %s: %s", robot_id, exc)
