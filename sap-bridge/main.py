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
    """Startup: connect MQTT. Shutdown: disconnect gracefully."""
    publisher = get_publisher()
    publisher.connect()
    logger.info("SAP Bridge started")
    yield
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
    """Return all connected robots' status from Redis."""
    import redis
    r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True)
    keys = r.keys("robot:connection:*")
    robots = []
    for key in keys:
        data = r.hgetall(key)
        robots.append({
            "id": key.replace("robot:connection:", ""),
            "state": data.get("state", "UNKNOWN"),
            "lastSeen": data.get("lastSeen", ""),
            "battery": data.get("battery", ""),
        })
    return {"robots": robots, "count": len(robots)}


# ──────────────────────────────────────────────
# Order API (with in-memory fallback when Redis offline)
# ──────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    manufacturer: str
    serialNumber: str
    orderId: str
    nodes: list
    edges: list = []


# In-memory fallback when Redis is not available
_order_store: list[dict] = []
_order_store_max = 100


def _get_redis():
    """Get Redis client if available, else None."""
    try:
        import redis as rmod
        r = rmod.from_url(os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True)
        if r.ping():
            return r
    except Exception:
        pass
    return None


def _save_order(req: CreateOrderRequest, mid: int | None):
    """Persist order to Redis if available, else in-memory."""
    record = {
        "orderId": req.orderId,
        "manufacturer": req.manufacturer,
        "serialNumber": req.serialNumber,
        "status": "ASSIGNED",
        "nodes": __import__("json").dumps(req.nodes),
        "edges": __import__("json").dumps(req.edges),
        "createdAt": _iso_now(),
        "mqttMid": mid,
    }

    r = _get_redis()
    if r is not None:
        order_key = f"order:{req.orderId}"
        r.hset(order_key, mapping=record)
        r.expire(order_key, 86400 * 7)
        r.lpush("orders:recent", req.orderId)
        r.ltrim("orders:recent", 0, _order_store_max - 1)
    else:
        _order_store.insert(0, record)
        if len(_order_store) > _order_store_max:
            _order_store.pop()

    return record


@app.post("/api/v1/orders")
async def create_order(req: CreateOrderRequest):
    """Create a VDA5050 order and publish via MQTT."""
    if not get_publisher().is_connected:
        return JSONResponse(status_code=503, content={"error": "mqtt_disconnected"})

    payload = {
        "orderId": req.orderId,
        "orderUpdateId": 0,
        "nodes": req.nodes,
        "edges": req.edges,
    }

    mid = get_publisher().publish(
        manufacturer=req.manufacturer,
        serial_number=req.serialNumber,
        topic_suffix="order",
        payload=payload,
        qos=0,
    )

    record = _save_order(req, mid)
    logger.info(f"Order {req.orderId} → {req.manufacturer}/{req.serialNumber} (mid={mid})")
    return {"status": "accepted", "orderId": req.orderId, "mqttMid": mid, "record": record}


@app.get("/api/v1/orders")
async def list_orders(limit: int = 50):
    """List recent orders from Redis or in-memory fallback."""
    r = _get_redis()
    if r is not None:
        order_ids = r.lrange("orders:recent", 0, limit - 1)
        orders = []
        for oid in order_ids:
            data = r.hgetall(f"order:{oid}")
            if data:
                data["nodes"] = __import__("json").loads(data.get("nodes", "[]"))
                data["edges"] = __import__("json").loads(data.get("edges", "[]"))
                orders.append(data)
        return {"orders": orders, "count": len(orders)}
    else:
        return {"orders": _order_store[:limit], "count": min(len(_order_store), limit)}


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

_start_time = __import__("time").time()


def _uptime() -> int:
    return int(__import__("time").time() - _start_time)


@staticmethod
def _iso_now() -> str:
    return __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()


def _check_redis() -> bool:
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True)
        return r.ping()
    except Exception:
        return False
