"""Charger Reservation — 陷阱 #7 (电池死亡螺旋) + 灰犀牛 #14.

电池死亡螺旋补丁: 续航边际成本, ≤20% 强制锁桩.
The robot is forced onto a charger bay when battery ≤ 20% and a bay is
reserved (held) so a draining robot is never queue-blocked by an IDLE one.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.config import ChargerConfig
from core.messages import FleetState, RobotMode


class ChargerState(str, Enum):
    FREE = "FREE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"


@dataclass
class ChargerBay:
    bay_id: str
    state: ChargerState = ChargerState.FREE
    reserved_for: str | None = None
    reserved_at: float = 0.0


class ChargerReservation:
    """Manages charger bay reservation with force-lock at low battery."""

    def __init__(self, config: ChargerConfig | None = None) -> None:
        self.cfg = config or ChargerConfig()
        self._bays: dict[str, ChargerBay] = {}

    def register_bay(self, bay_id: str) -> ChargerBay:
        bay = ChargerBay(bay_id=bay_id)
        self._bays[bay_id] = bay
        return bay

    def free_bay(self) -> ChargerBay | None:
        for b in self._bays.values():
            if b.state is ChargerState.FREE:
                return b
        return None

    def needs_force_lock(self, battery_percent: float) -> bool:
        """≤20% 强制锁桩."""
        return battery_percent <= self.cfg.force_lock_threshold

    def reserve(self, robot_id: str, battery_percent: float, now: float) -> str | None:
        """Reserve a bay for a low-battery robot; returns bay_id or None."""
        if not self.needs_force_lock(battery_percent):
            return None
        # Already reserved?
        for b in self._bays.values():
            if b.reserved_for == robot_id:
                b.reserved_at = now  # refresh hold
                return b.bay_id
        self._expire(now)
        bay = self.free_bay()
        if bay is None:
            return None
        bay.state = ChargerState.RESERVED
        bay.reserved_for = robot_id
        bay.reserved_at = now
        return bay.bay_id

    def _expire(self, now: float) -> list[str]:
        """Release reservations held longer than reservation_hold_seconds."""
        expired: list[str] = []
        for b in self._bays.values():
            if (
                b.state is ChargerState.RESERVED
                and b.reserved_for is not None
                and now - b.reserved_at > self.cfg.reservation_hold_seconds
            ):
                b.state = ChargerState.FREE
                b.reserved_for = None
                expired.append(b.bay_id)
        return expired

    def tick(self, now: float) -> list[str]:
        """Advance reservations; returns expired bay_ids."""
        return self._expire(now)

    def occupy(self, robot_id: str) -> str | None:
        for b in self._bays.values():
            if b.reserved_for == robot_id and b.state is ChargerState.RESERVED:
                b.state = ChargerState.OCCUPIED
                return b.bay_id
        return None

    def release(self, robot_id: str) -> None:
        for b in self._bays.values():
            if b.reserved_for == robot_id:
                b.state = ChargerState.FREE
                b.reserved_for = None

    def should_send_to_charger(self, state: FleetState) -> bool:
        """Decision: force a robot onto a charger."""
        return (
            state.mode is not RobotMode.CHARGING
            and state.battery_percent <= self.cfg.force_lock_threshold
        )
