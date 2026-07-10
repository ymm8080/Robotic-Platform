"""经济模型 (RaaS) — 治理层 (Function Spec §5.1, 灰犀牛 #14).

预留 cost_weight 接口 (γ=0 默认关闭, 3个月后调优).
作弊成本 > 收益 (灰犀牛 #10): reputation slippage raises marginal cost,
so a cheating fleet operator pays more per km over time.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.config import GovernanceConfig
from core.governance.reputation_engine import ReputationEngine


@dataclass
class RobotCostProfile:
    """Per-robot marginal cost (RaaS). Until γ is enabled this returns 0."""

    robot_id: str
    base_cost_per_km: float = 0.0
    battery_wear: float = 0.0   # wear cost per km scaled by battery age


class EconomicModel:
    """RaaS utility — the γ term in TaskAllocator.utility."""

    def __init__(
        self,
        reputation: ReputationEngine,
        config: GovernanceConfig | None = None,
    ) -> None:
        self.reputation = reputation
        self.cfg = config or GovernanceConfig()
        self._profiles: dict[str, RobotCostProfile] = {}

    def register(self, profile: RobotCostProfile) -> None:
        self._profiles[profile.robot_id] = profile

    def marginal_cost_per_km(self, robot_id: str) -> float:
        """作弊成本 > 收益: low reputation inflates effective cost.

        Returns 0.0 while γ (cost_weight) is disabled — the interface is
        reserved so the allocator can be switched on without code change.
        The returned cost is *before* γ scaling; the TaskAllocator multiplies
        by its own cost_weight so the penalty knob stays in one place.
        """
        if self.cfg.cost_weight == 0.0:
            return 0.0
        profile = self._profiles.get(robot_id)
        base = profile.base_cost_per_km if profile else 0.0
        # reputation in [0,1]; cost multiplier grows as reputation drops
        rep = self.reputation.score(robot_id)
        return base * (1.0 + (1.0 - rep))

    def cost_for(self, robot_id: str, distance_m: float) -> float:
        """Total marginal cost for a concrete distance."""
        return self.marginal_cost_per_km(robot_id) * (distance_m / 1000.0)

    def enabled(self) -> bool:
        return self.cfg.cost_weight > 0.0
