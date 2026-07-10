"""v5.0 wire types (Function Spec §1.1 / §1.2).

Field numbers are preserved as comments so a future .proto mirrors them
exactly. ``version`` is mandatory on every message (灰犀牛 #7: Version
Gateway, N-1 兼容).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RobotMode(IntEnum):
    """FleetState.mode (Function Spec §1.1)."""

    IDLE = 0
    CHARGING = 1
    TASKING = 2
    ERROR = 3


class HealthStatus(IntEnum):
    """SensorHealth sub-status (Function Spec §1.1)."""

    HEALTHY = 0
    DEGRADED = 1
    CRITICAL = 2


class SignalColor(IntEnum):
    """TrafficLightState.color (Function Spec §1.2)."""

    GREEN = 0
    YELLOW = 1
    RED = 2


class ActionPrimitive(IntEnum):
    """动作原语 (v4.0 补丁3). 任务描述必须包含动作原语, 不支持则调度层直接过滤."""

    MOVE = 0          # 车道行驶
    PICK = 1
    PLACE = 2
    DOCK = 3          # 对接 (e.g. DockingType2)
    CHARGE = 4
    LIFT_FORK = 5     # 顶升


@dataclass
class EnvConstraints:
    """环境适应性 (v4.0 补丁3): 爬坡度 / 门槛高度 / 地面平整度.

    Stored as edge attributes on the lane graph AND in the robot capability
    vector so the allocator can filter before dispatching.
    """

    max_grade: float = 0.0       # 最大爬坡度 (rad), 0=平地
    floor_threshold: float = 0.0  # 门槛高度 (m), 0=无门槛
    min_friction: float = 0.0    # 最低摩擦系数 (附录: 干燥>0.4)


@dataclass
class CapabilityVector:
    """机器人能力向量 (v4.0 §5.2 Task Scheduler).

    载重 / 速度 / 支持车道型号 / 支持动作原语 / 环境适应性.
    The allocator filters on this BEFORE utility scoring — "载重50kg" 不代表
    能过 3 号区门槛 (补丁3 语义鸿沟).
    """

    payload_kg: float = 0.0
    max_speed: float = 1.5
    supported_models: list[str] = field(default_factory=list)
    action_primitives: set[ActionPrimitive] = field(default_factory=set)
    env: EnvConstraints = field(default_factory=EnvConstraints)
    supports_reverse: bool = False   # SCS 是否允许负速度 (Adapter 硬编码后退前提)

    def supports(self, primitives: set[ActionPrimitive]) -> bool:
        return primitives.issubset(self.action_primitives)

    def can_traverse(self, env: EnvConstraints) -> bool:
        """Can this robot traverse an edge with the given env constraints?

        Robot env = what it CAN handle (max grade it can climb, max threshold
        it can cross). Edge env = what it REQUIRES. Friction is a ground
        property recorded for audit (附录: 干燥>0.4), not a robot limit.
        """
        return (
            self.env.max_grade >= env.max_grade
            and self.env.floor_threshold >= env.floor_threshold
        )


@dataclass
class Pose:
    """公共坐标系下的位姿."""

    x: float
    y: float
    theta: float = 0.0
    last_node_id: str = ""
    position_initialized: bool = True


@dataclass
class SensorHealth:
    """传感器健康度 (用于安全距离放大 / 降级决策)."""

    velocity_sensor: HealthStatus = HealthStatus.HEALTHY  # =1
    lidar: HealthStatus = HealthStatus.HEALTHY            # =2
    camera: HealthStatus = HealthStatus.HEALTHY           # =3
    time_sync: HealthStatus = HealthStatus.HEALTHY        # =4  NTP/PTP

    @property
    def worst(self) -> HealthStatus:
        return max(
            self.velocity_sensor, self.lidar, self.camera, self.time_sync
        )

    @property
    def degraded(self) -> bool:
        return self.worst >= HealthStatus.DEGRADED


class Versioned:
    """Mixin: every crossing-boundary message carries a version field."""

    version: str = "5.0"


@dataclass
class FleetState(Versioned):
    """Adapter → Platform (上行). Function Spec §1.1."""

    robot_id: str                       # =1
    boot_id: str                        # =2  每次重启生成的UUID
    pose: Pose                          # =3
    battery_percent: float              # =4
    mode: RobotMode = RobotMode.IDLE    # =5
    errors: list[str] = field(default_factory=list)  # =6
    sensor_health: SensorHealth = field(default_factory=SensorHealth)  # =7
    velocity: float = 0.0               # =8  当前线速度 (安全公式入参)
    # 平台侧维护, 非上行字段:
    last_seen_monotonic: float = 0.0
    capability: CapabilityVector = field(default_factory=CapabilityVector)
    degraded: bool = False   # v4.0 §5.2: 降级模式不再接受新任务, 由 FailoverDegrade 盖戳

    @property
    def offline(self) -> bool:
        return self.mode == RobotMode.ERROR and bool(self.errors)


@dataclass
class TrafficLightState(Versioned):
    """TaskAssignment.traffic_state. Function Spec §1.2."""

    intersection_id: str                # =1
    color: SignalColor = SignalColor.RED  # =2
    valid_until: float = 0.0            # =3  信号灯状态有效期 (秒)


@dataclass
class TaskAssignment(Versioned):
    """Platform → Adapter (下行). Function Spec §1.2."""

    task_id: str                        # =1
    path: list[str] = field(default_factory=list)  # =2  车道序列 (lane ids)
    max_speed: float = 1.5              # =3  平台计算的最大限速
    traffic_state: TrafficLightState | None = None  # =4
