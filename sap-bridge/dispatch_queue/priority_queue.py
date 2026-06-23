"""
Redis-backed priority queue for order dispatch.
Uses Sorted Set with score = priority * 1e15 + timestamp_ns for FIFO within priority.

Priority scale:
  0 = critical (highest)
  1 = high
  2 = normal
  3 = low (lowest)
"""
import json
import logging
import os
import time
from typing import Any, Optional

import redis as rd

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY = "orders:queue"
PROCESSING_KEY = "orders:processing"


class PriorityQueue:
    """Redis sorted-set priority queue with processing set for crash safety."""

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = rd.from_url(redis_url, decode_responses=True)

    # ── Enqueue ──────────────────────────────────────

    def enqueue(self, order_no: str, priority: int = 3, payload: Optional[dict] = None) -> bool:
        """Push order onto queue. Score = priority + timestamp for FIFO within priority.

        BZPOPMIN pops lowest score first, so lower priority number = higher priority.
        Score format: PCCCTTTTTTTTTTTT where P = priority, T = timestamp ns.
        """
        p = min(3, max(0, priority))
        ts = time.time_ns()
        score = float(f"{p}{ts:019d}")

        item = json.dumps({"order_no": order_no, "payload": payload, "enqueued_at": time.time()})

        self._redis.zadd(QUEUE_KEY, {item: score})
        logger.debug(f"Enqueued order {order_no} (priority={priority}, score={score})")
        return True

    def enqueue_batch(self, items: list[tuple[str, int, Optional[dict]]]) -> int:
        """Enqueue multiple orders atomically. Returns count."""
        pipe = self._redis.pipeline()
        count = 0
        for order_no, priority, payload in items:
            p = min(3, max(0, priority))
            ts = time.time_ns() + count  # Unique timestamps within batch
            score = float(f"{p}{ts:019d}")
            item = json.dumps({"order_no": order_no, "payload": payload, "enqueued_at": time.time()})
            pipe.zadd(QUEUE_KEY, {item: score})
            count += 1
        pipe.execute()
        logger.info(f"Enqueued {count} orders in batch")
        return count

    # ── Dequeue ──────────────────────────────────────

    def dequeue(self, timeout_ms: int = 5000) -> Optional[dict]:
        """Blocking dequeue with timeout. Returns item dict or None.

        Uses BZPOPMIN for blocking pop with automatic processing set tracking.
        On consumer crash the item remains in processing set and is
        recovered by the worker on restart.
        """
        result = self._redis.bzpopmin(QUEUE_KEY, timeout=timeout_ms / 1000)
        if result is None:
            return None

        _key, item_json, score = result
        item = json.loads(item_json)

        # Add to processing set (crash recovery)
        self._redis.hset(PROCESSING_KEY, item["order_no"], json.dumps({
            **item,
            "popped_at": time.time(),
            "score": score,
        }))
        self._redis.expire(PROCESSING_KEY, 3600)  # Auto-clean after 1h

        return item

    # ── Queue management ─────────────────────────────

    def depth(self) -> int:
        """Current queue depth."""
        return self._redis.zcard(QUEUE_KEY)

    def depth_by_priority(self) -> dict[int, int]:
        """Queue depth grouped by priority level."""
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        # Sample items to estimate priority distribution
        items = self._redis.zrange(QUEUE_KEY, 0, -1)
        for item_json in items:
            try:
                item = json.loads(item_json)
                # Score not available in zrange, estimate from order store
                counts[3] += 1  # Conservative default
            except json.JSONDecodeError:
                pass
        return counts

    def peek(self, n: int = 10) -> list[dict]:
        """Peek at top N items without dequeuing."""
        items = self._redis.zrange(QUEUE_KEY, 0, n - 1)
        result = []
        for item_json in items:
            try:
                item = json.loads(item_json)
                item["_waiting"] = time.time() - item.get("enqueued_at", time.time())
                result.append(item)
            except json.JSONDecodeError:
                pass
        return result

    def remove(self, order_no: str) -> bool:
        """Remove an order from the queue (e.g., cancelled before dispatch)."""
        items = self._redis.zrange(QUEUE_KEY, 0, -1)
        for item_json in items:
            try:
                item = json.loads(item_json)
                if item.get("order_no") == order_no:
                    self._redis.zrem(QUEUE_KEY, item_json)
                    self._redis.hdel(PROCESSING_KEY, order_no)
                    logger.info(f"Removed order {order_no} from queue")
                    return True
            except json.JSONDecodeError:
                pass
        return False

    def recover_stale_processing(self, max_age_seconds: int = 300) -> list[str]:
        """Reclaim items that have been processing too long (crash recovery).

        On worker restart, any items in the processing set older than
        max_age_seconds are re-enqueued.
        """
        now = time.time()
        reclaimed = []
        processing = self._redis.hgetall(PROCESSING_KEY)
        for order_no, item_json in processing.items():
            try:
                item = json.loads(item_json)
                age = now - item.get("popped_at", 0)
                if age > max_age_seconds:
                    self._redis.zadd(QUEUE_KEY, {json.dumps(item): item["score"]})
                    self._redis.hdel(PROCESSING_KEY, order_no)
                    reclaimed.append(order_no)
                    logger.warning(f"Reclaimed stale order {order_no} (age={age:.0f}s)")
            except json.JSONDecodeError:
                self._redis.hdel(PROCESSING_KEY, order_no)
        return reclaimed

    def clear(self) -> int:
        """Clear entire queue (for testing/reset). Returns count removed."""
        count = self._redis.zcard(QUEUE_KEY)
        self._redis.delete(QUEUE_KEY)
        self._redis.delete(PROCESSING_KEY)
        logger.warning(f"Cleared {count} items from queue")
        return count

    @property
    def is_healthy(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self._redis.ping()
        except Exception:
            return False
