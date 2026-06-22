"""
SAP EWM Robot Dispatch Platform — SAP Bridge Main Application
Python FastAPI + pyrfc service for SAP EWM integration.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
