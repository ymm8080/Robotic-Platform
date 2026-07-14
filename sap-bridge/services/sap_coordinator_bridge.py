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

from clients.zewm_robco_exceptions import (
    RobcoError,
    RobotHasOrderError,
    WhoAssignedError,
    WhoInProcessError,
    WhoLockedError,
    WhoNotUnassignedError,
    WhtAlreadyConfirmedError,
    WhtNotConfirmedError,
)
from clients.zewm_robco_types import ExceptionCode
from services.pick_result_store import get_pick_result_store

if TYPE_CHECKING:
    from clients.traffic_coordinator_client import TrafficCoordinatorClient
    from clients.zewm_robco_client import ZewmRobcoClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = float(os.getenv("SAP_TC_POLL_INTERVAL", "5"))
WAREHOUSE = os.getenv("SAP_TC_WAREHOUSE", "WM01")
# When "0", tasks that disappear from the coordinator active list are NOT
# auto-confirmed to SAP — they remain in ``_submitted`` and require manual
# confirmation.  Set to "1" for automatic confirmation (risky).
AUTO_CONFIRM = os.getenv("SAP_TC_AUTO_CONFIRM", "0") == "1"
# Number of consecutive polls a task must be inactive before auto-confirming.
# Configurable via SAP_TC_GRACE_POLLS (default 2) — raise for flaky links,
# lower for faster confirmation.
try:
    GRACE_POLLS = int(os.getenv("SAP_TC_GRACE_POLLS", "2"))
except (ValueError, TypeError):
    GRACE_POLLS = 2

# Maximum confirmed task IDs to retain in memory.
MAX_CONFIRMED_RETENTION = 500
# How often (in polls) to run cleanup.
CLEANUP_INTERVAL = 60

# Coordinator order IDs forwarded for SAP tasks use this prefix.
SAP_ORDER_PREFIX = "SAP-"
# ZEWM step-2 confirmation retry (exponential backoff) — plan §3.5.  These
# defaults are overridden from the ZewmRobcoClient config when a client is
# injected (see ``_confirm_two_step``).
CONFIRM_RETRY_MAX = 5
CONFIRM_RETRY_BACKOFF_BASE = 1.0
CONFIRM_RETRY_BACKOFF_CAP = 30.0


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


def _strip_sap_prefix(task_id: str) -> str | None:
    """Return the SAP task id from a coordinator order id (``SAP-<tid>``).

    Only returns the remainder when it is a non-empty numeric string,
    preventing false matches on arbitrary ``SAP-`` prefixed IDs.
    """
    if task_id.startswith(SAP_ORDER_PREFIX):
        remainder = task_id[len(SAP_ORDER_PREFIX) :]
        if remainder.isdigit():
            return remainder
    return None


def _extract_task_ids(raw) -> set[str]:
    """Extract task ids from a ``recently_*`` list.

    Accepts both ``[task_id, timestamp]`` entries (current coordinator) and
    bare ``task_id`` strings (older builds), defensively.
    """
    ids: set[str] = set()
    for item in raw or []:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, (list, tuple)) and item:
            ids.add(str(item[0]))
    return ids


def _format_qty(qty: float) -> str:
    """Format an actual quantity for SAP ``nista`` (compact decimal string)."""
    text = f"{qty:.3f}".rstrip("0").rstrip(".")
    return text or "0"


