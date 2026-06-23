"""
SAP EWM Robot Dispatch Platform — SAP Bridge Main Application
Python FastAPI + pyrfc service for SAP EWM integration.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mqtt_publisher import get_publisher
from strategies import get_registry
from queue import QueueWorker, DeadLetterHandler, PriorityQueue

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# App lifecycle
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect MQTT + start queue worker. Shutdown: stop gracefully."""
    publisher = get_publisher()
    publisher.connect()
    worker = QueueWorker()
    worker.start()
    app.state.worker = worker
    logger.info("SAP Bridge started (MQTT + queue worker)")
    yield
    worker.stop()
    publisher.disconnect()
    logger.info("SAP Bridge stopped")


app = FastAPI(
    title="SAP EWM Robot Bridge",
    version=os.getenv("RUNTIME_VERSION", "v3.4"),
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log and return server errors for debugging."""
    import traceback
    tb = traceback.format_exc()
    logger.error(f"Unhandled error on {request.method} {request.url.path}:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "traceback": tb.split("\n")[-5:] if tb else []},
    )


# ──────────────────────────────────────────────
# Health endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — used by Docker healthcheck and Watchdog."""
    publisher = get_publisher()
    return {
        "status": "healthy",
        "version": os.getenv("RUNTIME_VERSION", "v3.4"),
        "mqtt_connected": publisher.is_connected,
        "redis_connected": _check_redis(),
        "uptime_seconds": _uptime(),
    }


@app.get("/ready")
async def ready():
    """Readiness check — returns 200 only when critical dependencies are ready."""
    if not get_publisher().is_connected:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "mqtt_disconnected"})
    return {"status": "ready"}


@app.get("/live")
async def live():
    """Liveness check — always returns 200. Process is alive."""
    return {"status": "alive"}


# ──────────────────────────────────────────────
# Robot status endpoint
# ──────────────────────────────────────────────

@app.get("/api/v1/robots/status")
async def robot_status():
    """Return all connected robots' status from Redis, normalized by brand strategy."""
    import redis
    import json as json_mod
    r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True)
    keys = r.keys("robot:connection:*")
    registry = get_registry()
    robots = []
    for key in keys:
        data = r.hgetall(key)
        robot_id = key.replace("robot:connection:", "")
        brand = data.get("brand", "UNKNOWN")

        # Normalize via brand strategy if raw_state is available
        strategy = registry.get(brand)
        if strategy and data.get("raw_state"):
            try:
                raw = json_mod.loads(data["raw_state"])
                normalized = strategy.handle_state(raw)
                state = normalized.status
                battery = f"{normalized.battery.percent:.0f}%"
            except Exception:
                state = data.get("state", "UNKNOWN")
                battery = data.get("battery", "")
        else:
            state = data.get("state", "UNKNOWN")
            battery = data.get("battery", "")

        robots.append({
            "id": robot_id,
            "brand": brand,
            "state": state,
            "lastSeen": data.get("lastSeen", ""),
            "battery": battery,
        })
    return {"robots": robots, "count": len(robots)}


@app.get("/api/v1/strategies")
async def list_strategies():
    """List all registered brand strategies and their quirks."""
    registry = get_registry()
    brands = []
    for name in registry.list_brands():
        strategy = registry.get(name)
        brands.append({
            "brand": strategy.brand,
            "supportedVersions": strategy.supported_versions,
            "quirks": [
                {"name": q.name, "description": q.description, "severity": q.severity}
                for q in strategy.get_quirks()
            ],
        })
    return {"strategies": brands, "count": len(brands)}


# ──────────────────────────────────────────────
# Order API (via OrderService + MQTT publish)
# ──────────────────────────────────────────────

from services import OrderService
from models.order import WarehouseOrder, OrderType, OrderStatus

_order_service = OrderService()


class CreateOrderRequest(BaseModel):
    manufacturer: str
    serialNumber: str
    orderId: str
    orderType: str = "MOVE"
    priority: int = 3
    nodes: list = []
    edges: list = []
    source: str = ""


class UpdateOrderStatusRequest(BaseModel):
    status: str
    errorMessage: str = ""


