"""
WCS Shadow Sandbox — Multi-Brand Zone Lock & Task Callback Mock v1.0

Design doc: v3.35 §改进十三 (WCS影子沙箱)
Purpose:
  - Mock WCS zone_lock API for negotiation leverage with vendors
  - Simulate brand-specific API deviations (timing, payload format)
  - Regression test baseline — verify Node-RED dispatch logic against known responses
  - Vendor blame evidence — prove when WCS API deviates from contract

Usage:
  uvicorn main:app --port 8100

TEST_TIMEOUT prefix: prepend to any order_id/robot_id to inject artificial delay
  e.g., "TEST_TIMEOUT_5000_R001" delays response by 5000ms
"""
import json
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("wcs-sandbox")

app = FastAPI(title="WCS Shadow Sandbox", version="1.0.0", docs_url="/docs")

# ── In-memory state ─────────────────────────────────────────────────────────
zone_locks: dict[str, dict] = {}         # zone_id → {robot_id, brand, zone_token, acquired_at}
task_callbacks: list[dict] = []           # historical callback log
brand_behaviors: dict[str, dict] = {}     # brand → config overrides

DEFAULT_BEHAVIORS = {
    "geekplus": {
        "zone_lock_support": True,
        "callback_delay_ms": 200,
        "response_format": "standard",
        "known_deviations": ["zone_token_missing_on_release"],
    },
    "hikrobot": {
        "zone_lock_support": True,
        "callback_delay_ms": 500,
        "response_format": "nested",
        "known_deviations": ["nested_response_wrapper", "slow_callback"],
    },
    "mir": {
        "zone_lock_support": False,  # MiR doesn't support zone lock
        "callback_delay_ms": 100,
        "response_format": "standard",
        "known_deviations": ["no_zone_lock"],
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _check_test_timeout(identifier: str):
    """If identifier starts with TEST_TIMEOUT_N, sleep N ms."""
    if identifier and identifier.startswith("TEST_TIMEOUT_"):
        parts = identifier.split("_")
        if len(parts) >= 3 and parts[2].isdigit():
            delay_ms = int(parts[2])
            logger.info(f"⏰ TEST_TIMEOUT: sleeping {delay_ms}ms")
            time.sleep(delay_ms / 1000.0)


def _make_response(success: bool, data: dict = None, error: str = None) -> dict:
    resp = {"success": success, "timestamp": datetime.now(timezone.utc).isoformat()}
    if data:
        resp.update(data)
    if error:
        resp["error"] = error
    return resp


# ── Models ──────────────────────────────────────────────────────────────────

class ZoneLockRequest(BaseModel):
    zone_id: str = Field(..., description="Zone identifier (e.g., CROSS_01)")
    robot_id: str = Field(..., description="Robot requesting the lock")
    brand: str = Field(..., description="Robot brand (geekplus/hikrobot/mir)")
    duration_seconds: int = Field(default=60, ge=10, le=3600)


class TaskStatusRequest(BaseModel):
    task_id: str
    status: str = Field(..., pattern="^(ACCEPTED|IN_PROGRESS|COMPLETED|FAILED)$")
    location: str = ""
    error_code: str = ""
    timestamp: str = ""


class BrandConfigRequest(BaseModel):
    zone_lock_support: bool = True
    callback_delay_ms: int = 200
    response_format: str = "standard"
    known_deviations: list[str] = Field(default_factory=list)


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "zone_locks": len(zone_locks), "callbacks": len(task_callbacks)}


# ── Zone Lock API (WCS must support per §供应商主权铁律) ────────────────────

@app.post("/api/zone_lock")
async def acquire_zone_lock(req: ZoneLockRequest):
    """Acquire a zone lock. Returns 423 if already locked by another robot.

    WCS must support this API per RFQ不可协商条款.
    """
    _check_test_timeout(req.robot_id)

    # Check brand support
    behavior = brand_behaviors.get(req.brand.lower(), DEFAULT_BEHAVIORS.get(req.brand.lower(), {}))
    if not behavior.get("zone_lock_support", True):
        logger.warning(f"⚠ {req.brand} attempted zone lock but brand does not support it")
        return JSONResponse(
            status_code=501,
            content=_make_response(False, error=f"Brand {req.brand} does not support zone_lock API"),
        )

    existing = zone_locks.get(req.zone_id)
    if existing:
        if existing["robot_id"] == req.robot_id:
            # Same robot — extend lock
            zone_locks[req.zone_id] = {
                **existing,
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": time.time() + req.duration_seconds,
            }
            return _make_response(True, data={"zone_token": existing["zone_token"], "extended": True})

        # Different robot — locked
        return JSONResponse(
            status_code=423,
            content=_make_response(False, data={
                "locked_by": existing["robot_id"],
                "locked_brand": existing["brand"],
                "acquired_at": existing.get("acquired_at"),
            }, error=f"Zone {req.zone_id} locked by {existing['robot_id']}"),
        )

    # Acquire
    zone_token = f"zt_{req.zone_id}_{req.robot_id}_{int(time.time())}"
    zone_locks[req.zone_id] = {
        "robot_id": req.robot_id,
        "brand": req.brand,
        "zone_token": zone_token,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": time.time() + req.duration_seconds,
    }
    logger.info(f"🔒 Zone lock acquired: {req.zone_id} → {req.robot_id} ({req.brand})")
    return _make_response(True, data={"zone_token": zone_token, "duration_s": req.duration_seconds})


@app.delete("/api/zone_lock/{zone_id}")
async def release_zone_lock(zone_id: str, robot_id: str = Query(...), zone_token: str = Query(...)):
    """Release a zone lock. Requires valid zone_token."""
    _check_test_timeout(robot_id)

    lock = zone_locks.get(zone_id)
    if not lock:
        return _make_response(True, data={"note": "zone not locked"})

    if lock["zone_token"] != zone_token:
        return JSONResponse(status_code=403, content=_make_response(False, error="invalid zone_token"))

    zone_locks[zone_id]["released_at"] = datetime.now(timezone.utc).isoformat()
    del zone_locks[zone_id]
    logger.info(f"🔓 Zone lock released: {zone_id} by {robot_id}")
    return _make_response(True, data={"zone_id": zone_id})


@app.get("/api/zone_lock/{zone_id}")
async def get_zone_lock(zone_id: str):
    """Check zone lock status."""
    lock = zone_locks.get(zone_id)
    if not lock:
        return _make_response(False, data={"zone_id": zone_id, "locked": False})
    return _make_response(True, data={
        "zone_id": zone_id,
        "locked": True,
        "robot_id": lock["robot_id"],
        "brand": lock["brand"],
        "acquired_at": lock.get("acquired_at"),
    })


# ── Task Callback API (标准化契约 §1) ──────────────────────────────────────

@app.post("/api/wcs/task_callback")
async def task_callback(req: TaskStatusRequest):
    """WCS task status callback — standardized format per 采购合同附件 §1.

    Standard fields: task_id, status, location, timestamp, error_code (max 5).
    """
    _check_test_timeout(req.task_id)
    # Simulate brand-specific delay
    behavior = brand_behaviors.get("default", DEFAULT_BEHAVIORS.get("geekplus", {}))
    delay = behavior.get("callback_delay_ms", 200)
    if req.task_id and req.task_id.startswith("TEST_TIMEOUT_"):
        pass  # already handled by _check_test_timeout
    else:
        time.sleep(delay / 1000.0)

    record = {
        "task_id": req.task_id,
        "status": req.status,
        "location": req.location,
        "timestamp": req.timestamp or datetime.now(timezone.utc).isoformat(),
        "error_code": req.error_code,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    task_callbacks.append(record)
    logger.info(f"📞 Task callback: {req.task_id} → {req.status}")
    return _make_response(True, data={"callback_id": len(task_callbacks)})


@app.get("/api/wcs/task_callbacks")
async def list_callbacks(limit: int = 50):
    """List recent task callbacks (for test verification)."""
    return {"callbacks": task_callbacks[-limit:], "count": min(len(task_callbacks), limit)}


# ── Brand Behavior Configuration ─────────────────────────────────────────────

@app.post("/api/admin/brand/{brand}/configure")
async def configure_brand(brand: str, config: BrandConfigRequest):
    """Override default behavior for a specific brand (for testing edge cases)."""
    brand_behaviors[brand.lower()] = config.model_dump()
    logger.info(f"⚙ Brand {brand} configured: {config.model_dump()}")
    return _make_response(True, data={"brand": brand, "config": config.model_dump()})


@app.get("/api/admin/brand/{brand}")
async def get_brand_config(brand: str):
    """Get current behavior config for a brand."""
    config = brand_behaviors.get(brand.lower(), DEFAULT_BEHAVIORS.get(brand.lower(), {}))
    return {"brand": brand, "config": config, "is_default": brand.lower() not in brand_behaviors}


@app.get("/api/admin/deviation-log")
async def deviation_log():
    """Return known brand API deviations for vendor blame evidence."""
    return {
        "deviations": [
            {"brand": b, "deviations": cfg.get("known_deviations", [])}
            for b, cfg in DEFAULT_BEHAVIORS.items()
        ]
    }


# ── Zone Lock Stress Test ───────────────────────────────────────────────────

@app.get("/api/admin/stress-test")
async def stress_test(count: int = 100, brand: str = "geekplus"):
    """Generate zone lock contention for k6/load testing."""
    results = {"acquired": 0, "rejected": 0, "errors": 0}
    for i in range(count):
        robot = f"STRESS-{brand}-{i:04d}"
        try:
            req = ZoneLockRequest(zone_id="STRESS_ZONE", robot_id=robot, brand=brand)
            resp = await acquire_zone_lock(req)
            # acquire_zone_lock returns a dict (via _make_response) on success/423,
            # or a JSONResponse on 501 (brand not supporting zone lock).
            if isinstance(resp, dict):
                if resp.get("success"):
                    results["acquired"] += 1
                else:
                    results["rejected"] += 1
            else:
                results["rejected"] += 1
        except Exception:
            results["errors"] += 1
    return {"results": results, "zones_locked": len(zone_locks)}
