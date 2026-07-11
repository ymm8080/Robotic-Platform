"""v5.0 Traffic Coordinator — HTTP + MQTT dual-transport service.

This service wires the ``core/`` platform loop to both an HTTP control plane
and an MQTT transport layer (VDA5050).  The MQTT gateway subscribes to robot
state topics and publishes TaskAssignment / AdapterCommand back to robots.

HTTP endpoints:
  ``GET  /health``              — mode self-check + MQTT status
  ``GET  /version``             — supported protocol versions
  ``POST /ingest/{brand}``      — submit a vendor-native robot state message
  ``POST /order``               — submit a WMS/ERP order
  ``POST /order/{id}/cancel``   — cancel an order
  ``POST /estop``               — emergency stop (zone-level)
  ``POST /robot/{id}/recover``  — manual recovery
  ``POST /robot/{id}/progress`` — report waypoint reached
  ``POST /lane/{id}/block``     — block a lane + reroute
  ``POST /lane/{id}/unblock``   — unblock a lane
  ``GET  /state``               — platform state snapshot
  ``GET  /metrics``             — Prometheus exposition format

MQTT topics:
  Subscribe: vda5050/+/+/state, vda5050/+/+/connection
  Publish:   vda5050/{mfr}/{sn}/order, vda5050/{mfr}/{sn}/instantActions
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import pathlib
import re
import secrets
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

try:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
    from prometheus_client.core import CounterMetricFamily

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

from core.config import CoreConfig, WormConfig
from core.coordinator import RobotPlatformCoordinator
from core.gateway import InboundMessage, MqttGateway, OutboundEnvelope
from core.infra.state_store import LocalStateStore
from core.messages import ActionPrimitive
from core.orders import Order
from core.platform.fixed_lane_map import Lane
from traffic_coordinator_v5.bootstrap import bootstrap_adapters
from traffic_coordinator_v5.maps.loader import load_facility_map

_logger = logging.getLogger(__name__)

# ── WORM blackbox sink path ────────────────────────────────────
WORM_SINK_PATH = os.environ.get("WORM_SINK_PATH", "")
_config_worm = WormConfig()
if WORM_SINK_PATH:
    sink_path = pathlib.Path(WORM_SINK_PATH)
    sink_dir = sink_path.parent if sink_path.suffix == ".jsonl" else sink_path
    sink_dir.mkdir(parents=True, exist_ok=True)
    _config_worm = WormConfig(sink_dir=str(sink_dir))
# Cold-start staggered registration: default 5s in production, 0 disables.
_reg_stagger = float(os.environ.get("TC_REGISTRATION_STAGGER_SECONDS", "5.0"))
CONFIG = replace(
    CoreConfig(), worm=_config_worm, registration_stagger_seconds=_reg_stagger
)

MODE = os.environ.get("MODE", "PRODUCTION")
PORT = int(os.environ.get("TC_HTTP_PORT", "8000"))
TC_API_KEY_FILE = os.environ.get("TC_API_KEY_FILE", "/run/secrets/tc_api_key")

# MQTT config (from env; defaults match docker-compose Mosquitto service)
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_ENABLED = os.environ.get("MQTT_ENABLED", "1") != "0"

# Background tick interval (seconds) — ensures the platform loop advances
# even when no HTTP requests arrive.
TICK_INTERVAL = float(os.environ.get("TC_TICK_INTERVAL", "0.5"))

# Snapshot interval (seconds) — persist coordinator state for crash recovery.
SNAPSHOT_INTERVAL = float(os.environ.get("TC_SNAPSHOT_INTERVAL", "10.0"))
SNAPSHOT_KEY = "tc:snapshot:v5"


def _load_api_key() -> str:
    """Load Traffic Coordinator API key from Docker secret or env var."""
    from pathlib import Path

    key_path = Path(TC_API_KEY_FILE)
    if key_path.is_file():
        return key_path.read_text().strip()
    return os.environ.get("TC_API_KEY", "")


TC_API_KEY = _load_api_key()
# In PRODUCTION mode, require an API key unless explicitly overridden
# with TC_REQUIRE_AUTH=0 (e.g. for local development or testing).
TC_REQUIRE_AUTH = os.environ.get("TC_REQUIRE_AUTH", "1") != "0"
if not TC_API_KEY:
    if MODE == "PRODUCTION" and TC_REQUIRE_AUTH:
        raise RuntimeError(
            "TC_API_KEY not set. API authentication is required in PRODUCTION mode. "
            "Set TC_API_KEY or TC_API_KEY_FILE, or set TC_REQUIRE_AUTH=0 to disable."
        )
    logging.getLogger("tc").warning(
        "TC_API_KEY not set — API authentication disabled. "
        "Set TC_API_KEY or TC_API_KEY_FILE for production."
    )

_MAX_BODY_BYTES = 1_048_576  # 1 MB
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _check_auth(handler: BaseHTTPRequestHandler) -> bool:
    if not TC_API_KEY:
        return True
    provided = handler.headers.get("X-API-Key", "")
    return secrets.compare_digest(TC_API_KEY, provided)


def _check_mode() -> list[str]:
    if MODE not in ("PRODUCTION", "DEMO"):
        return [f"invalid mode {MODE!r}; must be PRODUCTION or DEMO"]
    return []


# ── Global coordinator + gateway ──────────────────────────────────
COORDINATOR = RobotPlatformCoordinator(config=CONFIG)
STATE_STORE = LocalStateStore()

# Prometheus metrics registry (uses prometheus_client if available)
if _PROMETHEUS_AVAILABLE:
    class _CoreMetricsCollector:
        """Custom Prometheus collector bridging CoreMetrics to prometheus_client."""

        def collect(self):
            snap = COORDINATOR.metrics.snapshot()
            yield CounterMetricFamily(
                "tc_uplinks_total", "Total robot state uplinks received", snap.uplinks
            )
            yield CounterMetricFamily(
                "tc_orders_submitted_total", "Total orders submitted", snap.orders_submitted
            )
            yield CounterMetricFamily(
                "tc_tasks_allocated_total", "Total tasks allocated to robots", snap.tasks_allocated
            )
            yield CounterMetricFamily(
                "tc_tasks_completed_total", "Total tasks completed by robots", snap.tasks_completed
            )
            yield CounterMetricFamily(
                "tc_tasks_requeued_total", "Total tasks requeued due to failures", snap.tasks_requeued
            )
            yield CounterMetricFamily(
                "tc_collision_holds_total", "Total collision hold events", snap.collision_holds
            )
            yield CounterMetricFamily(
                "tc_deadlocks_total", "Total deadlock detections", snap.deadlocks
            )
            yield CounterMetricFamily(
                "tc_adapter_parse_errors_total", "Total adapter parse errors", snap.adapter_parse_errors
            )
            yield CounterMetricFamily(
                "tc_worm_records_total", "Total WORM audit records written", snap.worm_records
            )

    _prom_registry = CollectorRegistry()
    _prom_registry.register(_CoreMetricsCollector())

# Create the MQTT gateway (no-op if paho-mqtt is not installed)
MQTT_GATEWAY = MqttGateway(
    broker_host=MQTT_BROKER_HOST,
    broker_port=MQTT_BROKER_PORT,
    client_id="traffic-coordinator-v5",
)


def _on_mqtt_inbound(msg: InboundMessage) -> None:
    """Called by MqttGateway for each VDA5050 state/connection message.

    Routes the raw message through the coordinator's ingest_uplink pipeline
    which handles brand-adapter translation, state storage, obstacle updates,
    and cold-start registration.
    """
    COORDINATOR.ingest_uplink(msg.brand, msg.raw, msg.received_at)


def _publish_tick_result(result) -> None:
    """Emit assignments and commands from a tick result via MQTT."""
    for robot_id, assignment in result.assignments:
        adapter = COORDINATOR._robot_adapter.get(robot_id)
        brand = adapter.brand if adapter is not None else "generic"
        MQTT_GATEWAY.send(
            OutboundEnvelope(robot_id=robot_id, brand=brand, assignment=assignment)
        )

    for cmd in result.commands:
        adapter = COORDINATOR._robot_adapter.get(cmd.robot_id)
        brand = adapter.brand if adapter is not None else "generic"
        MQTT_GATEWAY.send(
            OutboundEnvelope(robot_id=cmd.robot_id, brand=brand, command=cmd)
        )


def _background_tick(stop_event: threading.Event) -> None:
    """Periodic platform tick + MQTT flush loop.

    Runs as a daemon thread so it exits cleanly when the HTTP server stops.
    Also periodically snapshots coordinator state for crash recovery.
    """
    last_snapshot = 0.0
    _snap_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="snapshot",
    )
    while not stop_event.is_set():
        now = time.monotonic()
        result = COORDINATOR.tick(now)
        _publish_tick_result(result)
        if now - last_snapshot >= SNAPSHOT_INTERVAL:
            try:
                snap = COORDINATOR.snapshot()
                _snap_executor.submit(_save_snapshot, snap)
                last_snapshot = now
            except Exception as exc:
                _logger.warning("[snapshot] submit failed: %s", exc)
        stop_event.wait(TICK_INTERVAL)
    _snap_executor.shutdown(wait=True)


def _save_snapshot(snapshot_data) -> None:
    """Save snapshot in background thread to avoid blocking tick loop."""
    try:
        STATE_STORE.set(SNAPSHOT_KEY, snapshot_data)
    except Exception as exc:
        _logger.warning("[snapshot] save failed: %s", exc)


# ── Bootstrap: load facility map and register adapters ───────────
MAP_PATH = os.environ.get("TC_MAP_PATH", "")
facility = load_facility_map(MAP_PATH if MAP_PATH else None)

if facility.warnings:
    for w in facility.warnings:
        print(f"[bootstrap] WARNING: {w}")

if facility.fmap.all_lanes():
    print(
        f"[bootstrap] loaded facility '{facility.facility_name}' "
        f"with {len(facility.fmap.all_lanes())} lanes, "
        f"{len(facility.intersections)} intersections"
    )
    for lane in facility.fmap.all_lanes():
        COORDINATOR.add_lane(lane)
    for iid in facility.intersections:
        COORDINATOR.register_intersection(iid)
    for cid in facility.charger_ids:
        COORDINATOR.register_charger(cid)
    for lift in facility.lift_ids:
        COORDINATOR.register_lift(lift["id"])
else:
    print("[bootstrap] no map loaded; seeding DEMO fallback (A->B->C, X1)")
    COORDINATOR.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
    COORDINATOR.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
    COORDINATOR.register_intersection("X1")

# Register brand adapters (VDA5050 with real strategies + generic fallback)
REGISTERED_ADAPTERS = bootstrap_adapters(COORDINATOR)

# Restore coordinator state from previous run (crash recovery)
_saved = STATE_STORE.get(SNAPSHOT_KEY)
if _saved is not None:
    try:
        COORDINATOR.restore(_saved)
        _logger.info("Restored coordinator state from snapshot")
    except Exception:
        _logger.exception("Snapshot restore failed — starting fresh")
else:
    _logger.info("No prior snapshot found — starting fresh")

# Start MQTT gateway + background ticker
_TICK_STOP = threading.Event()
_TICK_THREAD: threading.Thread | None = None

if MQTT_ENABLED:
    MQTT_GATEWAY.start(_on_mqtt_inbound)
    _TICK_THREAD = threading.Thread(
        target=_background_tick, args=(_TICK_STOP,), daemon=True, name="tc-tick-loop"
    )
    _TICK_THREAD.start()
    print(
        f"[mqtt] gateway started — broker={MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}, "
        f"tick_interval={TICK_INTERVAL}s"
    )
else:
    print("[mqtt] gateway disabled (MQTT_ENABLED=0)")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args) -> None:
        pass

    def _json(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body, default=str).encode())

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            if length > _MAX_BODY_BYTES:
                return None
            raw_body = self.rfile.read(length)
            return json.loads(raw_body.decode())
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json body"})
            return None
        except (ConnectionError, TimeoutError) as e:
            self.log_error("Error reading request body: %s", e)
            return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            checks = _check_mode()
            mqtt_online = MQTT_GATEWAY._client is not None if MQTT_ENABLED else False
            self._json(
                503 if checks else 200,
                {
                    "status": "unhealthy" if checks else "healthy",
                    "mode": MODE,
                    "version": CONFIG.supported_versions[0],
                    "supported_versions": list(CONFIG.supported_versions),
                    "mqtt": "connected" if mqtt_online else "disabled",
                    "online_robots": MQTT_GATEWAY.online_robots(),
                    "checks": checks,
                },
            )
        elif path == "/version":
            self._json(
                200,
                {
                    "version": CONFIG.supported_versions[0],
                    "supported_versions": list(CONFIG.supported_versions),
                },
            )
        elif path == "/state":
            if not _check_auth(self):
                self._json(401, {"error": "unauthorized"})
                return
            state = COORDINATOR.query_state()
            self._json(
                200,
                {
                    "locked_zones": state.locked_zones,
                    "pending_tasks": state.pending_tasks,
                    "active_assignments": state.active_assignments,
                    "pending_commands": state.pending_commands,
                    "metrics": state.metrics.__dict__,
                    "robots": {
                        rid: {"mode": r.mode.name, "pose": (r.pose.x, r.pose.y)}
                        for rid, r in state.robots.items()
                    },
                },
            )
        elif path == "/metrics":
            # /metrics is intentionally unauthenticated so that Prometheus
            # can scrape it without API key configuration.  In production,
            # restrict network access at the infrastructure level (e.g.
            # Docker network, firewall rules, or METRICS_ALLOWED_IPS).
            if _PROMETHEUS_AVAILABLE:
                output = generate_latest(_prom_registry)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(output)
            else:
                # Fallback: manual Prometheus text format
                # (used only when prometheus_client is not installed)
                snap = COORDINATOR.metrics.snapshot()
                lines = [
                    "# HELP tc_uplinks_total Total robot state uplinks received",
                    "# TYPE tc_uplinks_total counter",
                    f"tc_uplinks_total {snap.uplinks}",
                    "# HELP tc_orders_submitted_total Total orders submitted",
                    "# TYPE tc_orders_submitted_total counter",
                    f"tc_orders_submitted_total {snap.orders_submitted}",
                    "# HELP tc_tasks_allocated_total Total tasks allocated to robots",
                    "# TYPE tc_tasks_allocated_total counter",
                    f"tc_tasks_allocated_total {snap.tasks_allocated}",
                    "# HELP tc_tasks_completed_total Total tasks completed by robots",
                    "# TYPE tc_tasks_completed_total counter",
                    f"tc_tasks_completed_total {snap.tasks_completed}",
                    "# HELP tc_tasks_requeued_total Total tasks requeued due to failures",
                    "# TYPE tc_tasks_requeued_total counter",
                    f"tc_tasks_requeued_total {snap.tasks_requeued}",
                    "# HELP tc_collision_holds_total Total collision hold events",
                    "# TYPE tc_collision_holds_total counter",
                    f"tc_collision_holds_total {snap.collision_holds}",
                    "# HELP tc_deadlocks_total Total deadlock detections",
                    "# TYPE tc_deadlocks_total counter",
                    f"tc_deadlocks_total {snap.deadlocks}",
                    "# HELP tc_adapter_parse_errors_total Total adapter parse errors",
                    "# TYPE tc_adapter_parse_errors_total counter",
                    f"tc_adapter_parse_errors_total {snap.adapter_parse_errors}",
                    "# HELP tc_worm_records_total Total WORM audit records written",
                    "# TYPE tc_worm_records_total counter",
                    f"tc_worm_records_total {snap.worm_records}",
                ]
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.end_headers()
                self.wfile.write("\n".join(lines).encode())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        now = time.monotonic()

        # All POST endpoints require authentication — including /estop,
        # /robot/{id}/recover, /lane/{id}/block, /order, /ingest/*, etc.
        if not _check_auth(self):
            self._json(401, {"error": "unauthorized"})
            return

        body = self._read_json()
        if body is None:
            self._json(400, {"error": "invalid json"})
            return

        if path.startswith("/ingest/"):
            brand = path.split("/", 2)[2]
            if not _SAFE_ID_RE.match(brand):
                self._json(400, {"error": "invalid brand identifier"})
                return
            events = COORDINATOR.ingest_uplink(brand, body, now)
            result = COORDINATOR.tick(now)
            _publish_tick_result(result)
            self._json(200, {"events": events})
            return

        if path == "/order":
            order_id = body.get("order_id", "")
            if not _SAFE_ID_RE.match(order_id):
                self._json(400, {"error": "invalid order_id"})
                return
            raw_actions = body.get("actions", ["MOVE"])
            try:
                actions = [ActionPrimitive[a] for a in raw_actions]
            except KeyError as e:
                self._json(400, {"error": f"invalid_action: {e}"})
                return
            order = Order(
                order_id=order_id,
                origin_lane=body.get("origin_lane", ""),
                destination_lane=body.get("destination_lane", ""),
                actions=actions,
                payload_kg=body.get("payload_kg", 0.0),
                priority=body.get("priority", 0),
            )
            plan = COORDINATOR.submit_order(order)
            result = COORDINATOR.tick(now)
            _publish_tick_result(result)
            self._json(
                200,
                {
                    "order_id": order.order_id,
                    "status": plan.order.status.name,
                    "tasks": [t.task_id for t in plan.tasks],
                },
            )
            return

        if path.startswith("/order/") and path.endswith("/cancel"):
            parts = path.split("/")
            if len(parts) == 4:
                order_id = parts[2]
                if not _SAFE_ID_RE.match(order_id):
                    self._json(400, {"error": "invalid order_id"})
                    return
                ok = COORDINATOR.cancel_order(order_id, now)
                result = COORDINATOR.tick(now)
                _publish_tick_result(result)
                self._json(200, {"cancelled": ok})
                return

        if path == "/estop":
            zone_id = body.get("zone_id", "")
            if zone_id and not _SAFE_ID_RE.match(zone_id):
                self._json(400, {"error": "invalid zone_id"})
                return
            COORDINATOR.emergency_stop(zone_id or None, now)
            result = COORDINATOR.tick(now)
            _publish_tick_result(result)
            self._json(200, {"estop": True, "zone": zone_id})
            return

        if path.startswith("/robot/") and path.endswith("/recover"):
            parts = path.split("/")
            if len(parts) == 4:
                robot_id = parts[2]
                if not _SAFE_ID_RE.match(robot_id):
                    self._json(400, {"error": "invalid robot_id"})
                    return
                COORDINATOR.manual_recover(robot_id, now)
                result = COORDINATOR.tick(now)
                _publish_tick_result(result)
                self._json(200, {"recovered": robot_id})
                return

        if path.startswith("/robot/") and path.endswith("/progress"):
            parts = path.split("/")
            if len(parts) == 4:
                robot_id = parts[2]
                if not _SAFE_ID_RE.match(robot_id):
                    self._json(400, {"error": "invalid robot_id"})
                    return
                reached_lane = body.get("reached_lane", "")
                if not _SAFE_ID_RE.match(reached_lane):
                    self._json(400, {"error": "invalid reached_lane"})
                    return
                completed = COORDINATOR.report_progress(robot_id, reached_lane, now)
                result = COORDINATOR.tick(now)
                _publish_tick_result(result)
                self._json(200, {"robot_id": robot_id, "reached_lane": reached_lane, "assignment_completed": completed})
                return

        if path.startswith("/lane/") and path.endswith("/block"):
            parts = path.split("/")
            if len(parts) == 4:
                lane_id = parts[2]
                if not _SAFE_ID_RE.match(lane_id):
                    self._json(400, {"error": "invalid lane_id"})
                    return
                COORDINATOR.block_lane(lane_id, now)
                result = COORDINATOR.tick(now)
                _publish_tick_result(result)
                self._json(200, {"blocked": lane_id})
                return

        if path.startswith("/lane/") and path.endswith("/unblock"):
            parts = path.split("/")
            if len(parts) == 4:
                lane_id = parts[2]
                if not _SAFE_ID_RE.match(lane_id):
                    self._json(400, {"error": "invalid lane_id"})
                    return
                COORDINATOR.unblock_lane(lane_id, now)
                result = COORDINATOR.tick(now)
                _publish_tick_result(result)
                self._json(200, {"unblocked": lane_id})
                return

        self._json(404, {"error": "not found"})


def main() -> None:
    checks = _check_mode()
    if checks:
        raise RuntimeError(checks[0])

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print(f"v5.0 Traffic Coordinator listening on 0.0.0.0:{PORT} mode={MODE}")
    try:
        server.serve_forever()
    finally:
        _TICK_STOP.set()
        if _TICK_THREAD is not None:
            _TICK_THREAD.join(timeout=2.0)
        MQTT_GATEWAY.stop()


if __name__ == "__main__":
    main()
