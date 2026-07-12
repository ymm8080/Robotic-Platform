"""SAP ↔ v5.0 Coordinator bridge — background polling service.

Polls SAP EWM warehouse tasks (status=open) and forwards them to the
v5.0 Traffic Coordinator as lane-based orders.  When the Coordinator
reports completed assignments, confirms back to SAP.

Runs as an asyncio task inside the SAP Bridge process.  All SAP I/O is
delegated to the existing backend layer; all Coordinator I/O goes
through TrafficCoordinatorClient.

Env vars:
  SAP_TC_BRIDGE_ENABLED  — "1" to enable (default: "1" if ENABLE_V5)
  SAP_TC_POLL_INTERVAL   — seconds between SAP polls (default: 5)
  SAP_TC_WAREHOUSE       — warehouse ID for SAP task queries (default: "WM01")
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clients.traffic_coordinator_client import TrafficCoordinatorClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = float(os.getenv("SAP_TC_POLL_INTERVAL", "5"))
# Number of polls to wait before auto-confirming a task that disappeared
# from the coordinator active list without an explicit completion/failure.
GRACE_POLLS = int(os.getenv("SAP_TC_GRACE_POLLS", "2"))
WAREHOUSE = os.getenv("SAP_TC_WAREHOUSE", "WM01")
# When "0", tasks that disappear from the coordinator active list are NOT
# auto-confirmed to SAP — they remain in ``_submitted`` and require manual
# confirmation.  Set to "1" (default) for automatic confirmation.
AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "1") == "1"


@dataclass
class CoordinatorAssignment:
    """Structured representation of one active coordinator assignment."""

    task_id: str = ""
    path: list[str] = field(default_factory=list)
    max_speed: float = 0.0

    @property
    def order_id(self) -> str:
        """Extract the order_id from the task_id (format: ``order_id`` or ``charge:robot_id``)."""
        return self.task_id


@dataclass
class CoordinatorState:
    """Typed wrapper for the coordinator ``/state`` response.

    Provides a stable, typed interface for downstream consumers (like the
    SAP bridge) so that changes to the raw API response structure do not
    cause silent failures.
    """

    active_assignments: int = 0
    assignments: dict[str, CoordinatorAssignment] = field(default_factory=dict)
    pending_tasks: int = 0

    @classmethod
    def from_api(cls, data: dict | None) -> CoordinatorState:
        """Parse a raw API response dict into a typed object.

        Falls back gracefully: if the ``assignments`` field is missing,
        returns an empty dict so callers can treat ``not state.assignments``
        uniformly.
        """
        if not data or not isinstance(data, dict):
            return cls()
        raw_assignments = data.get("assignments", {})
        assignments: dict[str, CoordinatorAssignment] = {}
        if isinstance(raw_assignments, dict):
            for robot_id, raw in raw_assignments.items():
                if not isinstance(raw, dict):
                    continue
                assignments[robot_id] = CoordinatorAssignment(
                    task_id=str(raw.get("task_id", "")),
                    path=list(raw.get("path", [])),
                    max_speed=float(raw.get("max_speed", 0.0)),
                )
        return cls(
            active_assignments=int(data.get("active_assignments", 0)),
            assignments=assignments,
            pending_tasks=int(data.get("pending_tasks", 0)),
        )

    @property
    def active_order_ids(self) -> set[str]:
        """Return the set of task_ids currently active in the coordinator."""
        return {a.order_id for a in self.assignments.values()}


class SapCoordinatorBridge:
    """Background task: SAP tasks → Coordinator orders → SAP confirm."""

    def __init__(
        self,
        tc_client: TrafficCoordinatorClient | None,
        backend_provider: Callable[[str], object | None],
    ) -> None:
        """Args:
            tc_client: TrafficCoordinatorClient instance (or None if unavailable).
            backend_provider: callable(warehouse) → backend or None.
        """
        self._tc = tc_client
        self._get_backend = backend_provider
        self._submitted: set[str] = set()   # SAP task IDs already forwarded
        self._confirmed: set[str] = set()   # SAP task IDs already confirmed
        self._inactive_since: dict[str, int] = {}  # tid → first-seen-inactive timestamp
        self._poll_count: int = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._tc is None:
            logger.warning("SAP-TC bridge: coordinator client unavailable, not starting")
            return
        self._task = asyncio.create_task(self._run(), name="sap-tc-bridge")
        logger.info("SAP-TC bridge started (poll=%ss, warehouse=%s)", POLL_INTERVAL, WAREHOUSE)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("SAP-TC bridge stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._poll_sap_tasks()
                await self._poll_coordinator_state()
            except Exception as exc:
                logger.warning("SAP-TC bridge cycle error: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=POLL_INTERVAL)

    async def _poll_sap_tasks(self) -> None:
        """Fetch open SAP tasks and forward new ones to the Coordinator."""
        backend = self._get_backend(WAREHOUSE)
        if backend is None:
            return
        tasks = await asyncio.to_thread(backend.list_tasks, warehouse=WAREHOUSE, status="0", top=50)
        for task in tasks:
            tid = task.external_id
            if tid in self._submitted:
                continue
            tc_order = {
                "order_id": f"SAP-{tid}",
                "origin_lane": task.source_bin or "",
                "destination_lane": task.dest_bin or "",
                "actions": ["MOVE"],
                "payload_kg": 0.0,
                "priority": 1,
            }
            result = await self._tc.submit_order_async(tc_order)
            if result.ok:
                self._submitted.add(tid)
                logger.info("SAP-TC bridge: forwarded task %s → coordinator order SAP-%s", tid, tid)
            else:
                logger.warning("SAP-TC bridge: submit failed for task %s: %s", tid, result.error)

    async def _poll_coordinator_state(self) -> None:
        """Check Coordinator state for completed/failed assignments → confirm to SAP.

        The coordinator snapshot exposes ``recently_completed`` and
        ``recently_failed`` task ID lists, allowing the bridge to
        distinguish success from failure instead of guessing from the
        absence in the active list.
        """
        self._poll_count += 1
        result = await self._tc.state_async()
        if not result.ok or not result.data:
            return

        # Use the typed CoordinatorState wrapper instead of fragile inline
        # dict/list parsing.  This ensures that changes to the API response
        # structure are handled gracefully.
        state = CoordinatorState.from_api(result.data)
        active_order_ids = state.active_order_ids

        # Coordinator snapshot exposes explicit success/failure lists.
        completed_task_ids = set(result.data.get("recently_completed", []))
        failed_task_ids = set(result.data.get("recently_failed", []))

        for tid in list(self._submitted):
            if tid in self._confirmed:
                continue
            order_id = f"SAP-{tid}"
            if order_id in active_order_ids:
                self._inactive_since.pop(tid, None)
                continue  # still active

            # Check explicit completion confirmation
            if tid in completed_task_ids:
                backend = self._get_backend(WAREHOUSE)
                if backend is None:
                    continue
                ok = await asyncio.to_thread(backend.confirm_task, WAREHOUSE, tid, None)
                if ok:
                    self._confirmed.add(tid)
                    self._inactive_since.pop(tid, None)
                    logger.info("SAP-TC bridge: confirmed SAP task %s (completed)", tid)
                else:
                    logger.warning("SAP-TC bridge: SAP confirm failed for task %s", tid)
                continue

            # Check explicit failure
            if tid in failed_task_ids:
                logger.error(
                    "SAP-TC bridge: task %s marked FAILED by coordinator — "
                    "skipping SAP confirm, requires manual review", tid,
                )
                self._confirmed.add(tid)  # Remove from pending
                self._inactive_since.pop(tid, None)
                continue

            # Not in any explicit list — use grace-period fallback
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.info(
                    "SAP-TC bridge: order %s inactive, "
                    "waiting %d polls before confirming",
                    order_id, GRACE_POLLS,
                )
                continue
            if self._poll_count - self._inactive_since[tid] < GRACE_POLLS:
                continue
            # Grace period elapsed, still no explicit status.
            if not AUTO_CONFIRM:
                logger.warning(
                    "SAP-TC bridge: task %s inactive for %d polls but AUTO_CONFIRM=0 — "
                    "skipping SAP confirm, requires manual review", tid, GRACE_POLLS,
                )
                continue
            logger.info(
                "SAP-TC bridge: confirming SAP task %s "
                "(no explicit status, grace period elapsed)",
                tid,
            )
            backend = self._get_backend(WAREHOUSE)
            if backend is None:
                continue
            ok = await asyncio.to_thread(backend.confirm_task, WAREHOUSE, tid, None)
            if ok:
                self._confirmed.add(tid)
                self._inactive_since.pop(tid, None)
                logger.info("SAP-TC bridge: confirmed SAP task %s", tid)
            else:
                logger.warning("SAP-TC bridge: SAP confirm failed for task %s", tid)
