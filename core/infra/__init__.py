"""Infrastructure abstraction layer — K8s migration seam (灰犀牛 #5).

Provides ABCs for distributed locking and state sharing so the coordinator
can swap from local (threading/dict) to distributed (etcd/Redis) backends
without code changes when migrating to K8s multi-replica.

Current: LocalLockManager + LocalStateStore (single-process)
Future:  EtcdLockManager + RedisStateStore (K8s dual-replica)
"""
from __future__ import annotations

from core.infra.lock_manager import LockManager, LocalLockManager
from core.infra.state_store import LocalStateStore, StateStore

__all__ = [
    "LockManager",
    "LocalLockManager",
    "StateStore",
    "LocalStateStore",
]
