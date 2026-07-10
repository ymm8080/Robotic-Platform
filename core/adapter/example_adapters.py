"""Example per-brand adapter subclasses.

These demonstrate how to map a vendor-native state dict into the unified
``FleetState`` and how to translate unified goals back to native commands.
They are *templates*, not production adapters.
"""
from __future__ import annotations

from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.map_transformer import MapTransformer
from core.messages import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    HealthStatus,
    Pose,
    RobotMode,
    SensorHealth,
)


class MiRFleetAdapter(FleetAdapter):
    """MiR-style adapter: REST API state in MiR coordinate frame."""

    def __init__(self) -> None:
        # MiR fleet already uses the facility frame in this example
        transformer = MapTransformer.identity("MiR")
        super().__init__(brand="MiR", transformer=transformer)

    def map_vendor_state(self, raw: dict) -> FleetState:
        pose = self.transformer.transform_pose(
            raw.get("x", 0.0), raw.get("y", 0.0), raw.get("theta", 0.0)
        )
        pose.last_node_id = raw.get("current_node", "")
        return FleetState(
            robot_id=raw["robotId"],
            boot_id=raw.get("bootId", ""),
            pose=pose,
            battery_percent=raw.get("battery_percent", 0.0),
            mode=RobotMode[raw.get("mode", "IDLE")],
            errors=self.map_vendor_errors(raw.get("errors", [])),
            velocity=raw.get("velocity", 0.0),
            capability=CapabilityVector(
                payload_kg=raw.get("payload_kg", 100.0),
                max_speed=raw.get("max_speed", 1.5),
                supported_models=["MiR"],
                action_primitives={ActionPrimitive.MOVE, ActionPrimitive.DOCK},
                env=EnvConstraints(max_grade=0.1, floor_threshold=0.02),
                supports_reverse=True,
            ),
            sensor_health=SensorHealth(
                lidar=HealthStatus[raw.get("lidar_status", "HEALTHY")],
            ),
        )

    def map_vendor_errors(self, raw_errors: list) -> list[str]:
        mapping = {
            "mir_error_1": "ERR_SCS_TIMEOUT",
            "mir_error_2": "ERR_TRAFFIC_VIOLATION",
        }
        return [mapping.get(e, f"ERR_VENDOR:{e}") for e in raw_errors]


class OTTOFleetAdapter(FleetAdapter):
    """OTTO-style adapter: state uses a shifted/rotated coordinate frame."""

    def __init__(self) -> None:
        # example: OTTO origin is shifted +10m in x and rotated 90°
        def native_to_unified_pose(x: float, y: float, theta: float) -> Pose:
            return Pose(x=x + 10.0, y=y, theta=theta + 1.5708)

        def unified_to_native_goal(lane_id: str) -> dict:
            return {"goal": lane_id, "frame": "otto"}

        def native_to_unified_lane(native: str) -> str | None:
            return native.replace("OTTO_", "")

        transformer = MapTransformer(
            brand="OTTO",
            native_to_unified_pose=native_to_unified_pose,
            unified_to_native_goal=unified_to_native_goal,
            native_to_unified_lane=native_to_unified_lane,
        )
        super().__init__(brand="OTTO", transformer=transformer)

    def map_vendor_state(self, raw: dict) -> FleetState:
        pose = self.transformer.transform_pose(
            raw.get("x", 0.0), raw.get("y", 0.0), raw.get("theta", 0.0)
        )
        native_lane = raw.get("current_node", "")
        unified_lane = self.transformer.transform_lane(native_lane)
        pose.last_node_id = unified_lane or native_lane
        return FleetState(
            robot_id=raw["robotId"],
            boot_id=raw.get("bootId", ""),
            pose=pose,
            battery_percent=raw.get("battery_percent", 0.0),
            mode=RobotMode[raw.get("mode", "IDLE")],
            errors=self.map_vendor_errors(raw.get("errors", [])),
            velocity=raw.get("velocity", 0.0),
            capability=CapabilityVector(
                payload_kg=raw.get("payload_kg", 150.0),
                max_speed=raw.get("max_speed", 1.2),
                supported_models=["OTTO"],
                action_primitives={ActionPrimitive.MOVE},
                env=EnvConstraints(max_grade=0.05, floor_threshold=0.01),
                supports_reverse=False,
            ),
        )

    def map_vendor_errors(self, raw_errors: list) -> list[str]:
        mapping = {
            "otto_error_1": "ERR_SENSOR_DEGRADED",
        }
        return [mapping.get(e, f"ERR_VENDOR:{e}") for e in raw_errors]
