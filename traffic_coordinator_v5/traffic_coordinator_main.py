"""v5.0 Traffic Coordinator HTTP service.

This service wires the ``core/`` platform loop to a small HTTP surface:

- ``GET /health`` — mode self-check.
- ``GET /version`` — supported protocol versions.
- ``POST /ingest/{brand}`` — submit a vendor-native robot state message.
- ``POST /order`` — submit a WMS/ERP order.
- ``POST /order/{order_id}/cancel`` — cancel an order.
- ``GET /state`` — platform state snapshot.
- ``GET /metrics`` — in-memory metrics snapshot.

It is intentionally transport-light; production will usually add MQTT/DDS
below or beside this HTTP control plane.
"""
from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.shadow_state_machine import ShadowStateMachine
from core.config import CoreConfig
from core.coordinator import RobotPlatformCoordinator
from core.governance.economic_model import EconomicModel
from core.governance.reputation_engine import ReputationEngine
from core.messages import ActionPrimitive, FleetState, Pose, RobotMode, TaskAssignment
from core.orders import Order
from core.platform.charger_reservation import ChargerReservation
from core.platform.failover_degrade import FailoverDegrade
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.platform.lift_manager import LiftManager
from core.platform.robot_as_obstacle import RobotAsObstacle
from core.safety.safe_distance import SafeDistanceCalculator
from core.scheduling.facility_manager import FacilityManager
from core.scheduling.task_allocator import TaskAllocator
from core.scheduling.traffic_light_controller import TrafficLightController
from core.survival.version_router import VersionRouter
from core.survival.worm_blackbox import WormBlackbox

CONFIG = CoreConfig()
MODE = os.environ.get("MODE", "PRODUCTION")
PORT = int(os.environ.get("TC_HTTP_PORT", "8000"))
TC_API_KEY_FILE = os.environ.get("TC_API_KEY_FILE", "/run/secrets/tc_api_key")


def _load_api_key() -> str:
    """Load Traffic Coordinator API key from Docker secret or env var."""
    from pathlib import Path

    key_path = Path(TC_API_KEY_FILE)
    if key_path.is_file():
        return key_path.read_text().strip()
    return os.environ.get("TC_API_KEY", "")


TC_API_KEY = _load_api_key()

# Input validation rules
_MAX_BODY_BYTES = 1_048_576  # 1 MB
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _check_auth(handler: BaseHTTPRequestHandler) -> bool:
    """Verify X-API-Key header for mutating endpoints."""
    if not TC_API_KEY:
        return True
    provided = handler.headers.get("X-API-Key", "")
    import secrets

    return secrets.compare_digest(TC_API_KEY, provided)


def _check_mode() -> list[str]:
    """Hard-coded production/demo mode self-check (灰犀牛 #18)."""
    if MODE not in ("PRODUCTION", "DEMO"):
        return [f"invalid mode {MODE!r}; must be PRODUCTION or DEMO"]
    return []


# Global coordinator instance. In production this would be backed by Redis/etcd.
COORDINATOR = RobotPlatformCoordinator()
# Seed a minimal demo map so the endpoints are usable out of the box.
COORDINATOR.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
COORDINATOR.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
COORDINATOR.register_intersection("X1")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args) -> None:  # noqa: ANN002
        # Suppress default logging noise in container.
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
            return json.loads(self.rfile.read(length).decode())
        except Exception:  # noqa: BLE001
            return None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            checks = _check_mode()
            self._json(
                503 if checks else 200,
                {
                    "status": "unhealthy" if checks else "healthy",
                    "mode": MODE,
                    "version": CONFIG.supported_versions[0],
                    "supported_versions": list(CONFIG.supported_versions),
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
        elif path in ("/state", "/metrics"):
            if not _check_auth(self):
                self._json(401, {"error": "unauthorized"})
                return
            if path == "/state":
                state = COORDINATOR.query_state()
                self._json(
                    200,
                    {
                        "locked_zones": state.locked_zones,
                        "pending_tasks": state.pending_tasks,
                        "active_assignments": state.active_assignments,
                        "pending_commands": state.pending_commands,
                        "metrics": state.metrics.__dict__,
                        "robots": {rid: {"mode": r.mode.name, "pose": (r.pose.x, r.pose.y)} for rid, r in state.robots.items()},
                    },
                )
            else:
                self._json(200, COORDINATOR.metrics.snapshot().__dict__)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        now = time.monotonic()

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
            COORDINATOR.tick(now)
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
            COORDINATOR.tick(now)
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
                COORDINATOR.tick(now)
                self._json(200, {"cancelled": ok})
                return

        self._json(404, {"error": "not found"})


def main() -> None:
    checks = _check_mode()
    if checks:
        raise RuntimeError(checks[0])

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"v5.0 Traffic Coordinator listening on 0.0.0.0:{PORT} mode={MODE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
