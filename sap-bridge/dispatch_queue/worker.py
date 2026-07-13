"""
Queue worker — polls Redis priority queue and dispatches orders to robots.
Features:
- Polls every 500ms for highest-priority order
- Assigns to available robot matching brand/type
- Exponential backoff on failure (1s, 2s, 4s, 8s, 16s, max 60s)
- Max 5 retries, then deadletter
- Crash recovery via processing set
"""

import logging
import os
import threading
import time

from models.order import OrderStatus, WarehouseOrder
from mqtt_publisher import get_publisher
from redis_client import redis_from_url
from services.order_service import OrderService
from strategies import get_registry

from .deadletter import DeadLetterHandler
from .priority_queue import PriorityQueue

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
POLL_INTERVAL = 0.5  # seconds
MAX_RETRIES = 5
MAX_BACKOFF = 60  # seconds
BACKOFF_BASE = 1  # seconds


class QueueWorker:
    """Background worker that polls the priority queue and dispatches orders.

    Runs in a daemon thread. Recovers stale processing items on start.
    """

    def __init__(self):
        self._queue = PriorityQueue()
        self._deadletter = DeadLetterHandler()
        self._order_service = OrderService()
        self._publisher = get_publisher()
        self._registry = get_registry()
        self._redis = redis_from_url(REDIS_URL, decode_responses=True)
        self._running = False
        self._thread: threading.Thread | None = None
        self._retry_count: dict[str, int] = {}  # order_no → retry count
        self._backoff_until: dict[str, float] = {}  # order_no → timestamp
        self._dispatch_callback = None  # For middleware/hooks
        self._metrics = {
            "dispatched": 0,
            "failed": 0,
            "deadlettered": 0,
            "recovered": 0,
        }

    # ── Lifecycle ──────────────────────────────────

    def start(self):
        """Start the worker thread."""
        if self._running:
            return

        # Recover stale processing items (crash recovery)
        reclaimed = self._queue.recover_stale_processing()
        if reclaimed:
            self._metrics["recovered"] += len(reclaimed)
            logger.info(f"Recovered {len(reclaimed)} stale items from processing set")

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="queue-worker")
        self._thread.start()
        logger.info("Queue worker started")

    def stop(self):
        """Stop the worker gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Queue worker stopped")

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)

    def set_dispatch_callback(self, callback):
        """Register a dispatch callback for middleware/hooks."""
        self._dispatch_callback = callback

    # ── Main loop ──────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Worker tick error: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)

    def _tick(self):
        """One poll cycle: dequeue → validate → dispatch."""
        item = self._queue.dequeue(timeout_ms=2000)
        if item is None:
            return

        order_no = item.get("order_no")
        if not order_no:
            return

        # Check if order is in backoff
        if order_no in self._backoff_until:
            if time.time() < self._backoff_until[order_no]:
                # Still in backoff — re-enqueue
                self._queue.enqueue(order_no, payload=item.get("payload"))
                return
            else:
                del self._backoff_until[order_no]

        # Load order from database (PostgreSQL)
        order = self._order_service.get_order(order_no)
        if order is None:
            logger.warning(f"Order {order_no} not found in DB, skipping")
            return

        if order.status != OrderStatus.CREATED:
            logger.debug(f"Order {order_no} already {order.status.value}, skipping")
            return

        # Dispatch
        success = self._dispatch(order, item)

        if success:
            self._metrics["dispatched"] += 1
            self._retry_count.pop(order_no, None)
        else:
            self._handle_failure(order, item)

    # ── Dispatch logic ─────────────────────────────

    def _dispatch(self, order: WarehouseOrder, queue_item: dict) -> bool:
        """Dispatch an order to the appropriate robot via MQTT."""
        manufacturer = order.robot_brand
        serial = order.robot_serial

        # Auto-resolve brand if not specified (batch orders from SAP may be unassigned)
        if not manufacturer or manufacturer == "UNKNOWN":
            manufacturer, serial = self._resolve_robot(order)
            if manufacturer is None:
                logger.warning(f"No available robot for order {order.order_no}")
                return False

        # Build VDA5050 order payload — payload comes first so orderId/orderUpdateId are authoritative
        payload = queue_item.get("payload") or order.payload or {}
        vda5050_payload = {
            **payload,
            "orderId": order.order_no,
            "orderUpdateId": 0,
        }

        try:
            mid = self._publisher.publish(
                manufacturer=manufacturer,
                serial_number=serial,
                topic_suffix="order",
                payload=vda5050_payload,
                qos=1,
            )
        except Exception as e:
            logger.error(f"MQTT publish failed for {order.order_no}: {e}")
            return False

        if mid is None:
            return False

        # Update order status
        self._order_service.assign_order(order.order_no, manufacturer, serial)
        self._order_service.start_execution(order.order_no)

        # Dispatch callback hook
        if self._dispatch_callback:
            try:
                self._dispatch_callback(order, mid)
            except Exception as e:
                logger.warning(f"Dispatch callback error: {e}")

        logger.info(f"Dispatched {order.order_no} → {manufacturer}/{serial} (mid={mid})")
        return True

    # ── Robot resolution ──────────────────────────

    def _resolve_robot(self, order: WarehouseOrder) -> tuple[str | None, str | None]:
        """Auto-assign a robot when order has no brand specified.

        Uses SCAN (non-blocking) to find connected robots in ON-line states,
        filters to brands registered in the strategy registry, and picks the
        best available one.

        Returns (manufacturer, serial) or (None, None) if none available.
        """
        registered_brands = set(b.lower() for b in self._registry.list_brands())
        candidates: list[tuple[str, str]] = []  # (manufacturer, serial)

        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(
                    cursor,
                    match="robot:connection:*",
                    count=50,
                )
                for key in keys:
                    data = self._redis.hgetall(key)
                    state = data.get("state", data.get("connectionState", "")).upper()
                    # Per VDA5050 §6.10: only IDLE and CHARGING can receive new orders.
                    # ONLINE is a connection state (not vehicle state) — skip connection-only records.
                    if state not in ("IDLE", "CHARGING"):
                        continue

                    manufacturer = data.get("manufacturer", "")
                    serial = data.get("serialNumber", "")

                    if manufacturer.lower() not in registered_brands:
                        continue

                    candidates.append((manufacturer, serial))

                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Failed to scan Redis for robots: {e}")
            return None, None

        if not candidates:
            logger.warning(f"No available robots found for order {order.order_no}")
            return None, None

        # Pick first available — future enhancement: load-based selection
        manufacturer, serial = candidates[0]
        logger.info(f"Auto-assigned order {order.order_no} → {manufacturer}/{serial}")
        return manufacturer, serial

    # ── Failure handling ───────────────────────────

    def _handle_failure(self, order: WarehouseOrder, queue_item: dict):
        """Handle dispatch failure with exponential backoff → deadletter."""
        order_no = order.order_no
        retries = self._retry_count.get(order_no, 0) + 1
        self._retry_count[order_no] = retries

        if retries >= MAX_RETRIES:
            # Deadletter
            self._deadletter.send(
                order_no=order_no,
                error_type="MAX_RETRIES_EXCEEDED",
                error_message=f"Failed after {retries} attempts",
                payload=queue_item,
                retry_count=retries,
            )
            self._order_service.fail_order(order_no, f"Deadlettered after {retries} retries")
            self._metrics["deadlettered"] += 1
            self._retry_count.pop(order_no, None)
            logger.error(f"Order {order_no} deadlettered after {retries} retries")
        else:
            # Exponential backoff
            delay = min(BACKOFF_BASE * (2 ** (retries - 1)), MAX_BACKOFF)
            self._backoff_until[order_no] = time.time() + delay
            self._queue.enqueue(order_no, priority=order.priority, payload=order.payload)
            self._metrics["failed"] += 1
            logger.warning(f"Order {order_no} retry {retries}/{MAX_RETRIES} in {delay}s")
