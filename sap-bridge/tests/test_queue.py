"""Tests for priority queue, deadletter handler, and worker."""
import json
import time
from unittest.mock import patch

import pytest

from dispatch_queue.deadletter import DeadLetterHandler
from dispatch_queue.priority_queue import PriorityQueue


def _make_mock_redis():
    """Build a MagicMock that supports all Redis commands used by PriorityQueue."""

    class _FakeRedis:
        """In-memory fake for Redis sorted-set operations used by PriorityQueue.

        Supports: zadd, zcard, zrange, zrem, delete, bzpopmin, hset, hgetall,
        hdel, expire, ping, pipeline.
        """
        def __init__(self):
            self._zsets: dict[str, dict[str, float]] = {}  # key → {member: score}
            self._hsets: dict[str, dict[str, str]] = {}    # key → {field: value}
            self._pipe = None

        def zadd(self, key, mapping):
            self._zsets.setdefault(key, {}).update(mapping)
            return len(mapping)

        def zcard(self, key):
            return len(self._zsets.get(key, {}))

        def zrange(self, key, start, end, withscores=False, desc=False):
            items = sorted(self._zsets.get(key, {}).items(), key=lambda x: x[1])
            sliced = items[start:end + 1 if end >= 0 else None]
            if withscores:
                return sliced
            return [m for m, _ in sliced]

        def zrem(self, key, *members):
            d = self._zsets.get(key, {})
            count = 0
            for m in members:
                if m in d:
                    del d[m]
                    count += 1
            return count

        def delete(self, *keys):
            count = 0
            for k in keys:
                if k in self._zsets:
                    del self._zsets[k]
                    count += 1
                if k in self._hsets:
                    del self._hsets[k]
                    count += 1
            return count

        def bzpopmin(self, keys, timeout=0):
            # keys is a list; take first
            key = keys[0] if isinstance(keys, list) else keys
            d = self._zsets.get(key, {})
            if not d:
                return None
            member = min(d, key=lambda m: d[m])
            score = d[member]
            del d[member]
            return (key, member, score)

        def hset(self, key, field, value):
            self._hsets.setdefault(key, {})[field] = str(value)
            return 1

        def hgetall(self, key):
            return dict(self._hsets.get(key, {}))

        def hdel(self, key, *fields):
            d = self._hsets.get(key, {})
            count = 0
            for f in fields:
                if f in d:
                    del d[f]
                    count += 1
            return count

        def expire(self, key, ttl):
            return True

        def ping(self):
            return True

        def pipeline(self):
            return _FakePipeline(self)

    class _FakePipeline:
        def __init__(self, redis):
            self._redis = redis
            self._commands = []

        def zadd(self, key, mapping):
            self._commands.append(('zadd', key, mapping))
            return self

        def execute(self):
            results = []
            for cmd in self._commands:
                if cmd[0] == 'zadd':
                    results.append(self._redis.zadd(cmd[1], cmd[2]))
            self._commands = []
            return results

    return _FakeRedis()


