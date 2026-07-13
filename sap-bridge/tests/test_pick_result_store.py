"""Tests for the in-memory PickResultStore (Phase 2).

These tests are pure unit tests — no PostgreSQL, no HTTP.  The store is the
handoff buffer between a robot pick report (POST /api/v1/pick-result) and the
SAP bridge's ZEWM two-step confirmation.
"""

from __future__ import annotations

from services.pick_result_store import PickResult, PickResultStore


def test_record_get_pop_roundtrip():
    store = PickResultStore()
    assert store.get("t1") is None
    store.record(PickResult(task_id="t1", robot_id="R1", actual_qty=5.0, dest_bin="BIN9"))
    result = store.get("t1")
    assert result is not None
    assert result.task_id == "t1"
    assert result.robot_id == "R1"
    assert result.actual_qty == 5.0
    assert result.dest_bin == "BIN9"
    assert result.exception is None

    popped = store.pop("t1")
    assert popped is not None and popped.task_id == "t1"
    assert store.get("t1") is None
    assert len(store) == 0


def test_record_overwrites_existing():
    store = PickResultStore()
    store.record(PickResult(task_id="t1", robot_id="R1", actual_qty=1.0))
    store.record(PickResult(task_id="t1", robot_id="R2", actual_qty=9.0))
    result = store.get("t1")
    assert result is not None
    assert result.robot_id == "R2"
    assert result.actual_qty == 9.0


def test_pop_missing_returns_none():
    store = PickResultStore()
    assert store.pop("nope") is None


def test_len_tracks_entries():
    store = PickResultStore()
    assert len(store) == 0
    store.record(PickResult(task_id="t1", robot_id="R1", actual_qty=1.0))
    store.record(PickResult(task_id="t2", robot_id="R1", actual_qty=2.0))
    assert len(store) == 2
    store.pop("t1")
    assert len(store) == 1


def test_exception_field_preserved():
    store = PickResultStore()
    store.record(PickResult(task_id="t1", robot_id="R1", actual_qty=3.0, exception="BLKD"))
    assert store.get("t1").exception == "BLKD"
