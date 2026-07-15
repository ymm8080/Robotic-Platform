"""Distributed state store ABC (§9.1: main/standby hot-switch).

Local implementation uses an in-process dict — sufficient for single-process
Docker Compose deployment. When migrating to K8s dual-replica, swap with
RedisStateStore (or EtcdStateStore) with zero code changes in consumers.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any


class StateStore(ABC):
    """Key-value state sharing abstraction for TC failover."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get value by key, or None if not found / expired."""
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: float = 0.0) -> None:
        """Set key=value with optional TTL in seconds (0 = no expiry)."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a key. No-op if not exists."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        ...


class LocalStateStore(StateStore):
    """Single-process state store using dict — for Docker Compose deployment."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._purge_if_expired(key)
            return self._data.get(key)

    def set(self, key: str, value: Any, ttl: float = 0.0) -> None:
        with self._lock:
            self._data[key] = value
            if ttl > 0:
                import time

                self._expiry[key] = time.monotonic() + ttl
            else:
                self._expiry.pop(key, None)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def exists(self, key: str) -> bool:
        with self._lock:
            self._purge_if_expired(key)
            return key in self._data

    def _purge_if_expired(self, key: str) -> None:
        if key not in self._expiry:
            return
        import time

        if time.monotonic() > self._expiry[key]:
            self._data.pop(key, None)
            self._expiry.pop(key, None)


class RedisStateStore(StateStore):
    """Redis-backed state store for multi-replica failover.

    Uses JSON serialization for values. TTL is delegated to Redis EXPIRE.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def get(self, key: str) -> Any | None:
        import json

        raw = self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: float = 0.0) -> None:
        import json

        serialized = json.dumps(value, default=str)
        if ttl > 0:
            self._redis.setex(key, int(ttl), serialized)
        else:
            self._redis.set(key, serialized)

    def delete(self, key: str) -> None:
        self._redis.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._redis.exists(key))
