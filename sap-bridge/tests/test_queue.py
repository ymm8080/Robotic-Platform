"""Tests for priority queue, deadletter handler, and worker."""
import json
import time
import pytest
from unittest.mock import MagicMock, patch
from dispatch_queue.priority_queue import PriorityQueue
from dispatch_queue.deadletter import DeadLetterHandler


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
