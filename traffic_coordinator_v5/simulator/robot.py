"""Per-robot state machine and physics for the VDA5050 simulator."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

from core.messages import RobotMode
from traffic_coordinator_v5.simulator.map import LaneGraph


class SimRobotMode(str, Enum):
    """Simulator-side robot mode names (match ``RobotMode`` enum names)."""

    IDLE = "IDLE"
    TASKING = "TASKING"
    CHARGING = "CHARGING"
    ERROR = "ERROR"


@dataclass
class RobotConfig:
    """Physical constants for one simulated robot."""

    max_speed: float = 1.0              # m/s
    battery_drain_per_metre: float = 0.5  # % per metre while TASKING
    battery_charge_per_second: float = 5.0  # % per second while CHARGING
    charger_threshold: float = 20.0     # % — coordinator force-lock boundary


@dataclass
class SimulatedRobot:
    """One mock VDA5050 robot.

    The robot advances along a sequence of lane ids (the VDA5050 order path),
    drains battery proportionally to distance moved, charges while stopped on
    a charger lane, and reports generic-adapter-compatible state dicts.
    """

    robot_id: str
    brand: str
    lane_graph: LaneGraph
    config: RobotConfig = field(default_factory=RobotConfig)
    current_lane_id: str = ""
    distance_along_lane: float = 0.0
    battery_percent: float = 80.0
    mode: SimRobotMode = SimRobotMode.IDLE
    velocity: float = 0.0
    errors: list[str] = field(default_factory=list)
    sensor_health: dict[str, str] = field(default_factory=lambda: {
        "velocity_sensor": "HEALTHY",
        "lidar": "HEALTHY",
        "camera": "HEALTHY",
        "time_sync": "HEALTHY",
    })
    speed_cap: float = float("inf")
    held: bool = False
    boot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    sequence_number: int = 0
    _path: list[str] = field(default_factory=list, repr=False)
    _path_index: int = 0

    def __post_init__(self) -> None:
        if not self.current_lane_id:
            first = self.lane_graph.first_lane()
            if first is not None:
                self.current_lane_id = first

    @property
    def path(self) -> list[str]:
        """Current locked lane-id path."""
        return list(self._path)

    def assign_order(self, order: dict) -> None:
        """Accept a VDA5050 order and enter TASKING.

        ``order["nodes"]`` is expected to be a list of VDA5050 node dicts
        whose ``nodeId`` values are lane ids (matching the coordinator's
        TaskAssignment.path format).
        """
        nodes = order.get("nodes", []) or []
        lane_ids = [str(n.get("nodeId", n.get("node_id", ""))) for n in nodes]
        lane_ids = [lid for lid in lane_ids if lid]
        if not lane_ids:
            return
        self._path = lane_ids
        self._path_index = 0
        self.current_lane_id = lane_ids[0]
        self.distance_along_lane = 0.0
        self.errors = []
        self.held = False
        if self.mode != SimRobotMode.ERROR:
            self.mode = SimRobotMode.TASKING

    def inject_error(self, error_type: str) -> None:
        """Inject an error and stop the robot."""
        self.errors.append(error_type)
        self.mode = SimRobotMode.ERROR
        self.velocity = 0.0

    def clear_errors(self) -> None:
        """Clear errors and return to IDLE."""
        self.errors.clear()
        if self.mode == SimRobotMode.ERROR:
            self.mode = SimRobotMode.IDLE

    def cancel_order(self) -> None:
        """Cancel the current order and return to IDLE."""
        self._path = []
        self._path_index = 0
        self.mode = SimRobotMode.IDLE

    def hold(self, reason: str = "HOLD") -> None:
        """Pause motion (e.g. red traffic light / coordinator HOLD)."""
        self.held = True

    def resume(self) -> None:
        """Release a hold."""
        self.held = False

    def set_speed_cap(self, max_speed: float) -> None:
        """Apply a coordinator SPEED_CAP."""
        self.speed_cap = max(max_speed, 0.0)

    def clear_speed_cap(self) -> None:
        """Remove a coordinator SPEED_CAP."""
        self.speed_cap = float("inf")

    def tick(self, dt: float) -> list[str]:
        """Advance physics by ``dt`` seconds.

        Returns the list of lane ids whose end nodes were reached during this
        tick (usually zero or one, but may be multiple if ``dt`` is large).
        """
        reached: list[str] = []
        if self.mode == SimRobotMode.ERROR:
            self.velocity = 0.0
            return reached

        if self.mode == SimRobotMode.CHARGING:
            self.velocity = 0.0
            self.battery_percent = min(
                100.0,
                self.battery_percent + self.config.battery_charge_per_second * dt,
            )
            # Remain CHARGING until battery is full; then go IDLE.
            if self.battery_percent >= 99.9:
                self.mode = SimRobotMode.IDLE
            return reached

        if self.mode == SimRobotMode.IDLE or not self._path:
            self.velocity = 0.0
            # Auto-enter charging if idle on a charger lane and battery low.
            if (
                self.mode == SimRobotMode.IDLE
                and self.battery_percent <= self.config.charger_threshold
                and self.current_lane_id in self.lane_graph.charger_lanes()
            ):
                self.mode = SimRobotMode.CHARGING
            return reached

        if self.held:
            self.velocity = 0.0
            return reached

        # TASKING with a path: move along current lane.
        # If battery is critically low during TASKING, transition to ERROR
        # to prevent the robot from dying mid-mission.
        if self.battery_percent <= 0.0:
            self.inject_error("ERR_BATTERY_DEPLETED")
            return reached

        lane = self.lane_graph.lane(self.current_lane_id)
        if lane is None:
            self.velocity = 0.0
            return reached

        max_lane_speed = lane.max_speed if lane.max_speed > 0 else self.config.max_speed
        self.velocity = min(self.config.max_speed, max_lane_speed, self.speed_cap)
        step_distance = self.velocity * dt
        distance_moved = 0.0

        _guard = len(self._path) + 1  # safety: prevent infinite loop on degenerate lanes
        while step_distance > 0.0001 and self._path_index < len(self._path):
            _guard -= 1
            if _guard <= 0:
                break
            lane_id = self._path[self._path_index]
            lane = self.lane_graph.lane(lane_id)
            if lane is None:
                break
            remaining = lane.length - self.distance_along_lane
            if remaining <= 0.0001:
                reached.append(lane_id)
                self._path_index += 1
                self.distance_along_lane = 0.0
                if self._path_index < len(self._path):
                    self.current_lane_id = self._path[self._path_index]
                continue

            if step_distance >= remaining:
                reached.append(lane_id)
                distance_moved += remaining
                step_distance -= remaining
                self._path_index += 1
                self.distance_along_lane = 0.0
                if self._path_index < len(self._path):
                    self.current_lane_id = self._path[self._path_index]
                else:
                    self.current_lane_id = lane_id
            else:
                self.distance_along_lane += step_distance
                distance_moved += step_distance
                step_distance = 0.0

        self.battery_percent = max(
            0.0,
            self.battery_percent - distance_moved * self.config.battery_drain_per_metre,
        )

        if self._path_index >= len(self._path):
            self._finish_path()

        return reached

    def _finish_path(self) -> None:
        """Transition out of TASKING when the path is complete."""
        self._path = []
        self._path_index = 0
        self.velocity = 0.0
        # Rest at the destination node (end of the final lane).
        self.distance_along_lane = self.lane_graph.length(self.current_lane_id)
        # Do not override ERROR mode — a robot that entered an error state
        # during task execution must remain in ERROR until explicitly cleared.
        if self.mode != SimRobotMode.ERROR:
            self.mode = SimRobotMode.IDLE

    def _pose(self) -> tuple[float, float, float]:
        """Return current (x, y, theta) by interpolating along the lane."""
        lane = self.lane_graph.lane(self.current_lane_id)
        if lane is None:
            return (0.0, 0.0, 0.0)
        x0, y0 = self.lane_graph.node_position(lane.from_node)
        x1, y1 = self.lane_graph.node_position(lane.to_node)
        length = max(lane.length, 0.0001)
        ratio = min(1.0, self.distance_along_lane / length)
        x = x0 + (x1 - x0) * ratio
        y = y0 + (y1 - y0) * ratio
        theta = 0.0
        dx = x1 - x0
        dy = y1 - y0
        if abs(dx) > 0.0001 or abs(dy) > 0.0001:
            import math

            theta = math.atan2(dy, dx)
        return (x, y, theta)

    def state_payload(self) -> dict:
        """Return a generic-adapter-compatible VDA5050 state dict."""
        self.sequence_number += 1
        x, y, theta = self._pose()
        lane = self.lane_graph.lane(self.current_lane_id)
        if lane is None:
            last_node = ""
        elif self.distance_along_lane >= lane.length - 0.0001:
            last_node = lane.to_node
        else:
            last_node = lane.from_node
        return {
            "headerId": self.sequence_number,
            "timestamp": self._iso_now(),
            "version": "2.0.0",
            "manufacturer": self.brand,
            "serialNumber": self.robot_id,
            "robotId": self.robot_id,
            "x": round(x, 3),
            "y": round(y, 3),
            "theta": round(theta, 3),
            "lastNodeId": last_node,
            "lane_id": self.current_lane_id,
            "batteryPercent": round(self.battery_percent, 2),
            "mode": self.mode.value,
            "velocity": round(self.velocity, 3),
            "errors": list(self.errors),
            "sensorHealth": dict(self.sensor_health),
            "capability": {
                "payload_kg": 0.0,
                "max_speed": self.config.max_speed,
                "supported_models": ["AMR"],
                "action_primitives": ["MOVE"],
                "supports_reverse": True,
            },
        }

    def connection_payload(self, state: str = "ONLINE") -> dict:
        """Return a VDA5050 connection payload."""
        return {
            "connectionState": state,
            "bootId": self.boot_id,
        }

    @staticmethod
    def _iso_now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
