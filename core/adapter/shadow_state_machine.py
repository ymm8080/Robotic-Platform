"""Shadow State Machine + 超时熔断 (白皮书适配层, v4.0 补丁4).

影子状态机是底线: the platform keeps an independent expectation of each
robot's state. Discrepancies between expected (shadow) and reported (SCS)
state surface as ShadowMismatch → recorded to WORM (Function Spec §3
ERR_SCS_TIMEOUT: 上报影子状态机差异).

v4.0 补丁4 违约熔断: 下发指令 5s 内行为未预期变化 → 判定失联/异常 →
触发全 Fleet 安全接管. This is a *behavior-deadline* breaker, distinct
from the SCS-ack failure-count breaker (灰犀牛 #9 心跳超时3次). Both can
trip the circuit; once OPEN the adapter falls back to hardcoded retreat.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from core.messages import FleetState, RobotMode


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # normal
    OPEN = "OPEN"          # tripped — calls fail fast, fallback engaged
    HALF_OPEN = "HALF_OPEN"  # probing recovery


@dataclass
class ShadowMismatch:
    robot_id: str
    expected: str
    actual: str
    timestamp: float


@dataclass
class BehaviorExpectation:
    """v4.0 补丁4: 下发指令后期望的行为 + 5s 截止时间."""

    robot_id: str
    expected_mode: RobotMode
    deadline: float       # monotonic seconds by which the behavior must be seen


class ShadowStateMachine:
    """Per-robot expected-state tracker + circuit breaker."""

    BREAKER_THRESHOLD = 3     # 心跳超时3次 → 自动重启/熔断 (灰犀牛 #9)
    BREAKER_COOLDOWN = 30.0   # s before HALF_OPEN probe
    BEHAVIOR_DEADLINE = 5.0   # v4.0 补丁4: 5s 内行为未预期变化 → 熔断

    def __init__(self) -> None:
        # robot_id → expected mode (state-level shadow)
        self._shadow: dict[str, RobotMode] = {}
        # robot_id → behavior expectation with deadline (v4.0 补丁4)
        self._behavior: dict[str, BehaviorExpectation] = {}
        self._scs_failures: dict[str, int] = {}
        self._breaker: dict[str, CircuitState] = {}
        self._tripped_at: dict[str, float] = {}
        self.mismatches: deque[ShadowMismatch] = deque(maxlen=1000)
        self.behavior_timeouts: deque[str] = deque(maxlen=1000)  # robot_ids that tripped on 5s deadline

    # ── shadow ─────────────────────────────────────────────────
    def expect(self, robot_id: str, mode: RobotMode) -> None:
        self._shadow[robot_id] = mode

    def expect_behavior(self, robot_id: str, expected_mode: RobotMode, now: float) -> None:
        """v4.0 补丁4: 下发指令后期望 5s 内看到 expected_mode."""
        self._shadow[robot_id] = expected_mode
        self._behavior[robot_id] = BehaviorExpectation(
            robot_id=robot_id,
            expected_mode=expected_mode,
            deadline=now + self.BEHAVIOR_DEADLINE,
        )

    def reconcile(self, state: FleetState, now: float) -> ShadowMismatch | None:
        """Compare reported SCS state to the shadow expectation."""
        expected = self._shadow.get(state.robot_id)
        if expected is not None and state.mode != expected:
            mm = ShadowMismatch(
                robot_id=state.robot_id,
                expected=expected.name,
                actual=state.mode.name,
                timestamp=now,
            )
            self.mismatches.append(mm)
            return mm
        # match → clear shadow expectation, reset failure window + behavior deadline
        self._shadow.pop(state.robot_id, None)
        self._behavior.pop(state.robot_id, None)
        return None

    # ── circuit breaker ────────────────────────────────────────
    def record_scs_timeout(self, robot_id: str, now: float) -> CircuitState:
        """ERR_SCS_TIMEOUT: 重试1次, 仍失败→标记DEGRADED."""
        self._scs_failures[robot_id] = self._scs_failures.get(robot_id, 0) + 1
        if self._scs_failures[robot_id] >= self.BREAKER_THRESHOLD:
            self._trip(robot_id, now)
        return self._breaker.get(robot_id, CircuitState.CLOSED)

    def record_success(self, robot_id: str) -> None:
        self._scs_failures[robot_id] = 0
        self._breaker[robot_id] = CircuitState.CLOSED
        self._tripped_at.pop(robot_id, None)

    def _trip(self, robot_id: str, now: float) -> None:
        self._breaker[robot_id] = CircuitState.OPEN
        self._tripped_at[robot_id] = now

    def breaker_state(self, robot_id: str) -> CircuitState:
        return self._breaker.get(robot_id, CircuitState.CLOSED)

    def tick(self, now: float) -> list[str]:
        """Move OPEN → HALF_OPEN after cooldown; trip behavior-deadline timeouts.

        v4.0 补丁4: any behavior expectation past its 5s deadline that has
        not been reconciled → trip the breaker + engage fallback.
        Returns recovered (HALF_OPEN) robot_ids.
        """
        # behavior-deadline enforcement
        for rid, be in list(self._behavior.items()):
            if now >= be.deadline and self.breaker_state(rid) is CircuitState.CLOSED:
                self._trip(rid, now)
                self.behavior_timeouts.append(rid)
                self._behavior.pop(rid, None)

        recovered: list[str] = []
        for rid, st in list(self._breaker.items()):
            if st is CircuitState.OPEN:
                if now - self._tripped_at.get(rid, 0) >= self.BREAKER_COOLDOWN:
                    self._breaker[rid] = CircuitState.HALF_OPEN
                    recovered.append(rid)
        return recovered

    def should_fallback(self, robot_id: str) -> bool:
        """硬编码后退: when breaker is OPEN, engage hardcoded retreat."""
        return self.breaker_state(robot_id) is CircuitState.OPEN
