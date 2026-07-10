"""路口信号灯状态机 (白皮书 §2.2, v4.0 §5.2).

    GREEN → YELLOW → RED → GREEN
       │       │       │
       │       │       └── 另一方向 GREEN
       │       └── 持续 3s (已进入路口的车辆允许通过, 新车辆禁止进入)
       └── 无车等待 或 最大绿灯时间到

紧急任务 (E-Stop / 高优先级) 可强制切灯.
死锁破解 (v4.0 §5.2/§6.2): 检测到死锁时, 强制低优先级机器人硬编码后退 5 米.

This replaces Open-RMF's rmf_traffic negotiation with a deterministic
fixed-cycle controller — the core "降维打击" decision of v5.0 (砍掉
弹性时间窗协商 + 违约预测 + 二次协商).

GitHub: rmf_traffic (https://github.com/open-rmf/rmf_traffic)
        rmf_demos (https://github.com/open-rmf/rmf_demos)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.config import TrafficConfig
from core.messages import SignalColor

DEADLOCK_RETREAT_METRES = 5.0  # v4.0: 强制低优先级机器人后退 5 米


class LightPhase(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class WaitingRobot:
    robot_id: str
    direction: int
    priority: int
    arrived_at: float


@dataclass
class DeadlockBreak:
    """死锁破解指令: 强制低优先级机器人后退 5 米 (硬编码 /cmd_vel)."""

    intersection_id: str
    retreat_robot_id: str
    direction: int
    metres: float = DEADLOCK_RETREAT_METRES


@dataclass
class Intersection:
    """A single路口 with N competing directions.

    For the v5.0 MVP, intersections are 2-direction (fast/slow lane split,
    灰犀牛 #8 木桶效应: 快慢车道物理隔离). Direction 0 holds the green by
    default; direction 1 is RED while 0 is GREEN/YELLOW and vice-versa.
    """

    intersection_id: str
    current_direction: int = 0
    phase: LightPhase = LightPhase.RED
    phase_started_at: float = 0.0
    vehicle_waiting: dict[int, bool] = field(default_factory=lambda: {0: False, 1: False})
    emergency: bool = False
    # v4.0 死锁检测: 每方向等待的机器人 (取最早到达 + 最低优先级)
    waiting_robots: dict[int, WaitingRobot] = field(default_factory=dict)


class TrafficLightController:
    """Drives every Intersection forward in time.

    Tick is driven by a monotonic clock injected from the platform loop
    (no wall-clock dependency → deterministic & testable).
    """

    def __init__(self, config: TrafficConfig | None = None) -> None:
        self.cfg = config or TrafficConfig()
        self._intersections: dict[str, Intersection] = {}

    # ── registration ────────────────────────────────────────────
    def register(self, intersection_id: str) -> Intersection:
        it = Intersection(intersection_id=intersection_id)
        self._intersections[intersection_id] = it
        return it

    def get(self, intersection_id: str) -> Intersection | None:
        return self._intersections.get(intersection_id)

    def all_intersections(self) -> list[Intersection]:
        return list(self._intersections.values())

    # ── demand signalling ───────────────────────────────────────
    def report_waiting(self, intersection_id: str, direction: int, waiting: bool) -> None:
        it = self._intersections.get(intersection_id)
        if it is None:
            return
        it.vehicle_waiting[direction] = waiting

    def report_waiting_robot(
        self, intersection_id: str, robot_id: str, direction: int, priority: int, now: float
    ) -> None:
        """v4.0 死锁检测: 登记等待机器人 (含优先级 + 到达时间)."""
        it = self._intersections.get(intersection_id)
        if it is None:
            return
        it.vehicle_waiting[direction] = True
        existing = it.waiting_robots.get(direction)
        # 保留该方向最早到达的机器人 (死锁后退候选)
        if existing is None or now < existing.arrived_at:
            it.waiting_robots[direction] = WaitingRobot(robot_id, direction, priority, now)

    def clear_waiting(self, intersection_id: str, direction: int) -> None:
        it = self._intersections.get(intersection_id)
        if it is None:
            return
        it.vehicle_waiting[direction] = False
        it.waiting_robots.pop(direction, None)

    # ── entry gate (v4.0 YELLOW 语义) ──────────────────────────
    def may_enter(self, intersection_id: str, direction: int) -> bool:
        """新车辆是否允许进入路口. YELLOW: 已进入的可通过, 新车禁止进入."""
        it = self._intersections.get(intersection_id)
        if it is None:
            return True
        if it.emergency:
            return False
        return it.phase is LightPhase.GREEN and it.current_direction == direction

    # ── 死锁破解 (v4.0 §5.2/§6.2) ──────────────────────────────
    def detect_deadlocks(self, now: float, threshold: float = 15.0) -> list[DeadlockBreak]:
        """双方向均长时间等待 → 强制低优先级机器人后退 5 米.

        threshold: 双方均等待超过该秒数判定为死锁 (默认 15s, 大于最大绿灯时间).
        """
        breaks: list[DeadlockBreak] = []
        for it in self._intersections.values():
            if len(it.waiting_robots) < 2:
                continue
            robots = list(it.waiting_robots.values())
            # 双方向都等了超过 threshold
            if all(now - r.arrived_at >= threshold for r in robots):
                # 低优先级 (priority 数值小) 的后退; 同优先级取最早到达
                loser = min(robots, key=lambda r: (r.priority, -r.arrived_at))
                breaks.append(DeadlockBreak(
                    intersection_id=it.intersection_id,
                    retreat_robot_id=loser.robot_id,
                    direction=loser.direction,
                ))
                # 后退后清出该方向等待, 让另一方向通行
                self.clear_waiting(it.intersection_id, loser.direction)
        return breaks

    # ── emergency (E-Stop / high priority) ─────────────────────
    def force_all_red(self, intersection_id: str) -> None:
        """SOP-RED path: freeze the路口 immediately (铁律二 时空硬边界)."""
        it = self._intersections.get(intersection_id)
        if it is None:
            return
        it.phase = LightPhase.RED
        it.emergency = True

    def clear_emergency(self, intersection_id: str) -> None:
        it = self._intersections.get(intersection_id)
        if it is not None:
            it.emergency = False

    # ── the state machine ───────────────────────────────────────
    def tick(self, now: float) -> list[tuple[str, SignalColor, float]]:
        """Advance all intersections to ``now``; return (id, color, valid_until).

        valid_until is the seconds remaining in the current phase — used to
        populate TrafficLightState.valid_until on the downlink (Function
        Spec §1.2).
        """
        events: list[tuple[str, SignalColor, float]] = []
        for it in self._intersections.values():
            events.append((it.intersection_id, self._tick_one(it, now), self._valid_until(it, now)))
        return events

    def _tick_one(self, it: Intersection, now: float) -> SignalColor:
        if it.emergency:
            it.phase = LightPhase.RED
            return SignalColor.RED

        elapsed = now - it.phase_started_at
        if it.phase is LightPhase.GREEN:
            # 无车等待 (超过 no_vehicle_wait) 或 最大绿灯时间到 → 进入 YELLOW
            stale = not it.vehicle_waiting.get(it.current_direction, False)
            timed_out = elapsed >= self.cfg.max_green
            stale_timed_out = stale and elapsed >= self.cfg.no_vehicle_wait
            if stale_timed_out or timed_out:
                it.phase = LightPhase.YELLOW
                it.phase_started_at = now
        elif it.phase is LightPhase.YELLOW:
            if elapsed >= self.cfg.yellow_duration:
                it.phase = LightPhase.RED
                it.phase_started_at = now
        elif it.phase is LightPhase.RED:
            other = 1 - it.current_direction
            # 全红等待结束 → 切换方向 + GREEN (fixed-cycle)
            if elapsed >= self.cfg.no_vehicle_wait:
                it.current_direction = other
                it.phase = LightPhase.GREEN
                it.phase_started_at = now
        return SignalColor[it.phase.name]

    def _valid_until(self, it: Intersection, now: float) -> float:
        if it.emergency:
            return 0.0
        elapsed = now - it.phase_started_at
        if it.phase is LightPhase.GREEN:
            return max(0.0, self.cfg.max_green - elapsed)
        if it.phase is LightPhase.YELLOW:
            return max(0.0, self.cfg.yellow_duration - elapsed)
        # RED: time until we *could* switch, or 0 if no demand
        return max(0.0, self.cfg.no_vehicle_wait - elapsed)
