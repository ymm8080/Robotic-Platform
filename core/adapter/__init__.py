"""适配层 — Fleet Adapter (影子状态机 + 超时熔断 + 硬编码后退).

白皮书: 适配层是平台与黑盒 SCS 之间的边界. 影子状态机是底线,
超时熔断是保险, 硬编码后退是兜底. 本地安全兜底由 SCS 负责.
"""

from __future__ import annotations

from core.adapter.fleet_adapter import AdapterCommand, CmdVel, FleetAdapter
from core.adapter.map_transformer import MapTransformer
from core.adapter.shadow_state_machine import (
    CircuitState,
    ShadowMismatch,
    ShadowStateMachine,
)

__all__ = [
    "AdapterCommand",
    "CircuitState",
    "CmdVel",
    "FleetAdapter",
    "MapTransformer",
    "ShadowMismatch",
    "ShadowStateMachine",
]
