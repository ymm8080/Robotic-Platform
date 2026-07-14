"""品牌冲突降级档 (v7 Phase 4 task 2).

v7 架构说明书: 三层次冲突空间中, 品牌降级正交于空间层次 —
    VDA5050 合规品牌 → 节点预订 (NODE_BOOKING)
    半开放品牌       → 车道令牌 (LANE_TOKEN)
    黑盒品牌         → 信号灯 (SIGNAL_LIGHT)

降级档由 factsheet (brand_knowledge) 判定, 非硬编码. 本模块从已登记的
brand_knowledge 证据 *推导* 冲突档位, 不向 Phase 0 共享知识模块写入调度侧
专属字段 (保持 brand_knowledge 跨层纯净).

推导规则 (保守, 证据驱动):
- error_quirks 含 series_split / dual_protocol → SEMI_OPEN (混协议)
- 标准 field_mapping(mode_field=operatingMode) + 无协议分裂标志 → COMPLIANT
- 其余 → BLACKBOX (最保守, 退回信号灯 — 平台对所有品牌可控的最低假设)

# 设计决策: 推导而非新增 factsheet 字段 — 避免硬编码品牌档位;
# 升级路径: factsheet 显式声明 conflict_tier 后, 改为读取覆盖推导.
"""
from __future__ import annotations

import logging
from enum import Enum

from core.adapter.brands.brand_knowledge import BrandKnowledge, get_brand_knowledge

# 协议分裂证据键 (混协议 → 半开放)
_PROTOCOL_SPLIT_KEYS = ("series_split", "dual_protocol")
# 标准 VDA5050 mode 字段
_STANDARD_MODE_FIELD = "operatingMode"


class ConflictTier(str, Enum):
    """品牌冲突降级档 (由 factsheet 推导)."""

    COMPLIANT = "COMPLIANT"      # VDA5050 全合规 → 节点预订
    SEMI_OPEN = "SEMI_OPEN"      # 半开放 (混协议) → 车道令牌
    BLACKBOX = "BLACKBOX"        # 黑盒 / 未知 → 信号灯


class ReservationPolicy(str, Enum):
    """降级档对应的资源预约策略."""

    NODE_BOOKING = "NODE_BOOKING"   # 顶点/节点时间窗预订 (MAPFEngine)
    LANE_TOKEN = "LANE_TOKEN"       # 车道令牌 (整段车道互斥)
    SIGNAL_LIGHT = "SIGNAL_LIGHT"   # 路口信号灯 (TrafficLightController)


_TIER_TO_POLICY: dict[ConflictTier, ReservationPolicy] = {
    ConflictTier.COMPLIANT: ReservationPolicy.NODE_BOOKING,
    ConflictTier.SEMI_OPEN: ReservationPolicy.LANE_TOKEN,
    ConflictTier.BLACKBOX: ReservationPolicy.SIGNAL_LIGHT,
}


def infer_conflict_tier(knowledge: BrandKnowledge) -> ConflictTier:
    """从 brand_knowledge 证据推导冲突降级档 (保守)."""
    eq = knowledge.error_quirks
    # 1. 混协议 → 半开放
    if any(k in eq for k in _PROTOCOL_SPLIT_KEYS):
        return ConflictTier.SEMI_OPEN
    # 2. 标准 VDA5050 field_mapping + 无协议分裂 → 合规
    if knowledge.field_mapping.get("mode_field") == _STANDARD_MODE_FIELD:
        return ConflictTier.COMPLIANT
    # 3. 其余 (含 format 未确认 / 自定义 mode 字段) → 黑盒, 最保守
    return ConflictTier.BLACKBOX


class ConflictPolicyResolver:
    """品牌 → 资源预约策略 解析器.

    零配置安全: 未知/黑盒品牌退回 SIGNAL_LIGHT — 平台对所有品牌可控的最低
    假设, 与今日 (无降级档) 行为一致 (信号灯本就常驻).
    """

    @staticmethod
    def tier_for(knowledge: BrandKnowledge) -> ConflictTier:
        return infer_conflict_tier(knowledge)

    @staticmethod
    def tier_for_brand(brand: str) -> ConflictTier:
        return infer_conflict_tier(get_brand_knowledge(brand))

    @staticmethod
    def policy_for(knowledge: BrandKnowledge) -> ReservationPolicy:
        return _TIER_TO_POLICY[infer_conflict_tier(knowledge)]

    @staticmethod
    def policy_for_brand(brand: str) -> ReservationPolicy:
        return _TIER_TO_POLICY[ConflictPolicyResolver.tier_for_brand(brand)]


# ── 自检 (DoD: 3 品牌混合 — 合规/半开放/黑盒 各得正确策略) ──────────
def _demo() -> None:
    expected = {
        "mir": (ConflictTier.COMPLIANT, ReservationPolicy.NODE_BOOKING),
        "otto": (ConflictTier.COMPLIANT, ReservationPolicy.NODE_BOOKING),
        "kuka": (ConflictTier.COMPLIANT, ReservationPolicy.NODE_BOOKING),
        "geekplus": (ConflictTier.SEMI_OPEN, ReservationPolicy.LANE_TOKEN),
        "hairobotics": (ConflictTier.SEMI_OPEN, ReservationPolicy.LANE_TOKEN),
        "quicktron": (ConflictTier.BLACKBOX, ReservationPolicy.SIGNAL_LIGHT),
    }
    for brand, (tier, policy) in expected.items():
        got_tier = ConflictPolicyResolver.tier_for_brand(brand)
        got_policy = ConflictPolicyResolver.policy_for_brand(brand)
        assert got_tier == tier, f"{brand}: tier {got_tier} != {tier}"
        assert got_policy == policy, f"{brand}: policy {got_policy} != {policy}"
    logging.info("OK: 6 brands classified — %d tiers resolved correctly", len(expected))


if __name__ == "__main__":
    _demo()
