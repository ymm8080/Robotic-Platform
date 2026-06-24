"""Tests for OrderService with SQLite persistence."""
import os
import sqlite3
import tempfile

import pytest

from models.order import OrderStatus, OrderType, WarehouseOrder
from services.order_service import OrderService


@pytest.fixture
def db_path():
    """Return a temporary database path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    if os.path.exists(tmp.name):
        os.remove(tmp.name)


@pytest.fixture(autouse=True)
def setup_db(db_path):
    """Create orders_v2 table in test DB before each test."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders_v2 (
            id INTEGER PRIMARY KEY,
            order_no TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'MOVE',
            priority INTEGER NOT NULL DEFAULT 3,
            source TEXT,
            robot_brand TEXT,
            robot_serial TEXT,
            status TEXT NOT NULL DEFAULT 'CREATED',
            payload TEXT,
            zone_id TEXT,
            zone_token TEXT,
            weight REAL,
            location TEXT,
            env_tag TEXT DEFAULT 'PROD',
            expected_qty INTEGER,
            assigned_rule_id INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            version INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now')),
            description TEXT
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture
def service(db_path):
    return OrderService(db_path=db_path)


class TestOrderService:
    """Order Service CRUD and lifecycle tests."""

    def test_create_order(self, service):
        order = service.create_order(WarehouseOrder(order_no="ORDER-001"))
        assert order.id is not None
        assert order.id > 0

    def test_create_and_retrieve(self, service):
        service.create_order(WarehouseOrder(
            order_no="ORDER-002",
            type=OrderType.PICK,
            priority=0,
            source="SAP-TASK-001",
        ))
        retrieved = service.get_order("ORDER-002")
        assert retrieved is not None
        assert retrieved.order_no == "ORDER-002"
        assert retrieved.type == OrderType.PICK
        assert retrieved.priority == 0
        assert retrieved.source == "SAP-TASK-001"

    def test_get_order_not_found(self, service):
        assert service.get_order("NONEXISTENT") is None

    def test_list_orders(self, service):
        service.create_order(WarehouseOrder(order_no="O-001", priority=0))
        service.create_order(WarehouseOrder(order_no="O-002", priority=1))
        service.create_order(WarehouseOrder(order_no="O-003", priority=2))
        orders = service.list_orders(limit=10)
        assert len(orders) == 3

    def test_list_orders_filter_by_status(self, service):
        service.create_order(WarehouseOrder(order_no="O-001"))
        service.create_order(WarehouseOrder(order_no="O-002"))
        service.cancel_order("O-001")
        created = service.list_orders(status=OrderStatus.CREATED)
        cancelled = service.list_orders(status=OrderStatus.CANCELLED)
        assert len(created) == 1
        assert len(cancelled) == 1

    def test_list_orders_filter_by_brand(self, service):
        service.create_order(WarehouseOrder(order_no="O-001", robot_brand="KUKA"))
        service.create_order(WarehouseOrder(order_no="O-002", robot_brand="MIR"))
        kuka_orders = service.list_orders(brand="KUKA")
        assert len(kuka_orders) == 1
        assert kuka_orders[0].robot_brand == "KUKA"

    def test_assign_order(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-003"))
        order = service.assign_order("ORDER-003", "KUKA", "KMR-001")
        assert order is not None
        assert order.status == OrderStatus.ASSIGNED
        assert order.robot_brand == "KUKA"
        assert order.robot_serial == "KMR-001"

    def test_assign_already_assigned(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-004"))
        service.assign_order("ORDER-004", "KUKA", "KMR-001")
        result = service.assign_order("ORDER-004", "MIR", "MIR-001")
        assert result is None

    def test_full_lifecycle(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-005"))
        service.assign_order("ORDER-005", "KUKA", "KMR-001")
        service.start_execution("ORDER-005")
        service.complete_order("ORDER-005")
        order = service.get_order("ORDER-005")
        assert order.status == OrderStatus.COMPLETED
        assert order.completed_at is not None

    def test_cancel_created_order(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-006"))
        order = service.cancel_order("ORDER-006")
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_executing_order_fails(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-007"))
        service.assign_order("ORDER-007", "KUKA", "KMR-001")
        service.start_execution("ORDER-007")
        result = service.cancel_order("ORDER-007")
        assert result is None

    def test_fail_order(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-008"))
        service.assign_order("ORDER-008", "KUKA", "KMR-001")
        order = service.fail_order("ORDER-008", "Hardware error")
        assert order.status == OrderStatus.FAILED
        assert order.error_message == "Hardware error"

    def test_suspend_order(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-009"))
        service.assign_order("ORDER-009", "KUKA", "KMR-001")
        service.start_execution("ORDER-009")
        order = service.suspend_order("ORDER-009", "Human intervention needed")
        assert order.status == OrderStatus.SUSPENDED
        assert order.error_message == "Human intervention needed"

    def test_version_increments_on_update(self, service):
        service.create_order(WarehouseOrder(order_no="ORDER-010"))
        order_v1 = service.get_order("ORDER-010")
        assert order_v1.version == 1
        service.assign_order("ORDER-010", "KUKA", "KMR-001")
        order_v2 = service.get_order("ORDER-010")
        assert order_v2.version >= 2
