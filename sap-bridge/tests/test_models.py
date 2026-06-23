"""Tests for order data models."""
import pytest
from models.order import WarehouseOrder, OrderType, OrderStatus


class TestWarehouseOrder:
    """WarehouseOrder data class behavior."""

    def test_create_default_order(self):
        """Default order should have sensible defaults."""
        order = WarehouseOrder(order_no="ORDER-001")
        assert order.order_no == "ORDER-001"
        assert order.type == OrderType.MOVE
        assert order.priority == 3
        assert order.status == OrderStatus.CREATED
        assert order.env_tag == "PROD"
        assert order.version == 1
        assert order.created_at is not None
        assert order.updated_at is not None

    def test_create_pick_order(self):
        order = WarehouseOrder(
            order_no="ORDER-002",
            type=OrderType.PICK,
            priority=0,
            source="SAP-TASK-100",
            robot_brand="KUKA",
            robot_serial="KMR-001",
            payload={"nodes": [{"nodeId": "NODE-01"}]},
            weight=50.0,
        )
        assert order.type == OrderType.PICK
        assert order.priority == 0
        assert order.source == "SAP-TASK-100"
        assert order.robot_brand == "KUKA"
        assert order.robot_serial == "KMR-001"

    def test_mark_assigned(self):
        order = WarehouseOrder(order_no="ORDER-003")
        order.mark_assigned("KUKA", "KMR-001")
        assert order.status == OrderStatus.ASSIGNED
        assert order.robot_brand == "KUKA"
        assert order.robot_serial == "KMR-001"
        assert order.updated_at is not None

    def test_mark_in_progress(self):
        order = WarehouseOrder(order_no="ORDER-004")
        order.mark_assigned("KUKA", "KMR-001")
        order.mark_in_progress()
        assert order.status == OrderStatus.IN_PROGRESS

    def test_mark_completed(self):
        order = WarehouseOrder(order_no="ORDER-005")
        order.mark_assigned("KUKA", "KMR-001")
        order.mark_in_progress()
        order.mark_completed()
        assert order.status == OrderStatus.COMPLETED
        assert order.completed_at is not None

    def test_mark_failed(self):
        order = WarehouseOrder(order_no="ORDER-006")
        order.mark_assigned("KUKA", "KMR-001")
        order.mark_failed("Motor stall")
        assert order.status == OrderStatus.FAILED
        assert order.error_message == "Motor stall"

    def test_mark_cancelled(self):
        order = WarehouseOrder(order_no="ORDER-007")
        order.mark_cancelled()
        assert order.status == OrderStatus.CANCELLED

    def test_mark_suspended(self):
        order = WarehouseOrder(order_no="ORDER-008")
        order.mark_suspended("Zone locked")
        assert order.status == OrderStatus.SUSPENDED
        assert order.error_message == "Zone locked"

    def test_to_dict_includes_all_fields(self):
        order = WarehouseOrder(
            order_no="ORDER-009",
            type=OrderType.CHARGE,
            priority=1,
            source="SAP-001",
        )
        d = order.to_dict()
        assert d["orderNo"] == "ORDER-009"
        assert d["type"] == "CHARGE"
        assert d["priority"] == 1
        assert d["source"] == "SAP-001"
        assert d["status"] == "CREATED"
        assert "createdAt" in d
        assert "updatedAt" in d

    def test_order_type_values(self):
        assert OrderType.PICK.value == "PICK"
        assert OrderType.PUT.value == "PUT"
        assert OrderType.MOVE.value == "MOVE"
        assert OrderType.CHARGE.value == "CHARGE"

    def test_order_status_values(self):
        statuses = [
            "CREATED", "ASSIGNED", "IN_PROGRESS", "COMPLETED",
            "FAILED", "CANCELLED", "SUSPENDED", "DIFF_SUSPENDED",
        ]
        for s in statuses:
            assert OrderStatus(s).value == s
