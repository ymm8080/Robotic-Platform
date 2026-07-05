"""
Order lifecycle service.
Manages the full lifecycle of robot dispatch orders:
create → assign → execute → complete / fail / cancel / suspend

v4.1: PostgreSQL-only. All data in PostgreSQL.
"""
import json
import logging

from db import connect, init_schema
from models.order import OrderStatus, OrderType, WarehouseOrder

logger = logging.getLogger(__name__)


class OrderService:
    """Order lifecycle service with unified persistence via db.py abstraction."""

    def __init__(self):
        init_schema()

    # ── Connection ──────────────────────────────────────

    def _connect(self):
        """Get a new PostgreSQL connection."""
        return connect()

    # ── CRUD ────────────────────────────────────────────

    def create_order(self, order: WarehouseOrder) -> WarehouseOrder:
        """Persist a new order and return it with generated ID."""
        conn = self._connect()
        try:
            sql = """
                INSERT INTO orders
                (order_no, type, priority, source, robot_brand, robot_serial,
                 status, payload, zone_id, location, weight, env_tag,
                 expected_qty, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """
            cur = conn.execute(
                sql,
                (
                    order.order_no, order.type.value, order.priority,
                    order.source, order.robot_brand, order.robot_serial,
                    order.status.value,
                    json.dumps(order.payload) if order.payload else None,
                    order.zone_id, order.location, order.weight,
                    order.env_tag, order.expected_qty,
                    order.created_at, order.updated_at,
                ),
            )
            conn.commit()
            order.id = cur.lastrowid
            logger.info(f"Order created: {order.order_no} (id={order.id})")
            return order
        finally:
            conn.close()

    def get_order(self, order_no: str) -> WarehouseOrder | None:
        """Get order by order number."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_no = ?", (order_no,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_order(row)
        finally:
            conn.close()

    def get_order_by_id(self, order_id: int) -> WarehouseOrder | None:
        """Get order by database ID."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_order(row)
        finally:
            conn.close()

    def list_orders(
        self,
        status: OrderStatus | None = None,
        brand: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WarehouseOrder]:
        """List orders with optional filters."""
        conn = self._connect()
        try:
            query = "SELECT * FROM orders WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status.value)
            if brand:
                query += " AND robot_brand = ?"
                params.append(brand.upper())

            query += " ORDER BY priority ASC, created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_order(r) for r in rows]
        finally:
            conn.close()

    # ── State transitions ───────────────────────────────

    def assign_order(self, order_no: str, brand: str, serial: str) -> WarehouseOrder | None:
        """Assign order to a robot. Validates CREATED → ASSIGNED transition."""
        order = self.get_order(order_no)
        if order is None:
            return None
        if order.status != OrderStatus.CREATED:
            logger.warning(f"Cannot assign order {order_no}: status={order.status.value}")
            return None

        order.mark_assigned(brand, serial)
        self._update(order)
        return order

    def start_execution(self, order_no: str) -> WarehouseOrder | None:
        """Mark order as in progress. ASSIGNED → IN_PROGRESS."""
        order = self.get_order(order_no)
        if order is None or order.status != OrderStatus.ASSIGNED:
            return None
        order.mark_in_progress()
        self._update(order)
        return order

    def complete_order(self, order_no: str) -> WarehouseOrder | None:
        """Complete order successfully. IN_PROGRESS → COMPLETED."""
        order = self.get_order(order_no)
        if order is None:
            return None
        if order.status not in (OrderStatus.IN_PROGRESS, OrderStatus.ASSIGNED):
            logger.warning(f"Cannot complete order {order_no}: status={order.status.value}")
            return None
        order.mark_completed()
        self._update(order)
        return order

    def fail_order(self, order_no: str, error: str) -> WarehouseOrder | None:
        """Mark order as failed. IN_PROGRESS/ASSIGNED → FAILED."""
        order = self.get_order(order_no)
        if order is None:
            return None
        order.mark_failed(error)
        self._update(order)
        return order

    def cancel_order(self, order_no: str) -> WarehouseOrder | None:
        """Cancel order. CREATED/ASSIGNED → CANCELLED."""
        order = self.get_order(order_no)
        if order is None:
            return None
        if order.status not in (OrderStatus.CREATED, OrderStatus.ASSIGNED):
            logger.warning(f"Cannot cancel order {order_no}: status={order.status.value}")
            return None
        order.mark_cancelled()
        self._update(order)
        return order

    def suspend_order(self, order_no: str, reason: str) -> WarehouseOrder | None:
        """Suspend order for human intervention. IN_PROGRESS → SUSPENDED."""
        order = self.get_order(order_no)
        if order is None:
            return None
        order.mark_suspended(reason)
        self._update(order)
        return order

    # ── Helpers ─────────────────────────────────────────

    def _update(self, order: WarehouseOrder):
        """Persist order state changes. Raises on version conflict."""
        conn = self._connect()
        try:
            order.version += 1
            cur = conn.execute(
                """UPDATE orders SET
                   status=?, robot_brand=?, robot_serial=?, payload=?,
                   zone_id=?, location=?, weight=?, expected_qty=?,
                   assigned_rule_id=?, error_message=?,
                   updated_at=?, completed_at=?, version=?
                   WHERE order_no=? AND version=?""",
                (
                    order.status.value, order.robot_brand, order.robot_serial,
                    json.dumps(order.payload) if order.payload else None,
                    order.zone_id, order.location, order.weight,
                    order.expected_qty, order.assigned_rule_id,
                    order.error_message,
                    order.updated_at, order.completed_at, order.version,
                    order.order_no, order.version - 1,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                logger.error(
                    f"Optimistic lock failed for {order.order_no} — "
                    f"concurrent modification detected"
                )
                raise RuntimeError(
                    f"Order {order.order_no} was modified concurrently"
                )
            logger.info(f"Order updated: {order.order_no} → {order.status.value} (v{order.version})")
        finally:
            conn.close()

    @staticmethod
    def _row_to_order(row: dict) -> WarehouseOrder:
        """Convert a DB row dict to a WarehouseOrder."""
        payload_raw = row.get("payload")
        return WarehouseOrder(
            id=row.get("id"),
            order_no=row["order_no"],
            type=OrderType(row["type"]),
            priority=row["priority"],
            source=row.get("source"),
            robot_brand=row.get("robot_brand"),
            robot_serial=row.get("robot_serial"),
            status=OrderStatus(row["status"]),
            payload=payload_raw if isinstance(payload_raw, (dict, list)) else (json.loads(payload_raw) if payload_raw else None),
            zone_id=row.get("zone_id"),
            location=row.get("location"),
            weight=row.get("weight"),
            env_tag=row.get("env_tag", "PROD"),
            expected_qty=row.get("expected_qty"),
            assigned_rule_id=row.get("assigned_rule_id"),
            error_message=row.get("error_message"),
            version=row.get("version", 1),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
        )
