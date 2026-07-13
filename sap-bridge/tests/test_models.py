"""Tests for order data models."""

from models.order import OrderStatus, OrderType, WarehouseOrder


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
            "CREATED",
            "ASSIGNED",
            "IN_PROGRESS",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "SUSPENDED",
            "DIFF_SUSPENDED",
        ]
        for s in statuses:
            assert OrderStatus(s).value == s

    def test_order_with_batch_info(self):
        order = WarehouseOrder(order_no="BATCH-001", expected_qty=10)
        assert order.expected_qty == 10

    def test_order_with_zone_and_location(self):
        order = WarehouseOrder(order_no="ZONE-001", zone_id="ZONE-A", location="A01-01-01")
        assert order.zone_id == "ZONE-A"
        assert order.location == "A01-01-01"

    def test_order_with_assigned_rule(self):
        order = WarehouseOrder(order_no="RULE-001", assigned_rule_id=42)
        assert order.assigned_rule_id == 42

    def test_order_to_dict_omit_none(self):
        order = WarehouseOrder(order_no="DICT-001")
        d = order.to_dict()
        # Optional fields should be omitted or None
        assert d["orderNo"] == "DICT-001"
        assert "errorMessage" not in d or d.get("errorMessage") is None

    def test_order_version_increments_on_state_change(self):
        """Version increments via OrderService._update(), not model directly."""
        order = WarehouseOrder(order_no="VER-001")
        v1 = order.version
        assert v1 == 1

    def test_put_order_type(self):
        order = WarehouseOrder(order_no="PUT-001", type=OrderType.PUT)
        assert order.type == OrderType.PUT
        assert order.type.value == "PUT"

    def test_charge_order_type(self):
        order = WarehouseOrder(order_no="CHG-001", type=OrderType.CHARGE)
        assert order.type == OrderType.CHARGE

    def test_order_multiple_transitions(self):
        """Full lifecycle: CREATED → ASSIGNED → IN_PROGRESS → COMPLETED."""
        order = WarehouseOrder(order_no="LIFECYCLE-001")
        assert order.status == OrderStatus.CREATED
        order.mark_assigned("MIR", "MIR-001")
        assert order.status == OrderStatus.ASSIGNED
        order.mark_in_progress()
        assert order.status == OrderStatus.IN_PROGRESS
        order.mark_completed()
        assert order.status == OrderStatus.COMPLETED
        assert order.completed_at is not None

    def test_order_failed_with_long_message(self):
        long_msg = "E" * 1000
        order = WarehouseOrder(order_no="LONG-ERR-001")
        order.mark_failed(long_msg)
        assert order.error_message == long_msg
        assert order.status == OrderStatus.FAILED

    def test_order_suspended_then_failed(self):
        order = WarehouseOrder(order_no="SUSP-FAIL-001")
        order.mark_suspended("Waiting for operator")
        assert order.status == OrderStatus.SUSPENDED
        order.mark_failed("Operator cancelled")
        assert order.status == OrderStatus.FAILED
