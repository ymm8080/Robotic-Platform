"""
Order lifecycle service.
Manages the full lifecycle of robot dispatch orders:
create → assign → execute → complete / fail / cancel / suspend
"""
import json
import logging
import os
import sqlite3

from models.order import OrderStatus, OrderType, WarehouseOrder

logger = logging.getLogger(__name__)

# SQLite database path (mounted Docker volume path)
DB_PATH = os.getenv("DB_PATH", "/data/robot_platform.db")


class OrderService:
    """Order lifecycle service with SQLite persistence."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_no TEXT NOT NULL,
                    type TEXT NOT NULL,
                    priority INTEGER DEFAULT 3,
                    source TEXT,
                    robot_brand TEXT,
                    robot_serial TEXT,
                    status TEXT DEFAULT 'CREATED',
                    payload TEXT,
                    zone_id TEXT,
                    location TEXT,
                    weight REAL,
                    env_tag TEXT,
                    expected_qty INTEGER,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_v2_status ON orders_v2(status)")
            conn.commit()
        finally:
            conn.close()

    # ── Connection ──────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Get a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── CRUD ────────────────────────────────────────────

    def create_order(self, order: WarehouseOrder) -> WarehouseOrder:
        """Persist a new order and return it with generated ID."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO orders_v2
                   (order_no, type, priority, source, robot_brand, robot_serial,
                    status, payload, zone_id, location, weight, env_tag,
                    expected_qty, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                "SELECT * FROM orders_v2 WHERE order_no = ?", (order_no,)
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
                "SELECT * FROM orders_v2 WHERE id = ?", (order_id,)
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
            query = "SELECT * FROM orders_v2 WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status.value)
            if brand:
                query += " AND robot_brand = ?"
                params.append(brand.upper())

            query += " ORDER BY priority ASC, created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
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
                """UPDATE orders_v2 SET
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
    def _row_to_order(row: sqlite3.Row) -> WarehouseOrder:
        """Convert a DB row to a WarehouseOrder."""
        data = dict(row)
        return WarehouseOrder(
            id=data["id"],
            order_no=data["order_no"],
            type=OrderType(data["type"]),
            priority=data["priority"],
            source=data.get("source"),
            robot_brand=data.get("robot_brand"),
            robot_serial=data.get("robot_serial"),
            status=OrderStatus(data["status"]),
            payload=json.loads(data["payload"]) if data.get("payload") else None,
            zone_id=data.get("zone_id"),
            location=data.get("location"),
            weight=data.get("weight"),
            env_tag=data.get("env_tag", "PROD"),
            expected_qty=data.get("expected_qty"),
            assigned_rule_id=data.get("assigned_rule_id"),
            error_message=data.get("error_message"),
            version=data.get("version", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
        )
