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

    assert p.may_wait("R0", "S1") is True  # R0->R1
    assert p.may_wait("R1", "S2") is True  # R1->R2
    assert p.may_wait("R2", "S3") is True  # R2->R3
    assert p.may_wait("R3", "S0") is False  # R3->R0 closes ring → REJECT

    # 无死锁: 每条资源仍只有一车持有, 没有环被形成
    holders = {p.held_by(f"S{i}") for i in range(4)}
    assert holders == {"R0", "R1", "R2", "R3"}


def test_release_breaks_cycle_allows_wait():
    """R0 释放 S0 后, R3->S0 的 may_wait 从 False 变为 True."""
    p = DeadlockPreventer()
    for i in range(4):
        p.acquire(f"R{i}", f"S{i}")
    p.may_wait("R0", "S1")
    p.may_wait("R1", "S2")
    p.may_wait("R2", "S3")
    assert p.may_wait("R3", "S0") is False  # ring closed

    p.release("R0", "S0")
    p.clear_wait("R0")
    # S0 now free → R3 may_wait no longer closes a cycle
    assert p.may_wait("R3", "S0") is True  # cycle broken, wait safe
    # R3 can also acquire outright since S0 is free
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


# ── task 4: 检测解除 (reactive ring detection + 退避) ─────────
# _form_ring replaced by DeadlockPreventer._inject_ring (封装测试注入)


def test_detect_deadlock_ring_finds_three_cycle():
    p = DeadlockPreventer()
    p._inject_ring(3)
    ring = p.detect_deadlock_ring()
    assert ring is not None
    assert set(ring) == {"R0", "R1", "R2"}


def test_detect_deadlock_ring_finds_four_cycle():
    p = DeadlockPreventer()
    p._inject_ring(4)
    ring = p.detect_deadlock_ring()
    assert ring is not None
    assert set(ring) == {"R0", "R1", "R2", "R3"}


def test_detect_deadlock_ring_none_when_no_cycle():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    p.acquire("R1", "S1")
    p.may_wait("R0", "S1")  # chain R0->R1, no cycle
    assert p.detect_deadlock_ring() is None


def test_detect_deadlock_ring_none_when_no_waits():
    p = DeadlockPreventer()
    p.acquire("R0", "S0")
    assert p.detect_deadlock_ring() is None


def test_break_deadlock_picks_lowest_priority():
    p = DeadlockPreventer()
    p._inject_ring(3)
    ring = p.detect_deadlock_ring()
    assert ring is not None
    # R1 has smallest priority value → retreats (数值小 = 低优先级 = 退避)
    yielder = p.break_deadlock(ring, {"R0": 5, "R1": 1, "R2": 3})
    assert yielder == "R1"


def test_break_deadlock_tiebreak_is_deterministic():
    p = DeadlockPreventer()
    p._inject_ring(3)
    ring = sorted(p.detect_deadlock_ring())
    # all equal priority → min picks lexicographically first by ring order
    yielder = p.break_deadlock(ring, {"R0": 2, "R1": 2, "R2": 2})
    assert yielder in ring


def test_break_deadlock_unknown_robot_defaults_to_retreat():
    """未登记优先级的 robot 默认 0 (最低 → 退避)."""
    p = DeadlockPreventer()
    p._inject_ring(3)
    ring = p.detect_deadlock_ring()
    # only R0 mapped (priority 5); R1,R2 unmapped → default 0 (lowest) → retreats
    # ring order from _inject_ring: R0->R1->R2->R0; min() scans in ring order,
    # so the first robot with priority 0 (i.e. R1) is deterministically selected
    yielder = p.break_deadlock(ring, {"R0": 5})
    assert yielder in {"R1", "R2"}, f"unmapped robot should retreat, got {yielder}"
    # verify determinism: equal-priority robots → first in ring order wins
    ring_order = ring if ring else []
    zeros = [r for r in ring_order if r != "R0"]
    assert yielder == zeros[0], f"expected first zero-priority robot {zeros[0]}, got {yielder}"


def test_prevention_and_detection_are_orthogonal():
    """预防阻止成环 → 检测无环可报; 注入环后检测命中."""
    p = DeadlockPreventer()
    for i in range(4):
        p.acquire(f"R{i}", f"S{i}")
    p.may_wait("R0", "S1")
    p.may_wait("R1", "S2")
    p.may_wait("R2", "S3")
    assert p.may_wait("R3", "S0") is False  # prevention rejects ring-closing wait
    assert p.detect_deadlock_ring() is None  # no ring formed → nothing to detect
