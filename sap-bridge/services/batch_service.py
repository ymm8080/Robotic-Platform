"""
Batch order submission service.
Collects pending warehouse tasks from SAP (EWM or WM) and submits as VDA5050 orders.
Uses the WarehouseBackend factory — backend type is selected per warehouse from config.
"""
import logging
import os
import time

from backends.factory import get_backend_for
from dispatch_queue import PriorityQueue
from models.order import OrderType, WarehouseOrder
from models.warehouse_task import WarehouseTask

from .order_service import OrderService

logger = logging.getLogger(__name__)

BATCH_INTERVAL = int(os.getenv("BATCH_INTERVAL_SECONDS", "60"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
DEFAULT_WAREHOUSE = os.getenv("SAP_DEFAULT_WAREHOUSE", "WM01")


class BatchService:
    """Polls SAP (EWM or WM) for pending warehouse tasks and submits as orders.

    Backend type is auto-selected from config per warehouse:
      - ewm → SAP EWM OData
      - wm  → SAP Classic WM RFC

    Runs as a periodic task. Each batch of tasks is submitted to the
    dispatch priority queue with staggered timing.
    """

    def __init__(self):
        self._orders = OrderService()
        self._queue = PriorityQueue()
        self._last_run = 0.0
        self._running = False
        self._metrics = {
            "batches_submitted": 0,
            "orders_created": 0,
            "errors": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)

    # ── Public API ─────────────────────────────────────

    def collect_and_submit(self, warehouse: str = DEFAULT_WAREHOUSE) -> int:
        """Collect pending SAP tasks and submit as orders.

        Returns number of orders created.
        """
        # Throttle check
        now = time.time()
        if now - self._last_run < BATCH_INTERVAL:
            return 0

        # Get backend for this warehouse
        backend = get_backend_for(warehouse)
        if backend is None:
            logger.error(f"No backend configured for warehouse '{warehouse}'")
            self._metrics["errors"] += 1
            return 0

        try:
            tasks = backend.list_tasks(
                warehouse=warehouse,
                status="0",  # STATUS_OPEN
                top=BATCH_SIZE,
            )
        except Exception as e:
            logger.error(f"Failed to collect tasks from {backend.display_name}: {e}")
            self._metrics["errors"] += 1
            return 0

        if not tasks:
            logger.debug(f"No pending tasks in warehouse {warehouse}")
            return 0

        # Convert to orders
        orders = []
        queue_items = []
        for task in tasks:
            order = self._task_to_order(task, warehouse)
            if order is None:
                continue

            # Persist order
            try:
                self._orders.create_order(order)
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to persist order for task {task.external_id}: {e}")
                self._metrics["errors"] += 1
                continue

            # Enqueue for dispatch
            queue_items.append((order.order_no, order.priority, order.payload))

        # Batch-enqueue all orders
        if queue_items:
            self._queue.enqueue_batch(queue_items)

        self._last_run = now
        self._metrics["batches_submitted"] += 1
        self._metrics["orders_created"] += len(orders)

        logger.info(f"Batch: {len(orders)} orders created from {len(tasks)} SAP tasks")
        return len(orders)

    # ── Helpers ────────────────────────────────────────

    def _task_to_order(self, task: WarehouseTask, warehouse: str) -> WarehouseOrder | None:
        """Map an SAP warehouse task to a VDA5050 WarehouseOrder."""
        if not task or not task.external_id:
            return None

        # Determine order type from process type (EWM) or movement type (WM)
        order_type = OrderType.MOVE
        if task.task_type:
            tt = task.task_type.upper()
            if "PICK" in tt:
                order_type = OrderType.PICK
            elif "PUT" in tt:
                order_type = OrderType.PUT
            elif "CHARGE" in tt:
                order_type = OrderType.CHARGE

        # Build VDA5050 payload
        payload = {
            "orderId": task.external_id,
            "orderUpdateId": 0,
            "warehouse": warehouse,
            "sourceSystem": task.source_system,
            "product": task.product,
            "sourceBin": task.source_bin,
            "destBin": task.dest_bin,
            "targetQty": task.target_qty,
            "batch": task.batch,
        }

        # Determine priority from task type
        priority = 3  # default low
        if order_type == OrderType.PICK:
            priority = 1  # high
        elif order_type == OrderType.CHARGE:
            priority = 2  # normal

        return WarehouseOrder(
            order_no=task.external_id,
            type=order_type,
            priority=priority,
            source=f"SAP:{warehouse}:{task.external_id}",
            robot_brand=None,  # Assignment happens at dispatch
            robot_serial=None,
            payload=payload,
            expected_qty=task.target_qty,
        )
