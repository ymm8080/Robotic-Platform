"""Distributed lock manager ABC (灰犀牛 #5: 并发写冲突).

Local implementation uses threading.Lock — sufficient for single-process
Docker Compose deployment. When migrating to K8s dual-replica, swap with
EtcdLockManager (etcd lease-based locks) with zero code changes in consumers.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod


class LockManager(ABC):
    """Distributed lock abstraction for mutual exclusion."""

    @abstractmethod
    def acquire(self, key: str, timeout: float = 10.0) -> bool:
        """Try to acquire a named lock. Returns True if acquired."""
        ...

    @abstractmethod
    def release(self, key: str) -> None:
        """Release a held lock. No-op if not held."""
        ...

    @abstractmethod
    def is_held(self, key: str) -> bool:
        """Check if a lock is currently held."""
        ...


class LocalLockManager(LockManager):
    """Single-process lock using threading — for Docker Compose deployment."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._held: set[str] = set()
        self._guard = threading.Lock()

    def acquire(self, key: str, timeout: float = 10.0) -> bool:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        acquired = lock.acquire(timeout=timeout)
        if acquired:
            self._held.add(key)
        return acquired

    def release(self, key: str) -> None:
        with self._guard:
            lock = self._locks.get(key)
        if lock is not None and lock.locked():
            lock.release()
            self._held.discard(key)

    def is_held(self, key: str) -> bool:
        return key in self._held
