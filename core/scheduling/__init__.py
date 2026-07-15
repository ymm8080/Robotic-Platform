"""核心调度层 (Open-RMF — 信号灯).

Task Allocator · Traffic Light Controller · Facility Manager.

Concepts follow Open-RMF (https://github.com/open-rmf/rmf) — specifically
rmf_traffic (negotiation/participants) and rmf_task (task allocation) —
but are stripped down to the v5.0 "固定车道 + 路口信号灯" strategy:
no dynamic replanning, no trajectory extrapolation, no elastic time-window
renegotiation (白皮书 §2.1 降维打击).
"""

from __future__ import annotations

from core.scheduling.facility_manager import FacilityManager, ZoneState
from core.scheduling.task_allocator import AllocationResult, Task, TaskAllocator
from core.scheduling.traffic_light_controller import (
    DeadlockBreak,
    Intersection,
    TrafficLightController,
)

__all__ = [
    "AllocationResult",
    "DeadlockBreak",
    "FacilityManager",
    "Intersection",
    "Task",
    "TaskAllocator",
    "TrafficLightController",
    "ZoneState",
]
