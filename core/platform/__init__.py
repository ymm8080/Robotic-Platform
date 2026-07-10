"""平台服务层 (精简 + 生存)."""
from __future__ import annotations

from core.platform.charger_reservation import (
    ChargerReservation,
    ChargerState,
)
from core.platform.failover_degrade import FailoverDegrade, RobotFleetState
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.platform.lift_manager import LiftManager, LiftState
from core.platform.robot_as_obstacle import RobotAsObstacle

__all__ = [
    "ChargerReservation",
    "ChargerState",
    "FailoverDegrade",
    "FixedLaneMap",
    "Lane",
    "LiftManager",
    "LiftState",
    "RobotAsObstacle",
    "RobotFleetState",
]
