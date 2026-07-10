"""Lift Manager — 电梯预约 (平台服务层).

Open-RMF's rmf_fleet_adapter handles lifts via the Door/Lift resource
negotiation. v5.0 simplifies to a single-occupancy reservation with a
timeout (灰犀牛 #2 僵尸占位 applies: 30s hold → release).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LiftState(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    OCCUPIED = "OCCUPIED"


@dataclass
class Lift:
    lift_id: str
    state: LiftState = LiftState.IDLE
    floor: int = 0
    current_user: str | None = None
    requested_floor: int | None = None
    occupied_since: float = 0.0


class LiftManager:
    """Single-occupancy lift scheduler with timeout-based release."""

    HOLD_TIMEOUT = 30.0  # 陷阱 #2: 30s 硬超时

    def __init__(self) -> None:
        self._lifts: dict[str, Lift] = {}

    def register(self, lift_id: str) -> Lift:
        lift = Lift(lift_id=lift_id)
        self._lifts[lift_id] = lift
        return lift

    def request(self, lift_id: str, robot_id: str, target_floor: int, now: float) -> bool:
        lift = self._lifts.get(lift_id)
        if lift is None:
            return False
        if lift.state is not LiftState.IDLE:
            return False
        lift.current_user = robot_id
        lift.requested_floor = target_floor
        lift.state = LiftState.MOVING
        lift.occupied_since = now
        return True

    def tick(self, now: float) -> list[tuple[str, str]]:
        """Advance lifts; release on timeout or arrival. Returns [(lift, robot)]."""
        released: list[tuple[str, str]] = []
        for lift in self._lifts.values():
            if lift.state is LiftState.MOVING:
                lift.floor = lift.requested_floor or lift.floor
                lift.state = LiftState.OCCUPIED
            elif lift.state is LiftState.OCCUPIED:
                if now - lift.occupied_since >= self.HOLD_TIMEOUT:
                    released.append((lift.lift_id, lift.current_user or ""))
                    self._reset(lift)
        return released

    def release(self, lift_id: str, robot_id: str) -> bool:
        lift = self._lifts.get(lift_id)
        if lift is None or lift.current_user != robot_id:
            return False
        self._reset(lift)
        return True

    def current_user(self, lift_id: str) -> str | None:
        lift = self._lifts.get(lift_id)
        return lift.current_user if lift is not None else None

    @staticmethod
    def _reset(lift: Lift) -> None:
        lift.state = LiftState.IDLE
        lift.current_user = None
        lift.requested_floor = None
        lift.occupied_since = 0.0
