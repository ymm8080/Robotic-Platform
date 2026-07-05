"""Tests for QueueWorker — dispatch logic, retry, backoff, deadletter."""
import os
from unittest.mock import MagicMock, patch

import pytest


# Use a single global mock redis before any module imports
MOCK_REDIS_FOR_TESTS = MagicMock()
MOCK_REDIS_FOR_TESTS.ping.return_value = True
MOCK_REDIS_FOR_TESTS.zadd.return_value = 1
MOCK_REDIS_FOR_TESTS.zcard.return_value = 0
MOCK_REDIS_FOR_TESTS.zrange.return_value = []
MOCK_REDIS_FOR_TESTS.zrem.return_value = 1
MOCK_REDIS_FOR_TESTS.delete.return_value = 1
MOCK_REDIS_FOR_TESTS.bzpopmin.return_value = None
MOCK_REDIS_FOR_TESTS.hset.return_value = 1
MOCK_REDIS_FOR_TESTS.hgetall.return_value = {}
MOCK_REDIS_FOR_TESTS.hdel.return_value = 1
MOCK_REDIS_FOR_TESTS.expire.return_value = True
MOCK_REDIS_FOR_TESTS.hlen.return_value = 0
MOCK_REDIS_FOR_TESTS.get.return_value = None
MOCK_REDIS_FOR_TESTS.set.return_value = True
MOCK_REDIS_FOR_TESTS.setex.return_value = True
MOCK_REDIS_FOR_TESTS.incr.return_value = 1
MOCK_REDIS_FOR_TESTS.pipeline.return_value = MagicMock()


@pytest.fixture(autouse=True)
def _patch_redis():
    """Patch redis.from_url globally before each test."""
    with patch("redis.from_url", return_value=MOCK_REDIS_FOR_TESTS):
        yield


@pytest.fixture
def db():
    """Schema is initialized by conftest.py. Return None for compatibility."""
    from db import init_schema
    init_schema()
    return None


class TestQueueWorkerLifecycle:
    """Worker start/stop and basic lifecycle."""

    def test_worker_starts_and_stops(self, db):
        from dispatch_queue.worker import QueueWorker
        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            assert worker._running is False
            worker.start()
            assert worker._running is True
            worker.stop()
            assert worker._running is False

    def test_worker_recovers_stale_on_start(self, db):
        from dispatch_queue.worker import QueueWorker
        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            with patch.object(worker._queue, 'recover_stale_processing',
                              wraps=worker._queue.recover_stale_processing) as mock_rec:
                worker.start()
                mock_rec.assert_called_once()
                worker.stop()

    def test_worker_metrics_property(self, db):
        from dispatch_queue.worker import QueueWorker
        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            metrics = worker.metrics
            metrics["dispatched"] = 999
            assert worker._metrics["dispatched"] == 0

    def test_tick_on_empty_queue(self, db):
        from dispatch_queue.worker import QueueWorker
        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            # _tick on empty queue should do nothing and return without error
            assert worker._queue.depth() == 0
            worker._tick()
            # After tick, queue should still be empty, no orders dispatched
            assert worker._queue.depth() == 0
            assert worker._metrics["dispatched"] == 0


class TestQueueWorkerDispatch:
    """Dispatch logic with mocked MQTT."""

    def _make_order(self, db, order_no, brand="KUKA", serial="KMR-001"):
        from models.order import WarehouseOrder
        from services.order_service import OrderService
        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no=order_no, robot_brand=brand, robot_serial=serial))
        return svc.get_order(order_no)

    def test_dispatch_success(self, db):
        from dispatch_queue.worker import QueueWorker
        order = self._make_order(db, "DISPATCH-001")
        mock_pub = MagicMock()
        mock_pub.publish.return_value = 42
        mock_pub.is_connected = True

        with patch("dispatch_queue.worker.get_publisher", return_value=mock_pub):
            worker = QueueWorker()
            result = worker._dispatch(order, {"payload": {}})
            assert result is True

    def test_dispatch_mqtt_failure(self, db):
        from dispatch_queue.worker import QueueWorker
        order = self._make_order(db, "FAIL-001")
        mock_pub = MagicMock()
        mock_pub.publish.return_value = None

        with patch("dispatch_queue.worker.get_publisher", return_value=mock_pub):
            worker = QueueWorker()
            result = worker._dispatch(order, {"payload": {}})
            assert result is False

    def test_dispatch_callback_invoked(self, db):
        from dispatch_queue.worker import QueueWorker
        order = self._make_order(db, "CB-001")
        mock_pub = MagicMock()
        mock_pub.publish.return_value = 42
        callback = MagicMock()

        with patch("dispatch_queue.worker.get_publisher", return_value=mock_pub):
            worker = QueueWorker()
            worker.set_dispatch_callback(callback)
            worker._dispatch(order, {"payload": {}})
            callback.assert_called_once()

    def test_handle_failure_deadletters_at_max(self, db):
        from dispatch_queue.worker import MAX_RETRIES, QueueWorker
        order = self._make_order(db, "DL-001")

        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            worker._retry_count["DL-001"] = MAX_RETRIES - 1
            worker._handle_failure(order, {"payload": {}})
            assert worker._metrics["deadlettered"] >= 1

    def test_handle_failure_retries_before_max(self, db):
        from dispatch_queue.worker import QueueWorker
        order = self._make_order(db, "RETRY-001")

        with patch("dispatch_queue.worker.get_publisher"):
            worker = QueueWorker()
            worker._retry_count["RETRY-001"] = 1
            worker._handle_failure(order, {"payload": {}})
            assert worker._metrics["deadlettered"] == 0
            assert worker._metrics["failed"] >= 1
            assert "RETRY-001" in worker._backoff_until
