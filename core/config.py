"""Centralised, overridable configuration for the v5.0 core.

Values mirror the constants called out in the whitepaper & appendices.
Everything is dataclass-based so it can be serialised to etcd (灰犀牛 #11:
集中配置) and hot-reloaded without redeploy.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SafetyConfig:
    """安全距离双轨制 (白皮书 §2.3, 附录A.1)."""

    k_brake: float = 1.5            # 制动系数
    c_static: float = 0.3           # 静态间距 (m)
    hard_floor: float = 1.5         # 法律硬下限 (GB/T 10827.1-2014), 写入安全PLC
    sensor_degrade_multiplier: float = 1.5  # ERR_SENSOR_DEGRADED → 距离×1.5 (Function Spec §3)
    unsafe_speed_floor: float = 0.2  # v4.0: D_safe 不满足 → 限速 0.2 m/s


@dataclass(frozen=True)
class TrafficConfig:
    """信号灯状态机参数 (白皮书 §2.2)."""

    yellow_duration: float = 3.0    # YELLOW 持续 3s
    max_green: float = 30.0         # 最大绿灯时间
    no_vehicle_wait: float = 2.0    # 无车等待后切灯


@dataclass(frozen=True)
class LivenessConfig:
    """心跳 / 僵尸清理 (灰犀牛 #2, #9, #18)."""

    heartbeat_timeout: float = 3.0     # 心跳超时 3s (主备切换 / Adapter僵尸)
    zombie_hold_seconds: float = 30.0  # 30s 硬超时清理僵尸占位
    offline_to_degraded: float = 3.0   # 失联>3s → DEGRADED
    offline_to_offline: float = 60.0   # 离线>60s → OFFLINE (SOP-YELLOW)
    degraded_max_speed: float = 0.3    # 失联>3s → DEGRADED 限速 0.3 m/s (§2.2)
    boot_takeover_timeout: float = 30.0  # 重启接管协议 30s 超时释放 (灰犀牛 #12)


@dataclass(frozen=True)
class GovernanceConfig:
    """治理层参数 (白皮书 §4 铁律一)."""

    reputation_window: int = 30      # 信誉度取最近30次滚动均值 (Function Spec §5.1)
    reputation_decay: float = 0.95   # 历史衰减
    violation_penalty: float = 0.1   # ERR_TRAFFIC_VIOLATION 信誉扣分
    cost_weight: float = 0.0         # RaaS γ=0 默认关闭, 3个月后调优 (灰犀牛 #14)


@dataclass(frozen=True)
class WormConfig:
    """WORM 黑匣子 (灰犀牛 #5, #10; 陷阱 #12)."""

    rotation_hours: float = 24.0     # 24h/文件 分片滚动
    retention_days: int = 180        # 180天保留
    disk_warn_pct: float = 20.0      # 剩余<20% 告警 (Runbook 图6)
    sink_dir: str = "/data/worm"     # 磁盘持久化目录 (铁律 #9: 审计日志留存≥6个月)


@dataclass(frozen=True)
class ChargerConfig:
    """充电桩预约 (陷阱 #7 电池死亡螺旋)."""

    force_lock_threshold: float = 20.0  # ≤20% 强制锁桩
    reservation_hold_seconds: float = 120.0


@dataclass(frozen=True)
class CoreConfig:
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    traffic: TrafficConfig = field(default_factory=TrafficConfig)
    liveness: LivenessConfig = field(default_factory=LivenessConfig)
    governance: GovernanceConfig = field(default_factory=GovernanceConfig)
    worm: WormConfig = field(default_factory=WormConfig)
    charger: ChargerConfig = field(default_factory=ChargerConfig)
    # 演示模式硬编码 (灰犀牛 #18): PRODUCTION / DEMO, 启动自检
    mode: str = "PRODUCTION"
    # N-1 版本兼容承诺 (灰犀牛 #7)
    supported_versions: tuple[str, ...] = ("5.0", "4.1", "4.0")
