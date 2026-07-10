"""Facility Manager — zone / shared-resource lifecycle.

Open-RMF's rmf_fleet_adapter exposes a ``FacilityManager`` for shared
resources (doors, lifts, cleaners). v5.0 keeps the concept but folds in
the platform-service resources (charger bays, lifts, zones) and owns the
SOP-RED Zone Lockdown (Runbook §1) + 僵尸占位清理 (陷阱 #2: 30s 硬超时).

This module is the *registry*; the resource-specific policies live in
``core.platform`` (charger_reservation, lift_manager, failover_degrade).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ZoneState(str, Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"          # SOP-RED Zone Lockdown
    DEGRADED = "DEGRADED"      # SOP-YELLOW


@dataclass
class Zone:
    zone_id: str
    state: ZoneState = ZoneState.OPEN
    locked_at: float = 0.0
    robots: set[str] = field(default_factory=set)
    # 僵尸占位清理 (陷阱 #2): 占位时间戳
    occupancy_since: dict[str, float] = field(default_factory=dict)


class FacilityManager:
    """Tracks zones and enforces facility-wide safety states."""

    def __init__(self) -> None:
        self._zones: dict[str, Zone] = {}

    def register_zone(self, zone_id: str) -> Zone:
        z = Zone(zone_id=zone_id)
        self._zones[zone_id] = z
        return z

    def get_zone(self, zone_id: str) -> Zone | None:
        return self._zones.get(zone_id)

    # ── SOP-RED ────────────────────────────────────────────────
    def lockdown(self, zone_id: str, now: float) -> bool:
        """Zone Lockdown — freezes a zone; robots get Level-0 E-Stop."""
        z = self._zones.get(zone_id)
        if z is None:
            return False
        z.state = ZoneState.LOCKED
        z.locked_at = now
        return True

    def release(self, zone_id: str) -> bool:
        z = self._zones.get(zone_id)
        if z is None:
            return False
        z.state = ZoneState.OPEN
        return True

    def locked_zones(self) -> list[str]:
        return [z.zone_id for z in self._zones.values() if z.state is ZoneState.LOCKED]

    # ── occupancy / 僵尸清理 (陷阱 #2) ─────────────────────────
    def occupy(self, zone_id: str, robot_id: str, now: float) -> None:
        z = self._zones.get(zone_id)
        if z is None:
            z = self.register_zone(zone_id)
        z.robots.add(robot_id)
        z.occupancy_since.setdefault(robot_id, now)

    def vacate(self, zone_id: str, robot_id: str) -> None:
        z = self._zones.get(zone_id)
        if z is None:
            return
        z.robots.discard(robot_id)
        z.occupancy_since.pop(robot_id, None)

    def reap_zombies(self, now: float, hold_seconds: float = 30.0) -> list[tuple[str, str]]:
        """30s 硬超时清理僵尸占位 + 广播释放 (陷阱 #2)."""
        reaped: list[tuple[str, str]] = []
        for z in self._zones.values():
            for rid, since in list(z.occupancy_since.items()):
                if now - since >= hold_seconds:
                    z.robots.discard(rid)
                    z.occupancy_since.pop(rid, None)
                    reaped.append((z.zone_id, rid))
        return reaped
