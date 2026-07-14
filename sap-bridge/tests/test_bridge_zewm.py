"""Tests for ZEWM_ROBCO wiring inside SapCoordinatorBridge (Phase 3).

The bridge is driven with a mocked coordinator client (``state_async``) and a
mocked ``ZewmRobcoClient`` so no SAP or coordinator process is required.  Each
test exercises one branch of the dispatch loop:

* assign on observed assignment (idempotent)
* two-step confirm on completion with a reported pick quantity
* completion without a pick result → await (no fabricated qty)
* failure → set_robot_status + unassign_robot_who
* disabled (zewm_client=None) → standard backend.confirm_task
* step-2 retry exhaustion → manual review
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from clients.traffic_coordinator_client import ClientResult
from clients.zewm_robco_exceptions import WhtNotConfirmedError
from services.pick_result_store import PickResult, get_pick_result_store
from services.sap_coordinator_bridge import SapCoordinatorBridge


def _tc_with_state(state_data):
    tc = MagicMock()

    async def _state():
        return ClientResult(ok=True, data=state_data)

    async def _submit(_order):
        return ClientResult(ok=True)

    tc.state_async = _state
    tc.submit_order_async = _submit
    return tc


def _make_bridge(state_data, zewm=None):
    tc = _tc_with_state(state_data)
    backend = MagicMock()
    backend.list_tasks = MagicMock(return_value=[])
    return SapCoordinatorBridge(tc_client=tc, backend_provider=lambda w: backend, zewm_client=zewm)


def _zewm_mock():
    z = MagicMock()
    z._confirm_retry_max = 3
    z._confirm_retry_backoff_base = 0
    z._confirm_retry_backoff_cap = 0
    return z


def _clear_pick_store():
    get_pick_result_store().clear()


def test_assign_on_observed_assignment_is_idempotent():
    """Observing an active SAP assignment registers it in SAP exactly once."""
    state = {
        "assignments": {"MIR_001": {"task_id": "SAP-1001", "path": [], "max_speed": 1.0}},
        "recently_completed": [],
        "recently_failed": [],
    }
    zewm = _zewm_mock()
    bridge = _make_bridge(state, zewm=zewm)
    bridge._submitted.add("1001")

    asyncio.run(bridge._poll_coordinator_state())
    assert zewm.assign_robot_who.call_count == 1
    assert zewm.assign_robot_who.call_args == ((("WM01", "MIR_001", "1001")),)
    assert bridge._robot_for_task["1001"] == "MIR_001"
    assert "1001" in bridge._assigned

    # Second poll must NOT register again.
    asyncio.run(bridge._poll_coordinator_state())
    assert zewm.assign_robot_who.call_count == 1


def test_completion_with_pick_result_two_step_confirm():
    """Completion + reported pick qty → step-1 then step-2 with nista/nlpla."""
    _clear_pick_store()
    state = {
        "assignments": {},
        "recently_completed": [["1002", 1.0]],
        "recently_failed": [],
    }
    zewm = _zewm_mock()
    bridge = _make_bridge(state, zewm=zewm)
    bridge._submitted.add("1002")
    bridge._robot_for_task["1002"] = "MIR_002"
    bridge._assigned.add("1002")
    get_pick_result_store().record(PickResult(task_id="1002", robot_id="MIR_002", actual_qty=5.0, dest_bin="BIN9"))

    asyncio.run(bridge._poll_coordinator_state())

    assert zewm.confirm_task_step_1.call_args == (("WM01", "1002", "MIR_002"),)
    assert zewm.confirm_task.called
    # nista is the formatted actual qty; nlpla the dest bin; conf_exc None.
    args, kwargs = zewm.confirm_task.call_args
    assert args == ("WM01", "1002", "5", "MIR_002")
    assert kwargs == {"nlpla": "BIN9", "conf_exc": None}
    assert "1002" in bridge._confirmed
    assert get_pick_result_store().get("1002") is None  # pick result consumed


def test_completion_without_pick_result_awaits():
    """Completion with no pick result must NOT confirm (no fabricated qty)."""
    _clear_pick_store()
    state = {
        "assignments": {},
        "recently_completed": [["1003", 1.0]],
        "recently_failed": [],
    }
    zewm = _zewm_mock()
    bridge = _make_bridge(state, zewm=zewm)
    bridge._submitted.add("1003")
    bridge._robot_for_task["1003"] = "MIR_003"
    bridge._assigned.add("1003")

    asyncio.run(bridge._poll_coordinator_state())

    assert not zewm.confirm_task.called
    assert "1003" in bridge._awaiting_pick
    assert "1003" not in bridge._confirmed  # retried next cycle


def test_failure_sets_status_and_unassigns():
    """Coordinator-reported failure → set_robot_status + unassign_robot_who."""
    _clear_pick_store()
    state = {
        "assignments": {},
        "recently_completed": [],
        "recently_failed": [["1004", 1.0]],
    }
    zewm = _zewm_mock()
    bridge = _make_bridge(state, zewm=zewm)
    bridge._submitted.add("1004")
    bridge._robot_for_task["1004"] = "MIR_004"
    bridge._assigned.add("1004")

    asyncio.run(bridge._poll_coordinator_state())

    assert zewm.set_robot_status.call_args == (("WM01", "MIR_004", "BLKD"),)
    assert zewm.unassign_robot_who.call_args == (("WM01", "MIR_004", "1004"),)
    assert "1004" in bridge._manual_review


def test_disabled_path_uses_backend_confirm():
    """Without a zewm_client the bridge falls back to backend.confirm_task."""
    _clear_pick_store()
    state = {
        "assignments": {},
        "recently_completed": [["2001", 1.0]],
        "recently_failed": [],
    }
    backend = MagicMock()
    backend.list_tasks = MagicMock(return_value=[])
    backend.confirm_task = MagicMock(return_value=True)
    tc = _tc_with_state(state)
    bridge = SapCoordinatorBridge(tc_client=tc, backend_provider=lambda w: backend, zewm_client=None)
    bridge._submitted.add("2001")

    asyncio.run(bridge._poll_coordinator_state())

    assert backend.confirm_task.call_args == (("WM01", "2001", None),)
    assert "2001" in bridge._confirmed


def test_step2_retry_exhaustion_parks_manual_review():
    """Step-2 retried confirm_retry_max times then parked for manual review."""
    _clear_pick_store()
    state = {
        "assignments": {},
        "recently_completed": [["3001", 1.0]],
        "recently_failed": [],
    }
    zewm = _zewm_mock()
    zewm.confirm_task = MagicMock(side_effect=WhtNotConfirmedError("nope"))
    bridge = _make_bridge(state, zewm=zewm)
    bridge._submitted.add("3001")
    bridge._robot_for_task["3001"] = "R"
    bridge._assigned.add("3001")
    get_pick_result_store().record(PickResult(task_id="3001", robot_id="R", actual_qty=2.0, dest_bin="B"))

    asyncio.run(bridge._poll_coordinator_state())

    assert zewm.confirm_task.call_count == 3  # confirm_retry_max
    assert "3001" not in bridge._confirmed
    assert "3001" in bridge._manual_review
