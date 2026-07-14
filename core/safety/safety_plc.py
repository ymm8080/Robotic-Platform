"""安全 PLC 接口 — 法律硬下限的权威寄存器 (v7 Phase 4 task 5).

白皮书 §2.3 / 铁律二 (物理层为最坏买单): 硬下限 S_min ≥ 1.5 m
(GB/T 10827.1-2014) 写入安全 PLC, 任何软件层无权覆盖.

此前 ``SafetyConfig.hard_floor`` 是一个 *声称* 镜像 PLC 寄存器的冻结配置值,
但并无真实 PLC 强制它 — 软件若误改配置即可静默 lowering. 本模块补上"落 PLC
接口"的缺口: ``SafetyPlc`` 代表安全 PLC 的权威寄存器, 软件只能 *抬高* 申请
下限, 永不能低于寄存器法定值.

# ponytail: 不引入真实 PLC 驱动 (硬件未定) — 仅建模其权威寄存器语义.
# 升级路径: 接真实安全 PLC (Modbus/EtherCAT) 读寄存器值, enforce() 不变.
"""
from __future__ import annotations

from dataclasses import dataclass

LEGAL_HARD_FLOOR_M = 1.5  # GB/T 10827.1-2014 法定硬下限
_DEMO_HARD_FLOOR_M = 0.5  # DEMO 模式寄存器 (销售演示, 显式降级)


@dataclass(frozen=True)
class PlcFloorViolation:
    """软件尝试 lowering 寄存器法定值的审计记录."""

    requested: float
    legal_floor: float
    enforced: float


class SafetyPlc:
    """安全 PLC 权威硬下限寄存器.

    软件只读寄存器值; ``enforce`` 把软件申请的下限钳到 ≥ 寄存器法定值.
    任何 lowering 尝试被拒绝并记录 (不抛异常 — 安全路径不得因审计而中断).
    """

    def __init__(self, hard_floor: float = LEGAL_HARD_FLOOR_M) -> None:
        if hard_floor < 0:
            raise ValueError("safety PLC hard floor must be non-negative")
        self._hard_floor = hard_floor
        self._violations: list[PlcFloorViolation] = []

    @property
    def hard_floor(self) -> float:
        """寄存器法定硬下限 (软件不可 lowering)."""
        return self._hard_floor

    @classmethod
    def for_demo(cls) -> SafetyPlc:
        """DEMO 模式寄存器 (0.5m, 显式降级 — 仅销售演示)."""
        return cls(_DEMO_HARD_FLOOR_M)

    def enforce(self, requested_floor: float) -> float:
        """钳制软件申请的下限到 ≥ 寄存器法定值.

        软件可抬高 (返回 requested), 不可 lowering (返回法定值并记审计).
        """
        if requested_floor < self._hard_floor:
            self._violations.append(
                PlcFloorViolation(
                    requested=requested_floor,
                    legal_floor=self._hard_floor,
                    enforced=self._hard_floor,
                )
            )
            return self._hard_floor
        return requested_floor

    def violations(self) -> list[PlcFloorViolation]:
        """返回至今被拒绝的 lowering 尝试 (审计 / 合规取证)."""
        return list(self._violations)


# ── 自检 (DoD: 软件无法 lowering PLC 法定下限) ───────────────────
def _demo() -> None:
    plc = SafetyPlc()  # 默认 1.5m 法定
    assert plc.hard_floor == 1.5
    # 抬高允许
    assert plc.enforce(2.0) == 2.0
    # lowering 被拒, 钳回法定值
    assert plc.enforce(0.5) == 1.5
    assert plc.enforce(0.0) == 1.5
    assert len(plc.violations()) == 2, "two lowering attempts recorded"
    # DEMO 寄存器显式降级
    assert SafetyPlc.for_demo().hard_floor == 0.5
    print("OK: safety PLC — software cannot lower legal hard floor (1.5m)")


if __name__ == "__main__":
    _demo()
