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

logger = logging.getLogger(__name__)

POLL_INTERVAL = float(os.getenv("SAP_TC_POLL_INTERVAL", "5"))
WAREHOUSE = os.getenv("SAP_TC_WAREHOUSE", "WM01")
# When "0" (default), tasks that disappear from the coordinator active list are NOT
# auto-confirmed to SAP — they remain in ``_submitted`` and require manual
# confirmation.  Set to "1" for automatic confirmation (risky: cannot
# distinguish completed from failed tasks).
AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"


class SapCoordinatorBridge:
    """Background task: SAP tasks → Coordinator orders → SAP confirm."""

    def __init__(self, tc_client, backend_provider) -> None:
        """Args:
            tc_client: TrafficCoordinatorClient instance (or None if unavailable).
            backend_provider: callable(warehouse) → backend or None.
        """
        self._tc = tc_client
        self._get_backend = backend_provider
        self._submitted: set[str] = set()   # SAP task IDs already forwarded
        self._confirmed: set[str] = set()   # SAP task IDs already confirmed
        self._inactive_since: dict[str, int] = {}  # tid → first-seen-inactive poll count
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
        if len(tasks) >= 50:
            logger.warning(
                "SAP-TC bridge: fetched 50 tasks (top limit) — "
                "可能有更多未处理任务，考虑增加 top 或缩短轮询间隔",
            )
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
        # Coordinator state includes active_assignments dict; we look for
        # SAP-prefixed orders that are no longer active (meaning completed or failed).
        active = result.data.get("active_assignments", {})
        active_order_ids = set()
        if isinstance(active, dict):
            for _robot, assign in active.items():
                if isinstance(assign, dict):
                    oid = assign.get("order_id", "")
                    if oid:
                        active_order_ids.add(oid)
                elif isinstance(assign, list):
                    for a in assign:
                        if isinstance(a, dict):
                            oid = a.get("order_id", "")
                            if oid:
                                active_order_ids.add(oid)
                else:
                    logger.warning(
                        "SAP-TC bridge: unexpected type for active_assignments "
                        "value: %s (robot=%s), skipping",
                        type(assign).__name__, _robot,
                    )
        elif isinstance(active, list):
            for a in active:
                if isinstance(a, dict):
                    oid = a.get("order_id", "")
                    if oid:
                        active_order_ids.add(oid)
        else:
            logger.warning(
                "SAP-TC bridge: unexpected type for active_assignments: %s, "
                "skipping confirmation cycle",
                type(active).__name__,
            )

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
                logger.warning(
                    "SAP-TC bridge: task %s marked FAILED by coordinator — "
                    "skipping SAP confirm, requires manual review", tid,
                )
                self._confirmed.add(tid)  # Remove from pending
                self._inactive_since.pop(tid, None)
                continue

            # Not in any explicit list — use grace-period fallback
            GRACE_POLLS = 2
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.info(
                    "SAP-TC bridge: order %s no longer active, "
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
            logger.warning(
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
