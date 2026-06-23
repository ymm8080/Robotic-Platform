"""Tests for priority queue, deadletter handler, and worker."""
import json
import time
import pytest
from dispatch_queue.priority_queue import PriorityQueue
from dispatch_queue.deadletter import DeadLetterHandler


# Use a separate Redis DB for testing
TEST_REDIS_URL = "redis://localhost:6379/15"


class TestPriorityQueue:
    """Priority queue tests (requires Redis)."""

    @pytest.fixture
    def q(self):
        q = PriorityQueue(redis_url=TEST_REDIS_URL)
        q.clear()
        yield q
        q.clear()

    def test_enqueue_single(self, q):
        assert q.depth() == 0
        q.enqueue("ORDER-001", priority=0)
        assert q.depth() == 1

    def test_enqueue_multiple(self, q):
        q.enqueue("ORDER-A", priority=3)
        q.enqueue("ORDER-B", priority=0)
        q.enqueue("ORDER-C", priority=1)
        assert q.depth() == 3

    def test_priority_order(self, q):
        """Higher priority (lower number) should be dequeued first."""
        q.enqueue("LOW", priority=3)
        q.enqueue("HIGH", priority=0)
        q.enqueue("MED", priority=1)

        item1 = q.dequeue(timeout_ms=1000)
        item2 = q.dequeue(timeout_ms=1000)
        item3 = q.dequeue(timeout_ms=1000)

        assert item1["order_no"] == "HIGH"
        assert item2["order_no"] == "MED"
        assert item3["order_no"] == "LOW"

    def test_fifo_within_same_priority(self, q):
        """Same priority should preserve FIFO order."""
        q.enqueue("FIRST", priority=1)
        time.sleep(0.01)
        q.enqueue("SECOND", priority=1)
        time.sleep(0.01)
        q.enqueue("THIRD", priority=1)

        assert q.dequeue(timeout_ms=1000)["order_no"] == "FIRST"
        assert q.dequeue(timeout_ms=1000)["order_no"] == "SECOND"
        assert q.dequeue(timeout_ms=1000)["order_no"] == "THIRD"

    def test_dequeue_empty(self, q):
        """Dequeue from empty queue should return None."""
        item = q.dequeue(timeout_ms=100)
        assert item is None

    def test_peek(self, q):
        q.enqueue("ORDER-001", priority=0)
        q.enqueue("ORDER-002", priority=1)
        items = q.peek(10)
        assert len(items) == 2
        assert items[0]["order_no"] == "ORDER-001"

    def test_remove(self, q):
        q.enqueue("ORDER-001", priority=0)
        q.enqueue("ORDER-002", priority=1)
        assert q.depth() == 2
        q.remove("ORDER-001")
        assert q.depth() == 1

    def test_clear(self, q):
        q.enqueue("A", priority=0)
        q.enqueue("B", priority=1)
        assert q.clear() == 2
        assert q.depth() == 0

    def test_is_healthy(self, q):
        assert q.is_healthy is True

    def test_enqueue_batch(self, q):
        items = [("A", 0, None), ("B", 1, None), ("C", 2, None)]
        count = q.enqueue_batch(items)
        assert count == 3
        assert q.depth() == 3


class TestDeadLetterHandler:
    """Dead letter handler tests (uses in-memory DB)."""

    @pytest.fixture
    def dl(self, tmp_path):
        """Use a temporary SQLite database."""
        db_path = str(tmp_path / "test_deadletter.db")
        # Create the dead_letter_queue table
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY,
                original_id TEXT,
                error_type TEXT,
                error_message TEXT,
                payload TEXT,
                status TEXT DEFAULT 'UNRESOLVED',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

        handler = DeadLetterHandler(db_path=db_path)
        yield handler

    def test_send(self, dl):
        dl_id = dl.send("ORDER-001", "MAX_RETRIES", "Failed after 5 attempts")
        assert dl_id > 0

    def test_list_unresolved(self, dl):
        dl.send("ORDER-001", "TIMEOUT", "MQTT timeout")
        dl.send("ORDER-002", "ERROR", "SAP failure")

        unresolved = dl.list_unresolved()
        assert len(unresolved) == 2

    def test_resolve(self, dl):
        dl_id = dl.send("ORDER-001", "ERROR", "test error")
        ok = dl.resolve(dl_id, "MANUAL_FIX")
        assert ok is True

        unresolved = dl.list_unresolved()
        assert len(unresolved) == 0

    def test_resolve_nonexistent(self, dl):
        ok = dl.resolve(999, "MANUAL_FIX")
        assert ok is False

    def test_retry(self, dl):
        payload = {"nodes": [{"nodeId": "NODE-01"}]}
        dl_id = dl.send("ORDER-001", "ERROR", "test", payload=payload)
        data = dl.retry(dl_id)
        assert data is not None
        assert data["original_id"] == "ORDER-001"
        assert data["error_type"] == "ERROR"

    def test_count_unresolved(self, dl):
        dl.send("ORDER-001", "E1", "err1")
        dl.send("ORDER-002", "E2", "err2")
        assert dl.count_unresolved() == 2
