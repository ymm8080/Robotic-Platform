"""
SAP Bridge Prometheus metrics module.
Exposes /metrics endpoint for Prometheus scraping.

Metrics:
  sap_bridge_orders_created_total    — Orders created (counter)
  sap_bridge_orders_completed_total  — Orders completed (counter)
  sap_bridge_orders_failed_total     — Orders failed (counter)
  sap_bridge_mqtt_connected          — MQTT broker connected (gauge)
  sap_bridge_redis_connected         — Redis connected (gauge)
  sap_bridge_queue_depth             — Dispatch queue depth (gauge)
  sap_bridge_deadletter_unresolved   — Unresolved dead letters (gauge)
  sap_bridge_http_requests_total     — HTTP requests by method+path+status (counter)
  sap_bridge_sap_connected           — SAP EWM connected (gauge)
  sap_bridge_uptime_seconds          — Process uptime (counter)
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ─── Metrics ───────────────────────────────────────────────────────────────

_start_time = time.time()

orders_created = Counter(
    "sap_bridge_orders_created_total",
    "Total orders created",
    labelnames=["type"],
)

orders_completed = Counter(
    "sap_bridge_orders_completed_total",
    "Total orders completed",
)

orders_failed = Counter(
    "sap_bridge_orders_failed_total",
    "Total orders failed",
    labelnames=["reason"],
)

mqtt_connected = Gauge(
    "sap_bridge_mqtt_connected",
    "MQTT broker connection status (1=connected, 0=disconnected)",
)

redis_connected = Gauge(
    "sap_bridge_redis_connected",
    "Redis connection status (1=connected, 0=disconnected)",
)

sap_connected = Gauge(
    "sap_bridge_sap_connected",
    "SAP EWM connection status (1=connected, 0=disconnected)",
)

queue_depth = Gauge(
    "sap_bridge_queue_depth",
    "Dispatch queue depth",
    labelnames=["priority"],
)

deadletter_unresolved = Gauge(
    "sap_bridge_deadletter_unresolved",
    "Number of unresolved dead letter items",
)

http_requests = Counter(
    "sap_bridge_http_requests_total",
    "Total HTTP requests by method, path, and status code",
    labelnames=["method", "path", "status"],
)

uptime = Counter(
    "sap_bridge_uptime_seconds",
    "Process uptime in seconds",
)

# ─── Middleware ────────────────────────────────────────────────────────────

class MetricsMiddleware(BaseHTTPMiddleware):
    """Counts every HTTP request by method, path, and status code."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Skip metrics endpoint itself to avoid infinite recursion
        if request.url.path != "/metrics":
            # Normalize path to route template to prevent unbounded cardinality
            path = request.scope.get("route", None)
            route_path = getattr(path, "path", request.url.path) if path else request.url.path
            http_requests.labels(
                method=request.method,
                path=route_path,
                status=response.status_code,
            ).inc()
        return response


# ─── Endpoint Helper ───────────────────────────────────────────────────────

def metrics_response() -> Response:
    """Generate a Prometheus-formatted metrics response."""
    delta = time.time() - _start_time - uptime._value.get()
    if delta > 0:
        uptime.inc(delta)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-cache"},
    )