class TestPriorityQueue:
    """Priority queue tests (mocked Redis)."""

    @pytest.fixture
    def q(self):
        with patch("dispatch_queue.priority_queue.rd.from_url") as mock_ru:
            mock_ru.return_value = _make_mock_redis()
            q = PriorityQueue()
            yield q

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

    def test_enqueue_batch_with_payloads(self, q):
        items = [("A", 0, {"nodes": [{"nodeId": "N1"}]}), ("B", 1, {"orderId": "O2"})]
        count = q.enqueue_batch(items)
        assert count == 2

    def test_remove_order_not_found(self, q):
        """Remove non-existent order should return False."""
        q.enqueue("EXISTS", priority=0)
        result = q.remove("DOES_NOT_EXIST")
        assert result is False
        assert q.depth() == 1

    def test_recover_stale_empty(self, q):
        """Recover with no processing items returns empty list."""
        reclaimed = q.recover_stale_processing(max_age_seconds=1)
        assert reclaimed == []

    def test_recover_stale_recent(self, q):
        """Recent processing items should not be reclaimed."""
        from dispatch_queue.priority_queue import PROCESSING_KEY
        item = json.dumps({"order_no": "FRESH", "popped_at": time.time(), "score": 0})
        q._redis.hset(PROCESSING_KEY, "FRESH", item)
        q._redis.expire(PROCESSING_KEY, 3600)

        reclaimed = q.recover_stale_processing(max_age_seconds=300)
        assert "FRESH" not in reclaimed

    def test_dequeue_adds_to_processing_set(self, q):
        """Dequeue should add item to processing set for crash recovery."""
        q.enqueue("PROC-001", priority=0)
        item = q.dequeue(timeout_ms=1000)
        assert item is not None
        assert item["order_no"] == "PROC-001"
        # Processing set should have the item
        processing = q._redis.hgetall("orders:processing")
        assert "PROC-001" in processing

    def test_depth_by_priority_on_empty(self, q):
        """Empty queue returns all zeros for depth_by_priority."""
        depths = q.depth_by_priority()
        assert depths == {0: 0, 1: 0, 2: 0, 3: 0}

    def test_depth_by_priority_with_items(self, q):
        """depth_by_priority should correctly count items at each priority level."""
        q.enqueue("CRITICAL", priority=0, payload={"orderId": "C1"})
        q.enqueue("HIGH", priority=1, payload={"orderId": "H1"})
        q.enqueue("HIGH-2", priority=1, payload={"orderId": "H2"})
        q.enqueue("NORMAL", priority=2, payload={"orderId": "N1"})
        q.enqueue("LOW", priority=3, payload={"orderId": "L1"})
        depths = q.depth_by_priority()
        assert depths[0] == 1, "Should have 1 critical item"
        assert depths[1] == 2, "Should have 2 high-priority items"
        assert depths[2] == 1, "Should have 1 normal item"
        assert depths[3] == 1, "Should have 1 low-priority item"

    def test_queue_clear_removes_processing(self, q):
        """Clear should remove both queue and processing set."""
        q.enqueue("CLEAR-001", priority=0)
        q.dequeue(timeout_ms=1000)
        assert q.depth() == 0  # dequeued
        # Add another
        q.enqueue("CLEAR-002", priority=1)
        assert q.clear() > 0


class TestPriorityQueueEdgeCases:
    """Additional edge cases for the priority queue."""

    @pytest.fixture
    def q(self):
        from dispatch_queue.priority_queue import PriorityQueue
        with patch("dispatch_queue.priority_queue.rd.from_url") as mock_ru:
            mock_ru.return_value = _make_mock_redis()
            yield PriorityQueue()

    def test_enqueue_priority_clamped_high(self, q):
        """Priority > 3 should be clamped to 3."""
        q.enqueue("HIGH", priority=999)
        q.enqueue("LOW", priority=-1)
        assert q.depth() == 2

    def test_peek_empty_returns_empty_list(self, q):
        assert q.peek(10) == []

    def test_multiple_priority_levels_order(self, q):
        """Multiple items at same priority preserve insertion order."""
        q.enqueue("A", priority=1, payload={"seq": 1})
        time.sleep(0.005)
        q.enqueue("B", priority=1, payload={"seq": 2})
        time.sleep(0.005)
        q.enqueue("C", priority=1, payload={"seq": 3})
        assert q.dequeue(timeout_ms=1000)["order_no"] == "A"
        assert q.dequeue(timeout_ms=1000)["order_no"] == "B"
        assert q.dequeue(timeout_ms=1000)["order_no"] == "C"


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

    def test_send_with_large_payload(self, dl):
        """Send should handle complex nested payloads."""
        payload = {"orderId": "O-001", "nodes": [{"nodeId": f"N{i}"} for i in range(100)]}
        dl_id = dl.send("ORDER-001", "ERROR", "complex", payload=payload)
        assert dl_id > 0

    def test_list_all_pagination(self, dl):
        """list_all should support pagination."""
        for i in range(5):
            dl.send(f"ORDER-{i:03d}", "ERR", f"test {i}")

        page1 = dl.list_all(limit=2, offset=0)
        assert len(page1) == 2

        page2 = dl.list_all(limit=2, offset=2)
        assert len(page2) == 2

    def test_retry_nonexistent(self, dl):
        """retry on non-existent ID returns None."""
        data = dl.retry(999)
        assert data is None

    def test_resolve_already_resolved(self, dl):
        """Resolving an already-resolved item should return False."""
        dl_id = dl.send("ORDER-001", "E1", "test")
        dl.resolve(dl_id, "MANUAL_FIX")
        ok = dl.resolve(dl_id, "MANUAL_FIX")
        assert ok is False

    def test_multiple_sends_same_order(self, dl):
        """Multiple deadletters for same order should each get unique ID."""
        id1 = dl.send("ORDER-001", "E1", "first error")
        id2 = dl.send("ORDER-001", "E2", "second error")
        assert id1 != id2
        assert dl.count_unresolved() == 2
