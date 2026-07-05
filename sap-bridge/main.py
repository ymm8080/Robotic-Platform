"""
SAP EWM / WM Robot Dispatch Platform — SAP Bridge Main Application
Python FastAPI + pyrfc service for multi-warehouse SAP integration.
Supports both SAP EWM (OData) and SAP Classic WM (RFC) via backend abstraction.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

# Shared Redis connection (avoid per-request from_url)
import redis as _redis_module
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dispatch_queue import DeadLetterHandler, PriorityQueue, QueueWorker
from metrics import (
    MetricsMiddleware,
    deadletter_unresolved,
    metrics_response,
    mqtt_connected,
    orders_completed,
    orders_created,
    orders_failed,
    queue_depth,
    redis_connected,
    sap_connected,
)
from mqtt_publisher import get_publisher
from strategies import get_registry
from strategies.registry import UnknownBrandError

_redis_client = _redis_module.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/1"),
    decode_responses=True,
)

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
    """Startup: connect MQTT + start queue worker + heartbeat monitor. Shutdown: stop gracefully."""
    publisher = get_publisher()
    publisher.connect()

    # Start heartbeat monitor (subscribes to robot connection/state MQTT topics)
    # Gracefully handles MQTT unavailability (tests, CI) — logs warning and continues
    try:
        from heartbeat_monitor import HeartbeatMonitor
        heartbeat = HeartbeatMonitor()
        heartbeat.start()
        app.state.heartbeat = heartbeat
    except Exception as e:
        logger.warning(f"Heartbeat monitor failed to start (MQTT unavailable?): {e}")
        app.state.heartbeat = None

    worker = QueueWorker()
    worker.start()
    app.state.worker = worker
    logger.info("SAP Bridge started (MQTT + queue worker + heartbeat)")
    yield
    if heartbeat is not None:
        heartbeat.stop()
    worker.stop()
    publisher.disconnect()
    logger.info("SAP Bridge stopped")


app = FastAPI(
    title="SAP EWM/WM Robot Bridge",
    version=os.getenv("RUNTIME_VERSION", "v4.1"),
    lifespan=lifespan,
)

# Register Prometheus metrics middleware
app.add_middleware(MetricsMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full traceback server-side, return generic error to client."""
    import traceback
    tb = traceback.format_exc()
    logger.error(f"Unhandled error on {request.method} {request.url.path}:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ──────────────────────────────────────────────
# Health endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — used by Docker healthcheck and Watchdog."""
    publisher = get_publisher()
    _mq_conn = publisher.is_connected
    _rd_conn = _check_redis()
    mqtt_connected.set(1 if _mq_conn else 0)
    redis_connected.set(1 if _rd_conn else 0)
    return {
        "status": "healthy",
        "version": os.getenv("RUNTIME_VERSION", "v4.1"),
        "mqtt_connected": _mq_conn,
        "redis_connected": _rd_conn,
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


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint — for Watchdog / Grafana scraping."""
    return metrics_response()


# ──────────────────────────────────────────────
# Robot status endpoint
# ──────────────────────────────────────────────

@app.get("/api/v1/robots/status")
async def robot_status():
    """Return all connected robots' status from Redis, normalized by brand strategy."""
    import json as json_mod

    keys = _redis_client.keys("robot:connection:*")
    registry = get_registry()
    robots = []
    for key in keys:
        data = _redis_client.hgetall(key)
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
# Dispatch API (v4.1: Strategy-pattern brand-specific dispatch)
# ──────────────────────────────────────────────


class DispatchRequest(BaseModel):
    """Request body for brand-specific order dispatch.

    v4.1: Routes order through the brand strategy pattern to build
    the correct protocol payload (VDA5050 / IOP / HAIQ / REST).
    """
    brand: str                          # Robot brand (e.g., "KUKA", "MiR")
    serialNumber: str                   # Robot serial number
    orderId: str                        # Unique order ID
    orderUpdateId: int = 0              # VDA5050 order update ID
    nodes: list = []                    # VDA5050 nodes
    edges: list = []                    # VDA5050 edges
    robotModel: str = ""                # For dual-protocol brands (Geek+, Hai)
    robotType: str = ""                 # For Hai ACR vs HaiPort
    protocol: str = ""                  # For Quicktron proprietary fallback
    taskType: str = "MOVE"              # IOP/HAIQ task type
    target: str = ""                    # Target location (IOP/HAIQ/proprietary)
    source: str = ""                    # Source location
    priority: int = 3


@app.post("/api/v1/dispatch")
async def dispatch_order(req: DispatchRequest):
    """Dispatch an order to a robot using the brand strategy pattern.

    v4.1: This endpoint replaces the legacy direct-MQTT-publish flow.
    It looks up the brand strategy, builds the protocol-specific payload
    via strategy.dispatch(), verifies VDA5050 version compatibility,
    then publishes to MQTT.

    Returns:
        200: Dispatch accepted with protocol payload
        501: Unknown brand (not registered in strategy registry)
        503: MQTT disconnected
    """
    if not get_publisher().is_connected:
        return JSONResponse(status_code=503, content={"error": "mqtt_disconnected"})

    registry = get_registry()

    # Strict brand lookup — raises UnknownBrandError for unregistered brands
    try:
        strategy = registry.get_or_raise(req.brand)
    except UnknownBrandError as e:
        logger.warning(f"Dispatch rejected: {e}")
        return JSONResponse(
            status_code=501,
            content={
                "error": "unknown_brand",
                "brand": e.brand,
                "availableBrands": e.available,
            },
        )

    # Version compatibility check (v4.1 verification matrix item 3)
    if not strategy.check_version_compatibility():
        return JSONResponse(
            status_code=422,
            content={
                "error": "version_incompatible",
                "brand": strategy.brand,
                "supportedVersions": strategy.supported_versions,
                "requiredVersion": ">=1.1.0",
            },
        )

    # Build the dispatch order dict for the strategy
    order = {
        "orderId": req.orderId,
        "orderUpdateId": req.orderUpdateId,
        "nodes": req.nodes,
        "edges": req.edges,
        "serialNumber": req.serialNumber,
        "robotModel": req.robotModel,
        "robotType": req.robotType,
        "protocol": req.protocol,
        "taskType": req.taskType,
        "target": req.target,
        "source": req.source,
        "priority": req.priority,
    }

    # Strategy builds the brand-specific protocol payload
    result = strategy.dispatch(order)

    if not result.success:
        return JSONResponse(
            status_code=400,
            content={"error": "dispatch_failed", "detail": result.error},
        )

    # Publish the payload to MQTT
    topic_suffix = "order" if result.protocol == "vda5050" else "command"
    mid = get_publisher().publish(
        manufacturer=req.brand,
        serial_number=req.serialNumber,
        topic_suffix=topic_suffix,
        payload=result.payload,
        qos=1,
    )

    orders_created.labels(type="DISPATCH").inc()
    logger.info(
        f"Dispatch {req.orderId} → {req.brand}/{req.serialNumber} "
        f"protocol={result.protocol} mid={mid}"
    )

    return {
        "status": "dispatched",
        "orderId": req.orderId,
        "brand": strategy.brand,
        "protocol": result.protocol,
        "mqttMid": mid,
        "payload": result.payload,
    }


# ──────────────────────────────────────────────
# Order API (via OrderService + MQTT publish)
# ──────────────────────────────────────────────

from models.order import OrderStatus, OrderType, WarehouseOrder
from services import OrderService

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

    # Validate order type
    order_type = None
    try:
        order_type = OrderType(req.orderType.upper())
    except ValueError:
        return JSONResponse(status_code=400, content={"error": f"invalid_order_type: {req.orderType}"})

    # Persist order via OrderService (PostgreSQL in production)
    order = WarehouseOrder(
        order_no=req.orderId,
        type=order_type,
        priority=min(3, max(0, req.priority)),
        source=req.source or None,
        robot_brand=req.manufacturer,
        robot_serial=req.serialNumber,
        payload=vda5050_payload,
    )
    _order_service.create_order(order)
    _order_service.assign_order(order.order_no, req.manufacturer, req.serialNumber)

    orders_created.labels(type=req.orderType).inc()

    logger.info(f"Order {req.orderId} → {req.manufacturer}/{req.serialNumber} (mid={mid})")
    return {"status": "accepted", "orderId": req.orderId, "mqttMid": mid, "record": order.to_dict()}


@app.get("/api/v1/orders")
async def list_orders(status: str = "", brand: str = "", limit: int = 50, offset: int = 0):
    """List orders with optional filters."""
    status_enum = None
    if status:
        try:
            status_enum = OrderStatus(status.upper())
        except ValueError:
            valid = [s.value for s in OrderStatus]
            return JSONResponse(status_code=400, content={"error": f"invalid_status: {status}. Valid: {valid}"})
    orders = _order_service.list_orders(
        status=status_enum,
        brand=brand or None,
        limit=limit,
        offset=offset,
    )
    return {"orders": [o.to_dict() for o in orders], "count": len(orders)}


@app.get("/api/v1/orders/queue")
async def order_queue_depth():
    """Return queue depth grouped by priority level."""
    all_orders = _order_service.list_orders(status=OrderStatus.CREATED, limit=1000)
    depth = {0: 0, 1: 0, 2: 0, 3: 0}
    for o in all_orders:
        depth[o.priority] = depth.get(o.priority, 0) + 1
    return {"queue": depth, "total": len(all_orders)}


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
    orders_completed.inc()
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/fail")
async def fail_order(order_no: str, req: UpdateOrderStatusRequest):
    """Mark order as failed with error message."""
    order = _order_service.fail_order(order_no, req.errorMessage or "Unknown error")
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    orders_failed.labels(reason=req.errorMessage[:32] if req.errorMessage else "unknown").inc()
    return order.to_dict()


@app.post("/api/v1/orders/{order_no}/suspend")
async def suspend_order(order_no: str, req: UpdateOrderStatusRequest):
    """Suspend an order (requires human intervention)."""
    order = _order_service.suspend_order(order_no, req.errorMessage or "Suspended by operator")
    if order is None:
        return JSONResponse(status_code=404, content={"error": "order_not_found_or_invalid_state"})
    return order.to_dict()


# ──────────────────────────────────────────────
# Outbox API (v4.1: Node-RED calls these instead of direct SQLite access)
# ──────────────────────────────────────────────


@app.get("/api/v1/outbox/pending")
async def outbox_pending(limit: int = 20):
    """Fetch pending outbox events for Node-RED outbox flow.

    Replaces: Node-RED direct DB access. All data now in PostgreSQL via sap-bridge HTTP API.
    """
    from db import connect

    conn = connect()
    try:
        rows = conn.execute(
            """SELECT id, order_id, event_type, payload, retry_count, created_at
               FROM outbox_events
               WHERE status = 'PENDING' AND retry_count < 5
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        # Parse payload JSON for each row
        import json as _json
        events = []
        for row in rows:
            d = dict(row) if not isinstance(row, dict) else row
            payload_raw = d.get("payload")
            d["payload"] = payload_raw if isinstance(payload_raw, (dict, list)) else (_json.loads(payload_raw) if payload_raw else {})
            events.append(d)
        return {"events": events, "count": len(events)}
    finally:
        conn.close()


class OutboxUpdateRequest(BaseModel):
    """Update outbox event status after SAP HTTP response."""
    status: str = "SENT"  # SENT | FAILED
    retry_count: int | None = None
    last_error: str = ""


@app.post("/api/v1/outbox/{event_id}/update")
async def outbox_update(event_id: int, req: OutboxUpdateRequest):
    """Update outbox event status after SAP callback.

    Replaces: Node-RED direct DB access.
    """
    from db import connect

    conn = connect()
    try:
        if req.status == "SENT":
            conn.execute(
                """UPDATE outbox_events
                   SET status = 'SENT', retry_count = retry_count + 1, sent_at = ?
                   WHERE id = ?""",
                (_now_iso(), event_id),
            )
        else:
            conn.execute(
                """UPDATE outbox_events
                   SET retry_count = retry_count + 1, last_error = ?
                   WHERE id = ? AND status = 'PENDING'""",
                (req.last_error[:500] if req.last_error else "", event_id),
            )
        conn.commit()

        # Check if deadletter needed
        row = conn.execute(
            "SELECT retry_count, status FROM outbox_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "event_not_found"})

        d = dict(row) if not isinstance(row, dict) else row
        needs_deadletter = d.get("retry_count", 0) >= 5 and d.get("status") != "SENT"
        return {
            "status": "updated",
            "eventId": event_id,
            "retryCount": d.get("retry_count", 0),
            "needsDeadletter": needs_deadletter,
        }
    finally:
        conn.close()


class OutboxDeadletterRequest(BaseModel):
    """Move an outbox event to dead letter queue."""
    error_type: str = "OUTBOX_RETRY_EXCEEDED"
    error_message: str = ""
    payload: dict | None = None


@app.post("/api/v1/outbox/{event_id}/deadletter")
async def outbox_deadletter(event_id: int, req: OutboxDeadletterRequest):
    """Move a failed outbox event to the dead letter queue.

    Replaces: Node-RED direct DB access.
    """
    import json as _json
    from db import connect

    conn = connect()
    try:
        # Insert into dead_letter_queue
        conn.execute(
            """INSERT INTO dead_letter_queue
               (original_id, error_type, error_message, payload, status, created_at)
               VALUES (?, ?, ?, ?, 'UNRESOLVED', ?)
               RETURNING id""",
            (
                str(event_id),
                req.error_type,
                req.error_message[:500],
                _json.dumps(req.payload) if req.payload else None,
                _now_iso(),
            ),
        )
        # Mark outbox event as FAILED
        conn.execute(
            "UPDATE outbox_events SET status = 'FAILED' WHERE id = ?",
            (event_id,),
        )
        conn.commit()
        return {"status": "deadlettered", "eventId": event_id}
    finally:
        conn.close()


@app.post("/api/v1/outbox")
async def outbox_create(order_id: int, event_type: str, payload: dict | None = None):
    """Create a new outbox event.

    Called by Node-RED when an order needs SAP synchronization.
    """
    import json as _json
    from db import connect

    conn = connect()
    try:
        cur = conn.execute(
            """INSERT INTO outbox_events
               (order_id, event_type, payload, status, retry_count, created_at)
               VALUES (?, ?, ?, 'PENDING', 0, ?)
               RETURNING id""",
            (order_id, event_type, _json.dumps(payload) if payload else None, _now_iso()),
        )
        conn.commit()
        event_id = cur.lastrowid
        return {"status": "created", "eventId": event_id, "orderId": order_id}
    finally:
        conn.close()


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


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
async def get_queue_depth():
    """Queue depth and health status."""
    depth = _priority_queue.depth()
    queue_depth.labels(priority="all").set(depth)
    return {
        "depth": depth,
        "healthy": _priority_queue.is_healthy,
    }


@app.get("/api/v1/admin/deadletter")
async def list_deadletter(limit: int = 50, offset: int = 0):
    """List deadletter items."""
    items = _deadletter_handler.list_all(limit=limit, offset=offset)
    unresolved = _deadletter_handler.count_unresolved()
    deadletter_unresolved.set(unresolved)
    return {"items": items, "count": len(items), "unresolved": unresolved}


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
# Batch submission endpoints
# ──────────────────────────────────────────────

from services.batch_service import BatchService

_batch_service = BatchService()


@app.post("/api/v1/orders/batch")
async def trigger_batch(warehouse: str = "WM01"):
    """Trigger batch collection from SAP EWM."""
    count = _batch_service.collect_and_submit(warehouse=warehouse)
    return {
        "status": "ok" if count > 0 else "no_tasks",
        "orders_created": count,
        "warehouse": warehouse,
    }


# ──────────────────────────────────────────────
# IDoc listener endpoint
# ──────────────────────────────────────────────

from services.idoc_listener import IdocListener

_idoc_listener = IdocListener()


@app.post("/api/v1/idoc")
async def receive_idoc(request: Request):
    """Receive SAP IDoc XML push, parse to warehouse tasks, enqueue."""
    raw = await request.body()
    xml_str = raw.decode("utf-8", errors="replace")
    result = _idoc_listener.process(xml_str)
    status = 202 if result.get("accepted") else 400
    return JSONResponse(content=result, status_code=status)


@app.get("/api/v1/idoc/stats")
async def idoc_stats():
    """IDoc processing statistics."""
    return {"stats": _idoc_listener.get_stats()}


@app.get("/api/v1/idoc/recent")
async def idoc_recent(n: int = 10):
    """Recent IDoc log entries."""
    return {"idocs": _idoc_listener.get_recent(n)}


@app.get("/api/v1/orders/batch/metrics")
async def batch_metrics():
    """Batch service metrics."""
    return {
        "status": "running" if _batch_service.is_running else "idle",
        "metrics": _batch_service.metrics,
    }


# ──────────────────────────────────────────────
# SAP EWM integration endpoints
# SAP integration endpoints (multi-warehouse via backend abstraction)



from backends.factory import get_backend_for, get_factory
from services.inventory_service import InventoryService

_inventory_service = InventoryService()


@app.get("/api/v1/sap/tasks")
async def list_sap_tasks(warehouse: str = "WM01", status: str = "0", top: int = 100):
    """Fetch open warehouse tasks from SAP (EWM or WM)."""
    backend = get_backend_for(warehouse)
    if backend is None:
        return JSONResponse(status_code=502, content={"error": f"no_backend_for_{warehouse}"})
    try:
        tasks = backend.list_tasks(warehouse=warehouse, status=status, top=top)
        return {
            "tasks": [
                {
                    "warehouse": t.warehouse,
                    "taskId": t.external_id,
                    "product": t.product,
                    "sourceBin": t.source_bin,
                    "destBin": t.dest_bin,
                    "targetQty": t.target_qty,
                    "status": t.status,
                    "batch": t.batch,
                    "processType": t.process_type,
                }
                for t in tasks
            ],
            "count": len(tasks),
        }
    except PermissionError as e:
        return JSONResponse(status_code=401, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"SAP connection failed: {str(e)}"})


@app.get("/api/v1/sap/tasks/{task_id}")
async def get_sap_task(task_id: str, warehouse: str = "WM01"):
    """Get a single warehouse task by ID (EWM or WM)."""
    backend = get_backend_for(warehouse)
    if backend is None:
        return JSONResponse(status_code=502, content={"error": f"no_backend_for_{warehouse}"})
    task = backend.get_task(warehouse, task_id)
    if task is None:
        return JSONResponse(status_code=404, content={"error": "task_not_found"})
    return {
        "warehouse": task.warehouse,
        "taskId": task.external_id,
        "taskItem": task.item_no,
        "product": task.product,
        "sourceBin": task.source_bin,
        "destBin": task.dest_bin,
        "targetQty": task.target_qty,
        "status": task.status,
        "batch": task.batch,
    }


@app.post("/api/v1/sap/tasks/{task_id}/confirm")
async def confirm_sap_task(task_id: str, warehouse: str = "WM01", qty: float | None = None):
    """Confirm warehouse task completion in SAP.

    Args:
        task_id: SAP warehouse task ID
        warehouse: Warehouse identifier
        qty: Confirmed quantity (None = confirm full planned qty)
    """
    backend = get_backend_for(warehouse)
    if backend is None:
        return JSONResponse(status_code=502, content={"error": f"no_backend_for_{warehouse}"})
    # None means "confirm all" — backends handle the interpretation
    ok = backend.confirm_task(warehouse, task_id, qty)
    if not ok:
        return JSONResponse(status_code=502, content={"error": "sap_confirm_failed"})
    return {"status": "confirmed", "taskId": task_id}


@app.post("/api/v1/sap/tasks/{task_id}/cancel")
async def cancel_sap_task(task_id: str, warehouse: str = "WM01"):
    """Cancel warehouse task in SAP."""
    backend = get_backend_for(warehouse)
    if backend is None:
        return JSONResponse(status_code=502, content={"error": f"no_backend_for_{warehouse}"})
    ok = backend.cancel_task(warehouse, task_id)
    if not ok:
        return JSONResponse(status_code=502, content={"error": "sap_cancel_failed"})
    return {"status": "cancelled", "taskId": task_id}


@app.get("/api/v1/sap/health")
async def sap_health():
    """SAP connectivity health check for all configured warehouses."""
    health = get_factory().health_check_all()
    any_connected = any(s.get("connected") for s in health.values())
    sap_connected.set(1 if any_connected else 0)
    return health


@app.get("/api/v1/inventory/{product}")
async def get_inventory(product: str, warehouse: str = "WM01"):
    """Get cached stock for a product."""
    qty = _inventory_service.get_stock(product, warehouse)
    if qty is None:
        return {"product": product, "warehouse": warehouse, "quantity": None, "cached": False}
    return {"product": product, "warehouse": warehouse, "quantity": qty, "cached": True}


@app.get("/api/v1/inventory")
async def list_inventory(warehouse: str = "WM01"):
    """Get all cached inventory for a warehouse."""
    stock = _inventory_service.get_all_stock(warehouse)
    return {"warehouse": warehouse, "items": stock, "count": len(stock)}


@app.post("/api/v1/inventory/sync")
async def sync_inventory(warehouse: str = "WM01"):
    """Trigger inventory cache refresh from SAP."""
    _inventory_service.clear_cache(warehouse)
    _inventory_service.mark_synced()
    return {"status": "synced", "warehouse": warehouse}


# ──────────────────────────────────────────────
# Robot Command API
# ──────────────────────────────────────────────


class RobotCommandRequest(BaseModel):
    action: str  # pause, resume, cancel_order, reboot
    orderId: str = ""


VALID_COMMANDS = {"pause", "resume", "cancel_order", "reboot"}

# Map commands to VDA5050 instantActions
COMMAND_ACTIONS: dict[str, dict] = {
    "pause": {
        "actionType": "startPause",
        "actionId": "pause-cmd",
        "blockingType": "HARD",
        "actionParameters": [{"key": "reason", "value": "operator_command"}],
    },
    "resume": {
        "actionType": "stopPause",
        "actionId": "resume-cmd",
        "blockingType": "HARD",
        "actionParameters": [],
    },
    "cancel_order": {
        "actionType": "cancelOrder",
        "actionId": "cancel-cmd",
        "blockingType": "HARD",
        "actionParameters": [],
    },
    "reboot": {
        "actionType": "startPause",
        "actionId": "reboot-cmd",
        "blockingType": "HARD",
        "actionParameters": [{"key": "reason", "value": "SERVICE_RESTART"}],
    },
}


@app.post("/api/v1/robots/{robot_id}/command")
async def robot_command(robot_id: str, req: RobotCommandRequest):
    """Send a command (pause/resume/cancel_order/reboot) to a robot via MQTT instantActions."""
    if req.action not in VALID_COMMANDS:
        return JSONResponse(
            status_code=400,
            content={"error": f"invalid_action: {req.action}. Valid: {sorted(VALID_COMMANDS)}"},
        )

    if not get_publisher().is_connected:
        return JSONResponse(status_code=503, content={"error": "mqtt_disconnected"})

    # robot_id format: "manufacturer/serialNumber" or "manufacturer-serialNumber"
    if "/" in robot_id:
        manufacturer, serial_number = robot_id.split("/", 1)
    elif "-" in robot_id:
        manufacturer, serial_number = robot_id.split("-", 1)
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_robot_id: use format 'manufacturer/serialNumber'"},
        )

    # Build instantActions payload
    action_template = COMMAND_ACTIONS.get(req.action, COMMAND_ACTIONS["pause"])
    instant_actions = [dict(action_template)]

    # Attach orderId to cancel_order if provided
    if req.action == "cancel_order" and req.orderId:
        instant_actions[0]["actionParameters"] = [
            {"key": "orderId", "value": req.orderId},
        ]

    mid = get_publisher().publish(
        manufacturer=manufacturer,
        serial_number=serial_number,
        topic_suffix="instantActions",
        payload={"instantActions": instant_actions},
        qos=1,
    )

    logger.info(f"Command '{req.action}' → {manufacturer}/{serial_number} (mid={mid})")
    return {
        "status": "sent",
        "robotId": robot_id,
        "action": req.action,
        "mqttMid": mid,
    }


@app.get("/api/v1/system/health")
async def system_health():
    """Aggregated system health — all services, resources, fleet summary."""
    import json as json_mod

    # SAP Bridge self-check
    mqtt_ok = get_publisher().is_connected
    redis_ok = _check_redis()

    # Fleet summary from Redis
    fleet = {"total": 0, "online": 0, "error": 0, "moving": 0, "idle": 0, "charging": 0}
    try:
        keys = _redis_client.keys("robot:connection:*")
        fleet["total"] = len(keys)
        for key in keys:
            data = _redis_client.hgetall(key)
            state = data.get("state", "").upper()
            if state == "ONLINE" and data.get("lastSeen"):
                fleet["online"] += 1
            if state in ("MOVING", "EXECUTING"):
                fleet["moving"] += 1
            elif state == "ERROR":
                fleet["error"] += 1
            elif state in ("CHARGING",):
                fleet["charging"] += 1
            elif state in ("IDLE", "ONLINE", "PAUSED"):
                fleet["idle"] += 1
    except Exception:
        pass

    # Try to reach Watchdog for extra metrics (optional, non-blocking)
    watchdog_ok = False
    watchdog_metrics = {}
    try:
        import asyncio
        wd_url = "http://watchdog:9090/metrics"
        # Run sync HTTP in thread pool to avoid blocking FastAPI event loop
        def _fetch_watchdog():
            import urllib.request
            req = urllib.request.Request(wd_url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json_mod.loads(resp.read().decode())
        wd_data = await asyncio.to_thread(_fetch_watchdog)
        watchdog_ok = True
        watchdog_metrics = {
            "safeMode": wd_data.get("safe_mode", False),
            "throttleActive": wd_data.get("throttle_active", False),
            "cpuPercent": wd_data.get("cpu_percent"),
            "memoryPercent": wd_data.get("memory_percent"),
            "errorRatePercent": wd_data.get("error_rate_percent"),
            "noderedStatus": wd_data.get("nodered_status"),
            "sapBridgeStatus": wd_data.get("sap_bridge_status"),
            "mqttStatus": wd_data.get("mqtt_status"),
        }
    except Exception:
        pass

    # DB health check
    db_ok = False
    try:
        _order_service.list_orders(limit=1)
        db_ok = True
    except Exception:
        pass

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "sapBridge": {"status": "healthy", "uptimeSeconds": _uptime()},
            "mqtt": {"status": "connected" if mqtt_ok else "disconnected", "connected": mqtt_ok},
            "redis": {"status": "connected" if redis_ok else "disconnected", "connected": redis_ok},
            "database": {"status": "connected" if db_ok else "error", "connected": db_ok},
            "watchdog": {"status": "reachable" if watchdog_ok else "unreachable", "connected": watchdog_ok},
        },
        "resources": watchdog_metrics,
        "fleet": fleet,
        "version": os.getenv("RUNTIME_VERSION", "v4.1"),
    }


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

_start_time = time.time()


def _uptime() -> int:
    return int(time.time() - _start_time)


def _check_redis() -> bool:
    try:
        return _redis_client.ping()
    except Exception:
        return False
