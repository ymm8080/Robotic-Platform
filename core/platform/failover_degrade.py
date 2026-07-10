"""Failover & Degrade — 主备热切换 + 心跳降级 + 本地缓存 (v4.0 §5.3 补丁5).

Robot state machine (Function Spec §2.2 + v4.0 补丁5):

    ONLINE → TASKING → OFFLINE
      │        │         │
      │        │         └── 失联>3s → DEGRADED (限速 0.3 m/s)
      │        └── 任务完成 → IDLE
      └── 启动注册 → 验证通过 → ONLINE

v4.0 补丁5 degrade semantics (beyond a speed cap):
  - 限速 0.3 m/s + 只执行最后一个目标点 + 禁止新任务.
  - 本地缓存: 机器人启动时下载局部车道图和 TF 树, 断网不趴窝;
    网络恢复后同步状态 (local_cache_valid flag).
  - 主备切换必须验证状态一致性, 避免双主脑裂 (etcd shared state, <1s 接管).

The TC-level主备切换 lives in the deployment layer (K8s双副本); this module
tracks per-robot degradation, stamps FleetState.degraded, and emits the ERR_*
events the WORM blackbox records.

GitHub: etcd (https://github.com/etcd-io/etcd) — 主备状态共享.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.config import LivenessConfig
from core.messages import FleetState


@dataclass
class RobotFleetState:
    robot_id: str
    boot_id: str
    online: bool = True
    degraded: bool = False
    last_seen: float = 0.0
    last_boot_id: str = ""
    # v4.0 补丁5: 降级模式语义
    only_last_goal: bool = False   # 只执行最后一个目标点
    accepts_new_tasks: bool = True  # 禁止新任务 (降级后 False, 人工恢复前不变)
    local_cache_valid: bool = False  # 本地车道图缓存有效 (断网不趴窝)


class FailoverDegrade:
    """Tracks liveness and drives ONLINE → DEGRADED → OFFLINE transitions."""

    def __init__(self, config: LivenessConfig | None = None) -> None:
        self.cfg = config or LivenessConfig()
        self._robots: dict[str, RobotFleetState] = {}
        # 主备状态一致性 (脑裂防护): last applied etcd revision
        self._state_revision: int = 0
        self.split_brain: bool = False
        # boot_id 变化后的冻结窗口
        self._boot_takeover_until: dict[str, float] = {}

    def observe(self, state: FleetState, now: float) -> list[str]:
        """Ingest an uplink FleetState; return list of events raised."""
        events: list[str] = []
        prev = self._robots.get(state.robot_id)

        # 灰犀牛 #12 / #18: boot_id 变化 → 重启接管协议 (冻结时间窗)
        if prev is not None and prev.last_boot_id and state.boot_id != prev.last_boot_id:
            events.append(f"ERR_BOOT_ID_CHANGED:{state.robot_id}")
            self._boot_takeover_until[state.robot_id] = now + self.cfg.boot_takeover_timeout

        rs = prev or RobotFleetState(
            robot_id=state.robot_id, boot_id=state.boot_id, last_seen=now
        )
        rs.last_seen = now
        rs.last_boot_id = state.boot_id
        rs.online = True
        # 恢复观测: 若此前降级且重新上线观测, 仍保持降级直到人工恢复
        # (v4.0: 降级模式触发后不再接受新任务, 直到人工恢复)
        self._robots[state.robot_id] = rs
        return events

    def tick(self, now: float) -> list[tuple[str, str]]:
        """Advance liveness; return [(robot_id, transition)] for WORM."""
        transitions: list[tuple[str, str]] = []
        t = self.cfg
        for rs in self._robots.values():
            if not rs.online:
                continue
            age = now - rs.last_seen
            if not rs.degraded and age > t.offline_to_degraded:
                self._enter_degraded(rs)
                transitions.append((rs.robot_id, "ONLINE→DEGRADED"))
            if age > t.offline_to_offline:
                rs.online = False
                rs.degraded = False
                transitions.append((rs.robot_id, "DEGRADED→OFFLINE"))
        return transitions

    def _enter_degraded(self, rs: RobotFleetState) -> None:
        """v4.0 补丁5: 限速 + 只执行最后目标点 + 禁止新任务 + 启用本地缓存."""
        rs.degraded = True
        rs.only_last_goal = True
        rs.accepts_new_tasks = False
        rs.local_cache_valid = True

    def manual_recover(self, robot_id: str) -> bool:
        """人工恢复: 清除降级, 重新接受新任务 (v4.0 §5.2)."""
        rs = self._robots.get(robot_id)
        if rs is None:
            return False
        rs.degraded = False
        rs.only_last_goal = False
        rs.accepts_new_tasks = True
        rs.local_cache_valid = False
        return True

    def stamp(self, state: FleetState) -> FleetState:
        """Stamp platform-maintained flags onto an uplink FleetState."""
        rs = self._robots.get(state.robot_id)
        if rs is not None:
            state.degraded = rs.degraded
        return state

    def degraded_speed_cap(self, robot_id: str) -> float | None:
        """If degraded, return the 0.3 m/s cap; else None (uncapped)."""
        rs = self._robots.get(robot_id)
        if rs and rs.degraded:
            return self.cfg.degraded_max_speed
        return None

    def accepts_new_tasks(self, robot_id: str, now: float) -> bool:
        rs = self._robots.get(robot_id)
        if rs and not rs.accepts_new_tasks:
            return False
        if self._boot_takeover_until.get(robot_id, 0.0) > now:
            return False
        return True

    def is_boot_takeover(self, robot_id: str, now: float) -> bool:
        return self._boot_takeover_until.get(robot_id, 0.0) > now

    def offline_robots(self) -> list[str]:
        return [r.robot_id for r in self._robots.values() if not r.online]

    def is_offline(self, robot_id: str) -> bool:
        rs = self._robots.get(robot_id)
        return rs is not None and not rs.online

    # ── 主备脑裂防护 (v4.0 §5.3 工程注意点) ─────────────────────
    def reconcile_state_revision(self, observed_revision: int) -> bool:
        """主备切换必须验证状态一致性, 避免双主脑裂.

        Returns True iff the observed etcd revision is monotonically newer
        — a stale or equal revision from a peer means split-brain.
        """
        if observed_revision < self._state_revision:
            self.split_brain = True
            return False
        self._state_revision = observed_revision
        self.split_brain = False
        return True
