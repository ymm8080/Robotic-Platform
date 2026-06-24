"""Tests for Inventory Service — SAP stock cache with Redis."""
from unittest.mock import MagicMock, patch

import pytest


class TestInventoryService:
    """Inventory cache service with mocked Redis."""

    @pytest.fixture
    def svc(self):
        from services.inventory_service import InventoryService
        with patch("services.inventory_service.rd.from_url") as mock_ru:
            mock_ru.return_value = MagicMock()
            yield InventoryService()

    def test_get_stock_miss(self, svc):
        svc._redis.get.return_value = None
        qty = svc.get_stock("PROD-001", "WM01")
        assert qty is None

    def test_get_stock_hit(self, svc):
        svc._redis.get.return_value = "42"
        qty = svc.get_stock("PROD-001", "WM01")
        assert qty == 42

    def test_get_stock_zero(self, svc):
        svc._redis.get.return_value = "0"
        qty = svc.get_stock("PROD-001", "WM01")
        assert qty == 0

    def test_get_all_stock(self, svc):
        svc._redis.keys.return_value = [
            "inventory:WM01:PROD-A",
            "inventory:WM01:PROD-B",
        ]
        svc._redis.get.side_effect = ["100", "200"]
        items = svc.get_all_stock("WM01")
        assert items["PROD-A"] == 100
        assert items["PROD-B"] == 200

    def test_get_all_stock_empty_warehouse(self, svc):
        svc._redis.keys.return_value = []
        items = svc.get_all_stock("WM01")
        assert items == {}

    def test_clear_cache(self, svc):
        svc._redis.keys.return_value = ["inventory:WM01:A", "inventory:WM01:B"]
        svc._redis.delete.return_value = 2
        svc.clear_cache("WM01")
        assert svc._redis.delete.called

    def test_mark_synced(self, svc):
        svc.mark_synced()
        svc._redis.set.assert_called_once()

    def test_update_stock(self, svc):
        svc.update_stock("PROD-001", 50.0, "WM01")
        svc._redis.setex.assert_called_once()

    def test_report_consumption(self, svc):
        svc._redis.get.return_value = "100"
        svc.report_consumption("PROD-001", 10, "ORD-001", "WM01")
        assert svc._redis.setex.called
        assert svc._redis.lpush.called

    def test_report_production(self, svc):
        svc._redis.get.return_value = "90"
        svc.report_production("PROD-001", 20, "ORD-002", "WM01")
        assert svc._redis.setex.called
        assert svc._redis.lpush.called

    def test_needs_sync_initially(self, svc):
        assert svc.needs_sync() is True

    def test_needs_sync_after_mark(self, svc):
        svc.mark_synced()
        assert svc.needs_sync() is False

    def test_update_batch(self, svc):
        items = [
            {"product": "A", "quantity": 10},
            {"product": "B", "quantity": 20},
        ]
        svc.update_batch(items, "WM01")
        assert svc._redis.pipeline.called

    def test_get_stock_unavailable_redis(self, svc):
        svc._redis.get.side_effect = RuntimeError("Redis connection failed")
        with pytest.raises(RuntimeError):
            svc.get_stock("PROD-001", "WM01")

    def test_get_stock_with_batch(self, svc):
        svc._redis.get.return_value = "15"
        qty = svc.get_stock("PROD-001", "WM01", batch="BATCH-001")
        assert qty == 15
