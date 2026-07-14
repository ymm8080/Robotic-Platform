"""Tests for DeadlockPreventer (v7 Phase 4, 灰犀牛 #19)."""
from __future__ import annotations

from core.scheduling.deadlock_prevention import DeadlockPreventer


# ── acquire / release 基础语义 ────────────────────────────────
def test_acquire_free_resource_grants():
    p = DeadlockPreventer()
    assert p.acquire("R0", "S0") is True
    assert p.held_by("S0") == "R0"
    assert p.holds("R0") == {"S0"}


def test_acquire_busy_resource_denied():
    p = DeadlockPreventer()
    assert p.acquire("R0", "S0") is True
    assert p.acquire("R1", "S0") is False  # busy, not deadlock — caller decides wait/reroute
    assert p.held_by("S0") == "R0"


def test_release_frees_resource_for_next_robot():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.release("R0", "S0")
    assert p.held_by("S0") is None
    assert p.acquire("R1", "S0") is True


def test_release_only_by_holder():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.release("R1", "S0")  # noop — R1 doesn't hold it
    assert p.held_by("S0") == "R0"


# ── would_deadlock 预防核心 ───────────────────────────────────
def test_would_deadlock_false_for_free_resource():
    p = DeadlockPreventer()
    assert p.would_deadlock("R0", "S0") is False  # free → never deadlock


def test_would_deadlock_false_for_self_held():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    assert p.would_deadlock("R0", "S0") is False  # self-held → never deadlock


def test_would_deadlock_false_for_simple_chain_no_cycle():
    # R0 holds S0, R1 holds S1; R0 waits S1 → edge R0->R1, no cycle
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.acquire("R1", "S1")
    assert p.would_deadlock("R0", "S1") is False


# ── may_wait 登记等待边 ───────────────────────────────────────
def test_may_wait_safe_chain_records_wait():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.acquire("R1", "S1")
    assert p.may_wait("R0", "S1") is True
    assert p.waiting_for("R0") == "S1"


def test_may_wait_rejects_on_cycle():
    # 2-cycle: R0 holds S0 waits S1; R1 holds S1 waits S0 → R0->R1->R0
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.acquire("R1", "S1")
    assert p.may_wait("R0", "S1") is True
    assert p.may_wait("R1", "S0") is False  # closes 2-cycle
    # R1 not recorded as waiting
    assert p.waiting_for("R1") is None


# ── DoD: 4 车环形死锁拓扑拒绝进死锁区, 0 死锁 ─────────────────
def test_four_vehicle_ring_deadlock_prevented():
    """R0->S1->R1->S2->R2->S3->R3->S0->R0 闭环: 第 4 个等待被拒."""
    p = DeadlockPreventer()
    for i in range(4):
        assert p.acquire(f"R{i}", f"S{i}")

    assert p.may_wait("R0", "S1") is True   # R0->R1
    assert p.may_wait("R1", "S2") is True   # R1->R2
    assert p.may_wait("R2", "S3") is True   # R2->R3
    assert p.may_wait("R3", "S0") is False  # R3->R0 closes ring → REJECT

    # 无死锁: 每条资源仍只有一车持有, 没有环被形成
    holders = {p.held_by(f"S{i}") for i in range(4)}
    assert holders == {"R0", "R1", "R2", "R3"}


def test_release_breaks_cycle_allows_wait():
    """R0 释放 S0 后, R3->S0 不再成环."""
    p = DeadlockPreventer()
    for i in range(4):
        p.acquire(f"R{i}", f"S{i}")
    p.may_wait("R0", "S1")
    p.may_wait("R1", "S2")
    p.may_wait("R2", "S3")
    assert p.may_wait("R3", "S0") is False  # ring closed

    p.release("R0", "S0")
    p.clear_wait("R0")
    # S0 now free → R3 can acquire outright, no wait needed
    assert p.acquire("R3", "S0") is True


def test_transitive_cycle_three_vehicles():
    """3 车环: R0->R1->R2->R0."""
    p = DeadlockPreventer()
    for i in range(3):
        p.acquire(f"R{i}", f"S{i}")
    assert p.may_wait("R0", "S1") is True
    assert p.may_wait("R1", "S2") is True
    assert p.may_wait("R2", "S0") is False  # closes 3-cycle


def test_clear_wait_removes_waiting_edge():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.acquire("R1", "S1")
    p.may_wait("R0", "S1")
    assert p.waiting_for("R0") == "S1"
    p.clear_wait("R0")
    assert p.waiting_for("R0") is None
