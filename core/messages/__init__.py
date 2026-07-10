"""Interface message types — v5.0 Function Spec §1.

These are the protobuf-equivalent contracts crossing the Adapter↔Platform
boundary. Kept as plain dataclasses (no protobuf dependency) so the core
remains import-light and testable in isolation; a .proto can be generated
from these when the DDS transport layer lands.
"""
from __future__ import annotations

from core.messages.types import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    HealthStatus,
    Pose,
    RobotMode,
    SensorHealth,
    SignalColor,
    TaskAssignment,
    TrafficLightState,
    Versioned,
)

__all__ = [
    "ActionPrimitive",
    "CapabilityVector",
    "EnvConstraints",
    "FleetState",
    "HealthStatus",
    "Pose",
    "RobotMode",
    "SensorHealth",
    "SignalColor",
    "TaskAssignment",
    "TrafficLightState",
    "Versioned",
]