class SapCoordinatorBridge:
    """Background task: SAP tasks → Coordinator orders → SAP confirm."""

    def __init__(
        self,
        tc_client: TrafficCoordinatorClient | None,
        backend_provider: Callable[[str], object | None],
        zewm_client: ZewmRobcoClient | None = None,
    ) -> None:
        """Args:
        tc_client: TrafficCoordinatorClient instance (or None if unavailable).
        backend_provider: callable(warehouse) → backend or None.
        zewm_client: ZewmRobcoClient instance for robot-specific ZEWM_ROBCO_SRV
            operations (assign/confirm/status/unassign).  None ⇒ the bridge
            uses the standard ``backend.confirm_task`` path only.
        """
        self._tc = tc_client
        self._get_backend = backend_provider
        self._zewm = zewm_client
        self._submitted: set[str] = set()  # SAP task IDs already forwarded
        self._confirmed: set[str] = set()  # SAP task IDs already confirmed
        self._assigned: set[str] = set()  # SAP task IDs registered via assign_robot_who
        self._robot_for_task: dict[str, str] = {}  # tid → rsrc (cached from coordinator state)
        self._awaiting_pick: set[str] = set()  # completed tids waiting for a pick result
        self._manual_review: set[str] = set()  # tids parked for manual SAP review
        self._inactive_since: dict[str, int] = {}  # tid → first-seen-inactive poll count
        self._poll_count: int = 0
        self._pick_store = get_pick_result_store()
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
        ``recently_failed`` (each a list of ``[task_id, timestamp]``),
        allowing the bridge to distinguish success from failure instead of
        guessing from the absence in the active list.

        When a ``ZewmRobcoClient`` is injected, the bridge additionally:
          * registers each observed assignment in SAP via ``assign_robot_who``
            (the coordinator is the assignment authority; the bridge is the
            SAP-side registrar),
          * confirms completed tasks via the ZEWM two-step confirmation using
            the robot-reported pick quantity from :class:`PickResultStore`,
          * reports failures via ``set_robot_status`` + ``unassign_robot_who``.

        Without a ``ZewmRobcoClient`` the bridge falls back to the standard
        ``backend.confirm_task`` path exactly as before.
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

        # Cache robot (rsrc) for each active SAP task, for ZEWM assign/confirm.
        for robot_id, assignment in state.assignments.items():
            tid = _strip_sap_prefix(assignment.task_id)
            if tid and tid in self._submitted:
                self._robot_for_task[tid] = robot_id

        # Coordinator snapshot exposes explicit success/failure lists.  Each
        # entry is ``[task_id, timestamp]``; fall back to bare strings for
        # older coordinator builds.
        completed_task_ids = _extract_task_ids(result.data.get("recently_completed"))
        failed_task_ids = _extract_task_ids(result.data.get("recently_failed"))

        for tid in list(self._submitted):
            if tid in self._confirmed or tid in self._manual_review:
                continue
            order_id = f"{SAP_ORDER_PREFIX}{tid}"
            if order_id in active_order_ids:
                self._inactive_since.pop(tid, None)
                # Register the assignment in SAP (idempotent — once per tid).
                if self._zewm is not None:
                    rsrc = self._robot_for_task.get(tid)
                    if rsrc is not None:
                        await self._register_assignment(WAREHOUSE, tid, rsrc)
                continue  # still active

            # Check explicit completion confirmation
            if tid in completed_task_ids:
                if self._zewm is not None:
                    rsrc = self._robot_for_task.get(tid)
                    if rsrc is None:
                        # Never observed the active assignment (ultra-short
                        # task) — ZEWM confirm needs a resource.  Park it.
                        self._park_manual_review(tid, "completed with no known rsrc")
                        continue
                    ok = await self._confirm_two_step(WAREHOUSE, tid, rsrc)
                    if ok:
                        self._confirmed.add(tid)
                        self._inactive_since.pop(tid, None)
                        self._robot_for_task.pop(tid, None)
                        logger.info("SAP-TC bridge: ZEWM confirmed SAP task %s (completed)", tid)
                    # else: retry next cycle (pick result may still arrive)
                    continue
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
                if self._zewm is not None:
                    rsrc = self._robot_for_task.get(tid)
                    if rsrc is not None:
                        await self._handle_failure(WAREHOUSE, tid, rsrc)
                    logger.error(
                        "SAP-TC bridge: task %s FAILED by coordinator — ZEWM cleanup attempted, manual review",
                        tid,
                    )
                else:
                    logger.error(
                        "SAP-TC bridge: task %s marked FAILED by coordinator — "
                        "skipping SAP confirm, requires manual review",
                        tid,
                    )
                self._manual_review.add(tid)
                self._inactive_since.pop(tid, None)
                self._robot_for_task.pop(tid, None)
                continue

            # Not in any explicit list — use grace-period fallback
            if tid not in self._inactive_since:
                self._inactive_since[tid] = self._poll_count
                logger.debug(
                    "SAP-TC bridge: order %s inactive, waiting %d polls before confirming",
                    order_id,
                    GRACE_POLLS,
                )
                continue
            if self._poll_count - self._inactive_since[tid] < GRACE_POLLS:
                continue
            # Grace period elapsed, still no explicit status.
            if self._zewm is not None:
                # ZEWM confirmation requires a real pick result + rsrc; without
                # an explicit completion signal we cannot confirm safely.
                self._park_manual_review(tid, f"inactive {GRACE_POLLS} polls, no completion signal")
                continue
            if not AUTO_CONFIRM:
                logger.warning(
                    "SAP-TC bridge: task %s inactive for %d polls but AUTO_CONFIRM=0 — "
                    "skipping SAP confirm, requires manual review",
                    tid,
                    GRACE_POLLS,
                )
                continue
            logger.info(
                "SAP-TC bridge: confirming SAP task %s (no explicit status, grace period elapsed)",
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

        # Prune confirmed entries and stale robot-for-task cache to prevent unbounded memory growth.
        if self._poll_count % CLEANUP_INTERVAL == 0:
            # Clean up _robot_for_task entries for tasks no longer active or submitted.
            stale_robots = [tid for tid in self._robot_for_task if tid in self._confirmed or tid in self._manual_review]
            for tid in stale_robots:
                self._robot_for_task.pop(tid, None)
            if stale_robots:
                logger.debug(
                    "SAP-TC bridge: cleaned %d stale _robot_for_task entries",
                    len(stale_robots),
                )
        if self._poll_count % CLEANUP_INTERVAL == 0 and len(self._confirmed) > MAX_CONFIRMED_RETENTION:
            excess = len(self._confirmed) - MAX_CONFIRMED_RETENTION
            to_remove = list(self._confirmed)[:excess]
            for tid in to_remove:
                self._confirmed.discard(tid)
            logger.info(
                "SAP-TC bridge: pruned %d stale confirmed entries (retention=%d)",
                excess,
                MAX_CONFIRMED_RETENTION,
            )

    # ── ZEWM_ROBCO helpers (only used when a zewm_client is injected) ──────

    def _park_manual_review(self, tid: str, reason: str) -> None:
        """Mark a task as parked for manual SAP review (logged once)."""
        if tid in self._manual_review:
            logger.debug("SAP-TC bridge: task %s already in manual review (reason: %s)", tid, reason)
            return
        self._manual_review.add(tid)
        logger.warning("SAP-TC bridge: task %s parked for manual SAP review — %s", tid, reason)

    async def _register_assignment(self, lgnum: str, tid: str, rsrc: str) -> None:
        """Register the coordinator's assignment decision in SAP (idempotent)."""
        if tid in self._assigned:
            return
        try:
            await asyncio.to_thread(self._zewm.assign_robot_who, lgnum, rsrc, tid)  # type: ignore[union-attr]
            self._assigned.add(tid)
            logger.info("SAP-TC bridge: ZEWM registered assign rsrc=%s → WHO %s", rsrc, tid)
        except (WhoLockedError, WhoAssignedError, WhoInProcessError, RobotHasOrderError) as exc:
            # Transient contention with another robot/instance — retry next cycle.
            logger.debug("SAP-TC bridge: ZEWM assign retry for task %s: %s", tid, exc)
        except RobcoError as exc:
            logger.warning("SAP-TC bridge: ZEWM assign failed for task %s: %s", tid, exc)

    async def _confirm_two_step(self, lgnum: str, tid: str, rsrc: str) -> bool:
        """ZEWM two-step confirmation with step-2 retry (plan §3.5).

        Returns True if fully confirmed (or already confirmed), False to
        retry next cycle.  Never raises — all failures are logged.
        """
        zewm = self._zewm
        if zewm is None:  # caller guards on self._zewm
            return False

        # Step 1 — resource confirmation (commits immediately in SAP).
        try:
            await asyncio.to_thread(zewm.confirm_task_step_1, lgnum, tid, rsrc)
        except WhtAlreadyConfirmedError:
            pass  # already past step 1 — proceed to step 2
        except RobcoError as exc:
            logger.warning("SAP-TC bridge: ZEWM step-1 failed for task %s: %s", tid, exc)
            return False

        # Step 2 — quantity/bin/exception confirmation.  Requires the actual
        # picked quantity reported via POST /api/v1/pick-result.
        pick = self._pick_store.get(tid)
        if pick is None:
            if tid not in self._awaiting_pick:
                self._awaiting_pick.add(tid)
                logger.warning(
                    "SAP-TC bridge: task %s completed but no pick result received — "
                    "awaiting POST /api/v1/pick-result before SAP confirm",
                    tid,
                )
            return False
        self._awaiting_pick.discard(tid)

        nista = _format_qty(pick.actual_qty)
        retry_max = getattr(zewm, "_confirm_retry_max", CONFIRM_RETRY_MAX)
        backoff_base = getattr(zewm, "_confirm_retry_backoff_base", CONFIRM_RETRY_BACKOFF_BASE)
        backoff_cap = getattr(zewm, "_confirm_retry_backoff_cap", CONFIRM_RETRY_BACKOFF_CAP)

        last_exc: Exception | None = None
        for attempt in range(retry_max):
            try:
                await asyncio.to_thread(
                    zewm.confirm_task,
                    lgnum,
                    tid,
                    nista,
                    rsrc,
                    nlpla=pick.dest_bin,
                    conf_exc=pick.exception,
                )
                self._pick_store.pop(tid)
                return True
            except WhtAlreadyConfirmedError:
                self._pick_store.pop(tid)
                return True
            except (WhtNotConfirmedError, RobcoError) as exc:
                # Retryable: transient SAP/transport error.  Other RobcoError
                # subtypes are unlikely here but treated as retryable too.
                last_exc = exc
                logger.warning(
                    "SAP-TC bridge: ZEWM step-2 retry %d/%d for task %s: %s",
                    attempt + 1,
                    retry_max,
                    tid,
                    exc,
                )
                if attempt < retry_max - 1:
                    delay = min(backoff_cap, backoff_base * (2**attempt))
                    await asyncio.sleep(delay)
        logger.error(
            "SAP-TC bridge: ZEWM step-2 exhausted %d retries for task %s: %s — manual review",
            retry_max,
            tid,
            last_exc,
        )
        self._park_manual_review(tid, "ZEWM step-2 retries exhausted")
        return False

    async def _handle_failure(self, lgnum: str, tid: str, rsrc: str) -> None:
        """Report a failed task to SAP: set robot exception status + unassign WHO."""
        zewm = self._zewm
        if zewm is None:  # caller guards on self._zewm
            return
        try:
            await asyncio.to_thread(zewm.set_robot_status, lgnum, rsrc, str(ExceptionCode.BLOCKED))
        except RobcoError as exc:
            logger.warning("SAP-TC bridge: ZEWM set_robot_status failed for task %s: %s", tid, exc)
        try:
            await asyncio.to_thread(zewm.unassign_robot_who, lgnum, rsrc, tid)
            logger.info("SAP-TC bridge: ZEWM unassigned WHO %s from rsrc %s", tid, rsrc)
        except WhoNotUnassignedError as exc:
            logger.debug("SAP-TC bridge: ZEWM unassign no-op for task %s: %s", tid, exc)
        except RobcoError as exc:
            logger.warning("SAP-TC bridge: ZEWM unassign failed for task %s: %s", tid, exc)
