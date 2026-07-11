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
        self._inactive_since: dict[str, float] = {}  # tid → first-seen-inactive timestamp
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
        """Check Coordinator state for completed assignments → confirm to SAP.

        The coordinator exposes only active assignments, not a completed list.
        To reduce false-positive confirmations, we require an order to be
        inactive for at least 2 consecutive polls before confirming to SAP.
        """
        import time
        self._poll_count += 1
        now = time.monotonic()
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

        GRACE_POLLS = 2
        for tid in list(self._submitted):
            if tid in self._confirmed:
                continue
            order_id = f"SAP-{tid}"
            if order_id in active_order_ids:
                self._inactive_since.pop(tid, None)
                continue  # still active
            # Not active — track when we first saw it inactive
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.info("SAP-TC bridge: order %s no longer active, waiting %d polls before confirming", order_id, GRACE_POLLS)
                continue
            # Check grace period
            if self._poll_count - self._inactive_since[tid] < GRACE_POLLS:
                continue
            # Grace period elapsed — confirm to SAP.
            # NOTE: coordinator doesn't expose failure/cancel status, so we
            # cannot distinguish completed from failed here. Log at WARNING.
            logger.warning("SAP-TC bridge: confirming SAP task %s as completed (cannot distinguish completed/failed from coordinator state)", tid)
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
