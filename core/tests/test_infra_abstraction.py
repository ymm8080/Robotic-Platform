"""Tests for infrastructure abstraction layer (LockManager + StateStore)."""
from __future__ import annotations

import threading
import time

from core.infra import LocalLockManager, LocalStateStore


# ── LockManager ──────────────────────────────────────────────
def test_lock_acquire_and_release():
    lm = LocalLockManager()
    assert lm.acquire("zone_1")
    assert lm.is_held("zone_1")
    lm.release("zone_1")
    assert not lm.is_held("zone_1")


def test_lock_blocks_second_acquire():
    lm = LocalLockManager()
    assert lm.acquire("resource_a")
    # second acquire from same thread should also block (Lock is not reentrant)
    # use short timeout to verify it cannot acquire
    assert not lm.acquire("resource_a", timeout=0.1)
    lm.release("resource_a")


def test_lock_cross_thread_contention():
    lm = LocalLockManager()
    lm.acquire("shared")
    results: list[bool] = []

    def try_grab():
        results.append(lm.acquire("shared", timeout=0.2))

    t = threading.Thread(target=try_grab)
    t.start()
    t.join()
    assert results == [False]
    lm.release("shared")


# ── StateStore ───────────────────────────────────────────────
def test_state_set_get_delete():
    store = LocalStateStore()
    store.set("tc_role", "active")
    assert store.get("tc_role") == "active"
    assert store.exists("tc_role")
    store.delete("tc_role")
    assert not store.exists("tc_role")
    assert store.get("tc_role") is None


def test_state_ttl_expiry():
    store = LocalStateStore()
    store.set("heartbeat", "alive", ttl=0.1)
    assert store.exists("heartbeat")
    time.sleep(0.15)
    assert not store.exists("heartbeat")
    assert store.get("heartbeat") is None


def test_state_no_ttl_persists():
    store = LocalStateStore()
    store.set("config", {"mode": "PRODUCTION"})
    assert store.get("config") == {"mode": "PRODUCTION"}