@app.post("/api/v1/orders")
async def create_order(req: CreateOrderRequest):
    """Create a VDA5050 order, persist, and publish via MQTT."""
    if not get_publisher().is_connected:
        return JSONResponse(status_code=503, content={"error": "mqtt_disconnected"})

    # Build VDA5050 payload
    vda5050_payload = {
        "orderId": req.orderId,
        "orderUpdateId": 0,
        "nodes": req.nodes,
        "edges": req.edges,
    }

    # Publish to MQTT first
    mid = get_publisher().publish(
        manufacturer=req.manufacturer,
        serial_number=req.serialNumber,
        topic_suffix="order",
        payload=vda5050_payload,
        qos=1,
    )

    # Persist order to SQLite via OrderService
    order = WarehouseOrder(
        order_no=req.orderId,
        type=OrderType(req.orderType.upper()),
        priority=min(3, max(0, req.priority)),
        source=req.source or None,
        robot_brand=req.manufacturer,
        robot_serial=req.serialNumber,
        payload=vda5050_payload,
    )
    _order_service.create_order(order)
    _order_service.assign_order(order.order_no, req.manufacturer, req.serialNumber)

    logger.info(f"Order {req.orderId} → {req.manufacturer}/{req.serialNumber} (mid={mid})")
    return {"status": "accepted", "orderId": req.orderId, "mqttMid": mid, "record": order.to_dict()}


@app.get("/api/v1/orders")
async def list_orders(status: str = "", brand: str = "", limit: int = 50, offset: int = 0):
    """List orders with optional filters."""
    status_enum = OrderStatus(status.upper()) if status else None
    orders = _order_service.list_orders(
        status=status_enum,
        brand=brand or None,
        limit=limit,
        offset=offset,
    )
    return {"orders": [o.to_dict() for o in orders], "count": len(orders)}


@app.get("/api/v1/orders/{order_no}")
async def get_order(order_no: str):
    """Get order by order number."""
    order = _order_service.get_order(order_no)
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found"})
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/cancel")
async def cancel_order(order_no: str):
    """Cancel an order."""
    order = _order_service.cancel_order(order_no)
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/complete")
async def complete_order(order_no: str):
    """Mark order as completed."""
    order = _order_service.complete_order(order_no)
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/fail")
async def fail_order(order_no: str, req: UpdateOrderStatusRequest):
    """Mark order as failed with error message."""
    order = _order_service.fail_order(order_no, req.errorMessage or "Unknown error")
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/suspend")
async def suspend_order(order_no: str, req: UpdateOrderStatusRequest):
    """Suspend an order (requires human intervention)."""
    order = _order_service.suspend_order(order_no, req.errorMessage or "Suspended by operator")
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    return order.to_dict()


@app.get("/api/v1/orders/queue")
async def order_queue_depth():
    """Return queue depth grouped by priority level."""
    all_orders = _order_service.list_orders(status=OrderStatus.CREATED, limit=1000)
    depth = {0: 0, 1: 0, 2: 0, 3: 0}
    for o in all_orders:
        depth[o.priority] = depth.get(o.priority, 0) + 1
    return {"queue": depth, "total": len(all_orders)}


# ──────────────────────────────────────────────
# Admin endpoints (queue, deadletter)
# ──────────────────────────────────────────────

_deadletter_handler = DeadLetterHandler()
_priority_queue = PriorityQueue()


@app.get("/api/v1/admin/queue/peek")
async def queue_peek(n: int = 10):
    """Peek at top N items in the dispatch queue."""
    items = _priority_queue.peek(n)
    return {"queue_depth": _priority_queue.depth(), "items": items}


@app.get("/api/v1/admin/queue/depth")
async def queue_depth():
    """Queue depth and health status."""
    return {
        "depth": _priority_queue.depth(),
        "healthy": _priority_queue.is_healthy,
    }


@app.get("/api/v1/admin/deadletter")
async def list_deadletter(limit: int = 50, offset: int = 0):
    """List deadletter items."""
    items = _deadletter_handler.list_all(limit=limit, offset=offset)
    return {"items": items, "count": len(items), "unresolved": _deadletter_handler.count_unresolved()}


@app.post("/api/v1/admin/deadletter/{dl_id}/resolve")
async def resolve_deadletter(dl_id: int, resolution: str = "MANUAL_FIX"):
    """Resolve a deadletter item."""
    ok = _deadletter_handler.resolve(dl_id, resolution)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "deadletter_not_found_or_already_resolved"})
    return {"status": "resolved", "id": dl_id}


@app.get("/api/v1/admin/worker/metrics")
async def worker_metrics(request: Request):
    """Queue worker metrics."""
    worker = getattr(request.app.state, "worker", None)
    if worker is None:
        return {"status": "not_running"}
    return {"status": "running", "metrics": worker.metrics}


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

_start_time = __import__("time").time()


def _uptime() -> int:
    return int(__import__("time").time() - _start_time)


def _check_redis() -> bool:
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True)
        return r.ping()
    except Exception:
        return False
