"""In-memory store for robot-reported pick results.

The SAP ZEWM two-step warehouse-task confirmation requires the *actual*
quantity a robot picked (``nista``), the destination bin reached (``nlpla``)
and any exception code.  VDA5050 carries no pick-quantity concept, so a robot
strategy adapter (or site integration) reports these facts by POSTing to the
sap-bridge ``/api/v1/pick-result`` endpoint, which stores them here keyed by
SAP task id.  ``SapCoordinatorBridge`` consumes the stored result at
confirmation time.

Thread-safe: the bridge polls on an asyncio loop while the HTTP handler runs
on FastAPI's threadpool, so all access is guarded by a lock.

The store is intentionally in-memory and process-local — it is a short-lived
handoff buffer between a pick report and the next confirm cycle (seconds), not
a durable record.  If the process restarts between pick and confirm, the task
is left for manual SAP review rather than confirmed with a fabricated qty.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PickResult:
    """One robot-reported pick result for a single SAP warehouse task."""

    task_id: str
    robot_id: str
    actual_qty: float
    dest_bin: str | None = None
    exception: str | None = None
    extra: dict = field(default_factory=dict)


class PickResultStore:
    """Thread-safe map of ``task_id → PickResult``."""

    def __init__(self) -> None:
        self._results: dict[str, PickResult] = {}
        self._lock = threading.Lock()

    def record(self, result: PickResult) -> None:
        """Insert or overwrite the pick result for ``result.task_id``."""
        with self._lock:
            self._results[result.task_id] = result
        logger.info(
            "pick-result stored: task=%s robot=%s qty=%s dest=%s exc=%s",
            result.task_id,
            result.robot_id,
            result.actual_qty,
            result.dest_bin,
            result.exception,
        )

    def get(self, task_id: str) -> PickResult | None:
        with self._lock:
            return self._results.get(task_id)

    def pop(self, task_id: str) -> PickResult | None:
        """Remove and return the result for ``task_id`` (or None)."""
        with self._lock:
            return self._results.pop(task_id, None)

    def clear(self) -> None:
        """Remove all pick results (mainly for testing)."""
        with self._lock:
            self._results.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._results)


# Module-level singleton — shared by the HTTP handler and the bridge.
_store: PickResultStore | None = None
_store_lock = threading.Lock()


def get_pick_result_store() -> PickResultStore:
    """Return the process-wide :class:`PickResultStore` singleton."""
    global _store
    with _store_lock:
        if _store is None:
            _store = PickResultStore()
    return _store
