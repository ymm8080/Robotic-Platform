"""Tests for BatchService — SAP task collection and order creation.

Tests use mocked backends. The backend abstraction means the same BatchService
code works for both EWM and WM — just mock get_backend_for().
"""
from unittest.mock import MagicMock, patch

import pytest


class TestBatchService:
    """Batch order submission service tests."""

    @pytest.fixture
    def svc(self):
        from services.batch_service import BatchService
        with patch("services.batch_service.OrderService"), \
             patch("services.batch_service.PriorityQueue"):
            svc = BatchService()
            svc._orders = MagicMock()
            svc._queue = MagicMock()
            yield svc

    def _make_mock_backend(self):
        """Create a mock WarehouseBackend that returns sample tasks."""
        from models.warehouse_task import WarehouseTask

        backend = MagicMock()
        backend.backend_type = "ewm"
        backend.display_name = "Test Backend"
        backend.list_tasks.return_value = []

        def _fake_task(task_id, process_type="PICK", product="MAT-A"):
            return WarehouseTask(
                source_system="EWM",
                warehouse="WM01",
                external_id=task_id,
                item_no="0001",
                task_type=process_type,
                source_bin="S01-01",
                dest_bin="D01-01",
                product=product,
                target_qty=10.0,
            )

        backend._fake_task = _fake_task
        return backend

    def test_collect_and_submit_with_tasks(self, svc):
        """Should create orders from SAP tasks and enqueue them."""
        backend = self._make_mock_backend()
        backend.list_tasks.return_value = [backend._fake_task("TASK-001")]

        with patch("services.batch_service.get_backend_for", return_value=backend):
            count = svc.collect_and_submit(warehouse="WM01")
            assert count == 1
        assert svc._metrics["batches_submitted"] == 1
        assert svc._metrics["orders_created"] == 1

    def test_collect_and_submit_no_backend(self, svc):
        """Should handle missing backend gracefully."""
        with patch("services.batch_service.get_backend_for", return_value=None):
            count = svc.collect_and_submit(warehouse="WM01")
            assert count == 0
        assert svc._metrics["errors"] >= 1

    def test_collect_and_submit_no_tasks(self, svc):
        backend = self._make_mock_backend()
        backend.list_tasks.return_value = []

        with patch("services.batch_service.get_backend_for", return_value=backend):
            count = svc.collect_and_submit(warehouse="WM01")
            assert count == 0

    def test_collect_and_submit_sap_error(self, svc):
        backend = self._make_mock_backend()
        backend.list_tasks.side_effect = ConnectionError("SAP down")

        with patch("services.batch_service.get_backend_for", return_value=backend):
            count = svc.collect_and_submit(warehouse="WM01")
            assert count == 0
        assert svc._metrics["errors"] >= 1

    def test_collect_and_submit_throttle(self, svc):
        """Should skip if called before interval elapses."""
        svc._last_run = 9999999999.0  # Far future
        count = svc.collect_and_submit(warehouse="WM01")
        assert count == 0  # Throttled

    def test_task_to_order_pick(self, svc):
        """PICK process type should map to high priority OrderType.PICK."""
        from models.warehouse_task import WarehouseTask
        task = WarehouseTask(
            source_system="EWM", warehouse="WM01",
            external_id="PICK-001", task_type="PICK",
            product="MAT-X", source_bin="S01", dest_bin="D01",
            target_qty=5.0,
        )
        order = svc._task_to_order(task, "WM01")
        assert order is not None
        assert order.order_no == "PICK-001"
        from models.order import OrderType
        assert order.type == OrderType.PICK
        assert order.priority == 1

    def test_task_to_order_move(self, svc):
        from models.warehouse_task import WarehouseTask
        task = WarehouseTask(
            source_system="EWM", warehouse="WM01",
            external_id="MOVE-001", task_type="MOVE",
            product="MAT-Y", target_qty=1.0,
        )
        order = svc._task_to_order(task, "WM01")
        assert order is not None
        assert order.priority == 3

    def test_metrics_property(self, svc):
        svc._metrics["orders_created"] = 42
        m = svc.metrics
        assert m["orders_created"] == 42
        m["orders_created"] = 999  # Should not affect original
        assert svc._metrics["orders_created"] == 42

    def test_e2e_with_wm_backend(self, svc):
        """Same flow should work with WM backend type."""
        from models.warehouse_task import WarehouseTask
        backend = MagicMock()
        backend.backend_type = "wm"
        backend.display_name = "WM Backend"
        backend.list_tasks.return_value = [
            WarehouseTask(
                source_system="WM", warehouse="001",
                external_id="TO-1000", task_type="MOVE",
                product="MAT-WM", target_qty=5.0,
                to_number="TO-1000", movement_type="999",
            )
        ]

        with patch("services.batch_service.get_backend_for", return_value=backend):
            count = svc.collect_and_submit(warehouse="001")
            assert count == 1
        assert svc._metrics["batches_submitted"] == 1
