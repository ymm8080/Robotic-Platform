"""Dynamic safe-distance formula with a legal hard floor.

白皮书 §2.3:
    动态公式:  S = V_curr · K_brake + RTT · V_curr + C_static
    硬下限:    S_min >= 1.5 m  (GB/T 10827.1-2014), 写入安全 PLC,
               任何软件层无权覆盖.

铁律二 (物理层 — 熵增冗余): 逻辑追求最优, 物理为最坏买单.
The hard floor is therefore *max(dynamic, floor)* and the floor can never
be lowered by software — it is read from a frozen config that mirrors the
safety PLC register.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import SafetyConfig
from core.messages import HealthStatus, SensorHealth
from core.safety.safety_plc import SafetyPlc


@dataclass
class SafeDistanceResult:
    dynamic: float  # 公式计算值
    floor: float  # 法律硬下限
    applied: float  # 实际采用 = max(dynamic, floor)
    sensor_penalty: bool  # 是否因传感器降级而放大


class SafeDistanceCalculator:
    """Stateless calculator bound to an immutable SafetyConfig."""

    def __init__(
        self,
        config: SafetyConfig | None = None,
        plc: SafetyPlc | None = None,
    ) -> None:
        self.cfg = config or SafetyConfig()
        # 安全 PLC 权威硬下限寄存器 (Phase 4 task 5). 默认 1.5m 法定;
        # 软件可通过 config 申请抬高, 但 plc.enforce 永不让其低于法定值.
        self.plc = plc or SafetyPlc()

    def compute(
        self,
        velocity: float,
        rtt: float,
        sensor_health: SensorHealth | None = None,
    ) -> SafeDistanceResult:
        """Return the safe following distance for one robot.

        Args:
            velocity: current linear speed (m/s).
            rtt: platform→adapter ACK round-trip (s).
            sensor_health: if any sensor DEGRADED, distance is amplified
                (Function Spec §3 ERR_SENSOR_DEGRADED → +50%).
        """
        cfg = self.cfg
        dynamic = velocity * cfg.k_brake + rtt * velocity + cfg.c_static

        penalty = False
        if sensor_health is not None and sensor_health.degraded:
            dynamic *= cfg.sensor_degrade_multiplier
            penalty = True

        # 硬下限: 软件无权覆盖. 经安全 PLC enforce — 软件可抬高, 不可降低
        # 于法定寄存器值. 取 max(dynamic, plc_floor).
        floor = self.plc.enforce(cfg.hard_floor)
        applied = max(dynamic, floor)
        return SafeDistanceResult(
            dynamic=dynamic,
            floor=floor,
            applied=applied,
            sensor_penalty=penalty,
        )

    def speed_cap_for_gap(
        self,
        velocity: float,
        rtt: float,
        available_gap: float,
        sensor_health: SensorHealth | None = None,
    ) -> float:
        """v4.0 §5.2/§6.2: D_safe 不满足 → 限速 0.2 m/s.

        The platform computes D_safe; if the actual available gap to the
        obstacle ahead is less than D_safe, the robot must be capped to the
        unsafe-floor speed (0.2 m/s) — distinct from the 0.3 m/s lost-comm
        degrade cap. Returns the (possibly reduced) commanded speed.
        """
        required = self.compute(velocity, rtt, sensor_health).applied
        if available_gap < required:
            return self.cfg.unsafe_speed_floor
        return velocity


def compute_safe_distance(
    velocity: float,
    rtt: float,
    sensor_health: SensorHealth | None = None,
    config: SafetyConfig | None = None,
) -> float:
    """Convenience: return just the applied distance."""
    return SafeDistanceCalculator(config).compute(velocity, rtt, sensor_health).applied


# Sanity guard imported for type-checkers that walk this module.
_ = HealthStatus  # noqa: F841  (kept to document the HealthStatus coupling)
