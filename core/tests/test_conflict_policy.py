"""Tests for brand conflict-tier degradation (v7 Phase 4 task 2)."""

from __future__ import annotations

import pytest

from core.adapter.brands.brand_knowledge import BrandKnowledge, get_brand_knowledge
from core.scheduling.conflict_policy import (
    ConflictPolicyResolver,
    ConflictTier,
    ReservationPolicy,
    infer_conflict_tier,
)

_COMPLIANT = ["mir", "otto", "kuka"]
_SEMI_OPEN = ["geekplus", "hairobotics"]
_BLACKBOX = ["quicktron"]


# ── tier 推导 (证据驱动) ──────────────────────────────────────
@pytest.mark.parametrize("brand", _COMPLIANT)
def test_infer_tier_compliant(brand: str):
    assert infer_conflict_tier(get_brand_knowledge(brand)) is ConflictTier.COMPLIANT


@pytest.mark.parametrize("brand", _SEMI_OPEN)
def test_infer_tier_semi_open(brand: str):
    assert infer_conflict_tier(get_brand_knowledge(brand)) is ConflictTier.SEMI_OPEN


@pytest.mark.parametrize("brand", _BLACKBOX)
def test_infer_tier_blackbox(brand: str):
    assert infer_conflict_tier(get_brand_knowledge(brand)) is ConflictTier.BLACKBOX


def test_protocol_split_implies_semi_open():
    bk = BrandKnowledge(
        brand="x",
        supported_versions=("2.0.0",),
        default_capability_vector={"max_speed": 1.0},
        error_quirks={"series_split": "proprietary"},
        field_mapping={"mode_field": "operatingMode"},
    )
    assert infer_conflict_tier(bk) is ConflictTier.SEMI_OPEN


def test_standard_mode_field_implies_compliant():
    bk = BrandKnowledge(
        brand="y",
        supported_versions=("2.0.0",),
        default_capability_vector={"max_speed": 1.0},
        field_mapping={"mode_field": "operatingMode"},
    )
    assert infer_conflict_tier(bk) is ConflictTier.COMPLIANT


def test_custom_mode_field_implies_blackbox():
    bk = BrandKnowledge(
        brand="z",
        supported_versions=("1.1.0",),
        default_capability_vector={"max_speed": 1.0},
        field_mapping={"mode_field": "robotStatus"},
    )
    assert infer_conflict_tier(bk) is ConflictTier.BLACKBOX


# ── tier → policy 映射 (合规→节点, 半开放→车道令牌, 黑盒→信号灯) ──
@pytest.mark.parametrize("brand", _COMPLIANT)
def test_policy_compliant_is_node_booking(brand: str):
    assert ConflictPolicyResolver.policy_for_brand(brand) is ReservationPolicy.NODE_BOOKING


@pytest.mark.parametrize("brand", _SEMI_OPEN)
def test_policy_semi_open_is_lane_token(brand: str):
    assert ConflictPolicyResolver.policy_for_brand(brand) is ReservationPolicy.LANE_TOKEN


@pytest.mark.parametrize("brand", _BLACKBOX)
def test_policy_blackbox_is_signal_light(brand: str):
    assert ConflictPolicyResolver.policy_for_brand(brand) is ReservationPolicy.SIGNAL_LIGHT


# ── resolver 端到端 ──────────────────────────────────────────
def test_resolver_tier_and_policy_consistent():
    for brand in _COMPLIANT + _SEMI_OPEN + _BLACKBOX:
        tier = ConflictPolicyResolver.tier_for_brand(brand)
        policy = ConflictPolicyResolver.policy_for_brand(brand)
        expected = {
            ConflictTier.COMPLIANT: ReservationPolicy.NODE_BOOKING,
            ConflictTier.SEMI_OPEN: ReservationPolicy.LANE_TOKEN,
            ConflictTier.BLACKBOX: ReservationPolicy.SIGNAL_LIGHT,
        }[tier]
        assert policy is expected


def test_unknown_brand_raises():
    """未知品牌抛出 KeyError — 由底层 get_brand_knowledge 抛出, 非 resolver 自身.

    若未来 get_brand_knowledge 改为返回默认值而非抛异常, 此测试需同步更新.
    """
    with pytest.raises(KeyError):
        ConflictPolicyResolver.tier_for_brand("nonexistent-brand")


def test_blackbox_is_safest_default():
    """未知/黑盒品牌 → SIGNAL_LIGHT (平台对所有品牌可控的最低假设)."""
    bk = BrandKnowledge(
        brand="unknown",
        supported_versions=("1.0.0",),
        default_capability_vector={"max_speed": 1.0},
        field_mapping={"mode_field": "weirdField"},
    )
    assert infer_conflict_tier(bk) is ConflictTier.BLACKBOX
    assert ConflictPolicyResolver.policy_for(bk) is ReservationPolicy.SIGNAL_LIGHT
