"""信誉度引擎 — 治理层 (白皮书 §4, Function Spec §5.1).

零信任博弈: 所有参与者默认机会主义者 (灰犀牛 #10 厂商囚徒困境).
信誉度 = 最近 N 次 (默认30) 滚动均值, 历史衰减.
ERR_TRAFFIC_VIOLATION → 降低信誉度 (Function Spec §3); 作弊成本 > 收益.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from core.config import GovernanceConfig


@dataclass
class ReputationEntry:
    timestamp: float
    delta: float  # +good / -bad
    reason: str


class ReputationEngine:
    """Rolling-window reputation with decay."""

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.cfg = config or GovernanceConfig()
        self._history: dict[str, deque[ReputationEntry]] = {}

    def _bucket(self, robot_id: str) -> deque[ReputationEntry]:
        if robot_id not in self._history:
            self._history[robot_id] = deque(maxlen=self.cfg.reputation_window)
        return self._history[robot_id]

    def record_good(self, robot_id: str, now: float, reason: str = "task_completed") -> None:
        self._bucket(robot_id).append(ReputationEntry(now, +1.0, reason))

    def record_violation(
        self, robot_id: str, now: float, reason: str = "traffic_violation"
    ) -> None:
        """闯红灯/超时 → 降低信誉度."""
        self._bucket(robot_id).append(ReputationEntry(now, -self.cfg.violation_penalty, reason))

    def score(self, robot_id: str) -> float:
        """Normalised reputation in [0, 1]. Default 0.5 for unknown robots
        (零信任: 未知参与者不享受信任红利)."""
        entries = self._history.get(robot_id)
        if not entries:
            return 0.5
        decay = self.cfg.reputation_decay
        total = 0.0
        weight = 1.0
        norm = 0.0
        # newest carries most weight (decay applied backwards)
        for e in reversed(entries):
            total += e.delta * weight
            norm += weight
            weight *= decay
        if norm == 0:
            return 0.5
        # clamp to [0,1]; raw delta is ~[-penalty, +1]
        raw = total / norm
        return max(0.0, min(1.0, 0.5 + raw / 2.0))

    def history(self, robot_id: str) -> list[ReputationEntry]:
        return list(self._history.get(robot_id, []))
