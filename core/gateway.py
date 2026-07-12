"""Transport gateway — MQTT (VDA5050) + in-memory test harness.

The coordinator is intentionally transport-agnostic. This module provides
the gateways that feed robot state into the coordinator and emit commands
back to robots:

- ``MqttGateway`` — production: subscribes VDA5050 MQTT topics, publishes
  TaskAssignment / AdapterCommand back to robots.
- ``MemoryGateway`` — test/simulation: in-memory queue, deterministic.

Topic hierarchy (VDA5050 §6.3):
  vda5050/{manufacturer}/{serialNumber}/state
  vda5050/{manufacturer}/{serialNumber}/connection
  vda5050/{manufacturer}/{serialNumber}/order
  vda5050/{manufacturer}/{serialNumber}/instantActions
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from core.adapter.fleet_adapter import AdapterCommand
from core.messages import TaskAssignment

logger = logging.getLogger(__name__)

# ── Wire types ───────────────────────────────────────────────


@dataclass
class InboundMessage:
    brand: str
    raw: dict
    received_at: float


@dataclass
class OutboundEnvelope:
    """One outbound message to a robot.

    ``robot_id`` is the VDA5050 ``serialNumber`` (not the manufacturer-prefixed
    internal connection key). ``brand`` is the VDA5050 ``manufacturer``.
    """

    robot_id: str
    brand: str
    assignment: TaskAssignment | None = None
    command: AdapterCommand | None = None


# ── Abstract gateways ────────────────────────────────────────


class InboundGateway(ABC):
    """Receives vendor-native robot state and forwards it to the coordinator."""

    @abstractmethod
    def start(self, callback: Callable[[InboundMessage], None]) -> None:
        """Begin receiving messages; invoke ``callback`` for each message."""

    @abstractmethod
    def stop(self) -> None:
        """Stop receiving messages."""


class OutboundGateway(ABC):
    """Sends assignments and fallback commands back to vendor fleets."""

    @abstractmethod
    def send(self, envelope: OutboundEnvelope) -> None:
        """Deliver one assignment or command to the target robot/brand."""


# ── Memory gateway (tests / simulation) ───────────────────────


class MemoryGateway(InboundGateway, OutboundGateway):
    """In-memory gateway for unit tests and offline simulation."""

    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.outbound: list[OutboundEnvelope] = []
        self._callback: Callable[[InboundMessage], None] | None = None

    def inject(self, msg: InboundMessage) -> None:
        self.inbound.append(msg)
        if self._callback is not None:
            self._callback(msg)

    def start(self, callback: Callable[[InboundMessage], None]) -> None:
        self._callback = callback

    def stop(self) -> None:
        self._callback = None

    def send(self, envelope: OutboundEnvelope) -> None:
        self.outbound.append(envelope)


# ── MQTT gateway (production) ─────────────────────────────────


@dataclass
class RobotConnection:
    """Tracked connection state for one robot (LWT + heartbeat)."""

    robot_id: str
    manufacturer: str
    serial_number: str
    online: bool = False
    last_seen: float = 0.0
    boot_id: str = ""


# VDA5050 topic constants
VDA5050_STATE_TOPIC = "vda5050/+/+/state"
VDA5050_CONNECTION_TOPIC = "vda5050/+/+/connection"
ORDER_TOPIC = "vda5050/{manufacturer}/{serialNumber}/order"
INSTANT_ACTIONS_TOPIC = "vda5050/{manufacturer}/{serialNumber}/instantActions"


def _parse_vda5050_topic(topic: str) -> tuple[str, str] | None:
    """Extract (manufacturer, serialNumber) from a VDA5050 topic."""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "vda5050":
        return parts[1], parts[2]
    return None


class MqttGateway(InboundGateway, OutboundGateway):
    """Bridges VDA5050 MQTT messages ↔ coordinator ingest/dispatch.

    Subscribes:
      - ``vda5050/+/+/state`` → ingest_uplink(brand, raw, now)
      - ``vda5050/+/+/connection`` → tracks online/offline, LWT

    Publishes:
      - TaskAssignment → ``vda5050/{mfr}/{sn}/order`` (VDA5050 order)
      - AdapterCommand   → ``vda5050/{mfr}/{sn}/instantActions`` (HOLD / RETREAT)
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "traffic-coordinator-v5",
        qos: int = 1,
    ) -> None:
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._client_id = client_id
        self._qos = qos
        self._client = None  # paho.mqtt.client.Client
        self._callback: Callable[[InboundMessage], None] | None = None
        self._connections: dict[str, RobotConnection] = {}
        self._lock = threading.Lock()
        self._running = False

    # ── lifecycle ────────────────────────────────────────────

    def start(self, callback: Callable[[InboundMessage], None]) -> None:
        self._callback = callback
        self._running = True
        self._connect()

    def stop(self) -> None:
        self._running = False
        if self._client is not None:
            with self._lock, contextlib.suppress(Exception):
                self._client.disconnect()
        self._callback = None

    def _connect(self) -> None:
        """Connect to MQTT broker and subscribe to VDA5050 topics."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning(
                "paho-mqtt not installed — MqttGateway running in no-op mode. "
                "Install with: pip install paho-mqtt"
            )
            return

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        # ── MQTT authentication (v5.x zero-trust) ──────────────
        mqtt_username = os.environ.get("MQTT_USERNAME", "")
        if mqtt_username:
            password = self._load_mqtt_password()
            if password:
                self._client.username_pw_set(mqtt_username, password)
                logger.info("MqttGateway: using MQTT auth for user %s", mqtt_username)
            else:
                logger.error(
                    "MqttGateway: MQTT_USERNAME is set but no password found "
                    "(set MQTT_PASSWORD or MQTT_PASSWORD_FILE). "
                    "Aborting connection — auth misconfiguration."
                )
                self._client = None
                return

        # ── TLS (off by default; enable with MQTT_USE_TLS=true) ─
        if os.environ.get("MQTT_USE_TLS", "false").lower() == "true":
            ca_cert = os.environ.get("MQTT_CA_CERT", "")
            client_cert = os.environ.get("MQTT_CLIENT_CERT", "")
            client_key = os.environ.get("MQTT_CLIENT_KEY", "")
            if ca_cert:
                self._client.tls_set(
                    ca_certs=ca_cert,
                    certfile=client_cert or None,
                    keyfile=client_key or None,
                )
                logger.info("MqttGateway: TLS enabled")
            else:
                logger.warning("MqttGateway: MQTT_USE_TLS=true but MQTT_CA_CERT not set")

        # Set Last Will: if TC goes down, operators see OFFLINE
        self._client.will_set(
            "vda5050/traffic-coordinator/connection",
            json.dumps({"state": "OFFLINE", "timestamp": self._iso_now()}),
            qos=1,
            retain=True,
        )

        try:
            self._client.connect(self._broker_host, self._broker_port, keepalive=10)
            self._client.loop_start()
            logger.info(
                "MqttGateway connected to %s:%s", self._broker_host, self._broker_port
            )
        except Exception:
            logger.exception("MqttGateway failed to connect to MQTT broker")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        rc_value = getattr(reason_code, "value", reason_code)
        if rc_value == 0:
            client.subscribe(VDA5050_STATE_TOPIC, qos=self._qos)
            client.subscribe(VDA5050_CONNECTION_TOPIC, qos=self._qos)
            # Announce TC online
            client.publish(
                "vda5050/traffic-coordinator/connection",
                json.dumps({"state": "ONLINE", "timestamp": self._iso_now()}),
                qos=1,
                retain=True,
            )
            logger.info("MqttGateway subscribed to VDA5050 topics")
        else:
            logger.error("MqttGateway connection failed, rc=%s", reason_code)

    def _on_disconnect(self, client, userdata, reason_code, properties=None) -> None:
        if self._running:
            logger.warning("MqttGateway disconnected (rc=%s), will retry on next tick", reason_code)

    # ── inbound: VDA5050 MQTT → coordinator ──────────────────

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning("MqttGateway: invalid JSON on %s", topic)
            return

        parsed = _parse_vda5050_topic(topic)
        if parsed is None:
            return

        manufacturer, serial_number = parsed
        now = time.monotonic()

        if topic.endswith("/connection"):
            self._handle_connection(manufacturer, serial_number, payload, now)
        elif topic.endswith("/state"):
            self._handle_state(manufacturer, serial_number, payload, now)

    def _handle_connection(
        self,
        manufacturer: str,
        serial_number: str,
        payload: dict,
        now: float,
    ) -> None:
        """Track connection LWT — ONLINE / OFFLINE / CONNECTIONBROKEN."""
        state = payload.get("connectionState", payload.get("state", "OFFLINE"))
        online = state.upper() == "ONLINE"
        robot_id = f"{manufacturer}_{serial_number}"
        with self._lock:
            conn = self._connections.setdefault(
                robot_id,
                RobotConnection(
                    robot_id=robot_id,
                    manufacturer=manufacturer,
                    serial_number=serial_number,
                ),
            )
            conn.online = online
            conn.last_seen = now
            if online:
                conn.boot_id = payload.get("bootId", payload.get("serialNumber", ""))

    def _handle_state(
        self, brand: str, serial_number: str, payload: dict, now: float
    ) -> None:
        """Forward VDA5050 state to coordinator via callback.

        The coordinator's internal robot_id is the VDA5050 serialNumber,
        not the manufacturer-prefixed connection key.
        """
        robot_id = serial_number
        # Stamp the robot_id onto the payload so adapters can find it, but only
        # if the VDA5050 message did not already provide it.
        payload.setdefault("robotId", robot_id)
        payload.setdefault("manufacturer", brand)

        if self._callback is not None:
            try:
                self._callback(InboundMessage(brand=brand, raw=payload, received_at=now))
            except Exception:
                logger.exception("MqttGateway: callback failed for %s", robot_id)

        with self._lock:
            conn_key = f"{brand}_{serial_number}"
            conn = self._connections.get(conn_key)
            if conn is not None:
                conn.last_seen = now

    # ── outbound: coordinator → VDA5050 MQTT ─────────────────

    def send(self, envelope: OutboundEnvelope) -> None:
        """Publish a TaskAssignment or AdapterCommand to the robot's MQTT topic."""
        if self._client is None:
            return

        if envelope.assignment is not None:
            self._send_order(envelope)
        if envelope.command is not None:
            self._send_instant_action(envelope)

    def _send_order(self, envelope: OutboundEnvelope) -> None:
        assignment = envelope.assignment
        if assignment is None:
            return

        # Build VDA5050 order from TaskAssignment
        order_id = assignment.task_id
        order = {
            "headerId": int(time.time() * 1000),
            "timestamp": self._iso_now(),
            "version": "2.0.0",
            "manufacturer": envelope.brand,
            "serialNumber": envelope.robot_id,
            "orderId": order_id,
            "orderUpdateId": 0,
            "nodes": [
                {"nodeId": lane_id, "sequenceId": i, "released": True}
                for i, lane_id in enumerate(assignment.path)
            ],
            "edges": [
                {
                    "edgeId": f"{assignment.path[i]}_{assignment.path[i + 1]}",
                    "sequenceId": i,
                    "released": True,
                }
                for i in range(len(assignment.path) - 1)
            ],
        }

        topic = ORDER_TOPIC.format(
            manufacturer=envelope.brand, serialNumber=envelope.robot_id
        )
        self._publish(topic, order)

        # Also emit traffic light state if present
        if assignment.traffic_state is not None:
            tl = assignment.traffic_state
            instant_action = {
                "headerId": int(time.time() * 1000),
                "timestamp": self._iso_now(),
                "version": "2.0.0",
                "manufacturer": envelope.brand,
                "serialNumber": envelope.robot_id,
                "actions": [
                    {
                        "actionType": "trafficLight",
                        "actionId": f"tl_{tl.intersection_id}",
                        "blockingType": "HARD",
                        "actionParameters": [
                            {"key": "intersection_id", "value": tl.intersection_id},
                            {"key": "color", "value": tl.color.name},
                            {"key": "valid_until", "value": str(tl.valid_until)},
                        ],
                    }
                ],
            }
            self._publish(
                INSTANT_ACTIONS_TOPIC.format(
                    manufacturer=envelope.brand, serialNumber=envelope.robot_id
                ),
                instant_action,
            )

    def _send_instant_action(self, envelope: OutboundEnvelope) -> None:
        cmd = envelope.command
        if cmd is None:
            return

        action_type = "cancelOrder"  # default
        action_params: list[dict] = [{"key": "reason", "value": cmd.reason}]

        if cmd.action == "RETREAT":
            action_type = "instantVelocity"
            action_params = [
                {"key": "linear_x", "value": str(cmd.cmd_vel.linear_x if cmd.cmd_vel else -0.2)},
                {"key": "angular_z", "value": str(cmd.cmd_vel.angular_z if cmd.cmd_vel else 0.0)},
                {"key": "metres", "value": str(cmd.metres)},
            ]
        elif cmd.action == "HOLD":
            action_type = "stopPause"
        elif cmd.action == "SPEED_CAP":
            action_type = "instantVelocity"
            action_params = [
                {"key": "max_speed", "value": str(cmd.metres)},
                {"key": "reason", "value": cmd.reason},
            ]

        payload = {
            "headerId": int(time.time() * 1000),
            "timestamp": self._iso_now(),
            "version": "2.0.0",
            "manufacturer": envelope.brand,
            "serialNumber": envelope.robot_id,
            "actions": [
                {
                    "actionType": action_type,
                    "actionId": f"{cmd.action}_{cmd.seq}",
                    "blockingType": "HARD",
                    "actionParameters": action_params,
                }
            ],
        }

        topic = INSTANT_ACTIONS_TOPIC.format(
            manufacturer=envelope.brand, serialNumber=envelope.robot_id
        )
        self._publish(topic, payload)

    def _publish(self, topic: str, payload: dict) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=self._qos)
        except Exception:
            logger.exception("MqttGateway failed to publish to %s", topic)

    @staticmethod
    def _iso_now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    # ── connection queries ───────────────────────────────────

    def online_robots(self) -> list[str]:
        with self._lock:
            return [r.robot_id for r in self._connections.values() if r.online]

    def connection_snapshot(self) -> dict[str, RobotConnection]:
        with self._lock:
            return dict(self._connections)

    def reap_stale_connections(self, max_age: float = 60.0) -> list[str]:
        """Return robot_ids unseen for > max_age seconds."""
        now = time.monotonic()
        stale: list[str] = []
        with self._lock:
            for rid, conn in list(self._connections.items()):
                if conn.online and now - conn.last_seen > max_age:
                    conn.online = False
                    stale.append(rid)
        return stale
