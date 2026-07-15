"""Tests for the safety PLC hard-floor interface (v7 Phase 4 task 5)."""

from __future__ import annotations

import pytest

from core.config import SafetyConfig
from core.safety.safe_distance import SafeDistanceCalculator
from core.safety.safety_plc import SafetyPlc


# ── SafetyPlc 寄存器语义 ─────────────────────────────────────
def test_default_plc_legal_floor_is_1_5m():
    plc = SafetyPlc()
    assert plc.hard_floor == 1.5


def test_enforce_allows_raising_above_legal():
    plc = SafetyPlc()
    assert plc.enforce(2.0) == 2.0
    assert plc.enforce(1.5) == 1.5
    assert plc.violations() == ()


def test_enforce_rejects_lowering_below_legal():
    plc = SafetyPlc()
    assert plc.enforce(0.5) == 1.5  # clamped to legal
    assert plc.enforce(0.0) == 1.5
    assert len(plc.violations()) == 2
    v = plc.violations()[0]
    assert v.requested == 0.5
    assert v.legal_floor == 1.5
    assert v.enforced == 1.5


def test_demo_plc_explicit_lower_floor():
    assert SafetyPlc.for_demo().hard_floor == 0.5


def test_negative_floor_rejected():
    with pytest.raises(ValueError):
        SafetyPlc(-1.0)


# ── calculator 接 PLC ────────────────────────────────────────
def test_default_calculator_floor_unchanged():
    """默认 PLC (1.5m) → 既有行为不变."""
    calc = SafeDistanceCalculator()
    r = calc.compute(velocity=0.0, rtt=0.0)
    assert r.floor == 1.5
    assert r.applied == 1.5


def test_software_cannot_lower_floor_below_plc_legal():
    """config.hard_floor 被误改为 0.5, 但 PLC 法定 1.5 → applied 仍 ≥ 1.5."""
    calc = SafeDistanceCalculator(
        config=SafetyConfig(hard_floor=0.5),  # 软件误降
        plc=SafetyPlc(),  # 法定 1.5
    )
    r = calc.compute(velocity=0.0, rtt=0.0)
    assert r.floor == 1.5  # PLC enforce 钳回法定
    assert r.applied == 1.5
    assert len(calc.plc.violations()) == 1  # lowering 尝试被审计


def test_software_can_raise_floor_above_legal():
    calc = SafeDistanceCalculator(
        config=SafetyConfig(hard_floor=2.0),
        plc=SafetyPlc(),  # 法定 1.5
    )
    r = calc.compute(velocity=0.0, rtt=0.0)
    assert r.floor == 2.0  # 抬高允许
    assert r.applied == 2.0
    assert calc.plc.violations() == ()


def test_demo_plc_allows_relaxed_floor():
    """DEMO PLC (0.5) + DEMO config (0.5) → 显式降级."""
    calc = SafeDistanceCalculator(
        config=SafetyConfig(hard_floor=0.5),
        plc=SafetyPlc.for_demo(),
    )
    r = calc.compute(velocity=0.0, rtt=0.0)
    assert r.floor == 0.5
    assert r.applied == 0.5


def test_dynamic_above_floor_unchanged_by_plc():
    calc = SafeDistanceCalculator(plc=SafetyPlc())
    r = calc.compute(velocity=1.0, rtt=0.1)  # dynamic 1.9
    assert abs(r.dynamic - 1.9) < 1e-6
    assert abs(r.applied - 1.9) < 1e-6


def test_speed_cap_still_respects_plc_floor():
    """config.hard_floor=0.5 但 PLC 法定 1.5 → gap < 1.5 时限速."""
    calc = SafeDistanceCalculator(
        config=SafetyConfig(hard_floor=0.5, unsafe_speed_floor=0.2),
        plc=SafetyPlc(),  # 法定 1.5
    )
    # gap < enforced floor (1.5) → capped to unsafe_speed_floor
    assert calc.speed_cap_for_gap(velocity=1.0, rtt=0.1, available_gap=1.0) == 0.2


def test_speed_cap_not_triggered_when_gap_above_plc_floor():
    """gap > enforced PLC floor → 速度不被限制."""
    calc = SafeDistanceCalculator(
        config=SafetyConfig(hard_floor=0.5, unsafe_speed_floor=0.2),
        plc=SafetyPlc(),  # 法定 1.5
    )
    # gap (2.0) > enforced floor (1.5) → speed unchanged
    assert calc.speed_cap_for_gap(velocity=1.0, rtt=0.1, available_gap=2.0) == 1.0
