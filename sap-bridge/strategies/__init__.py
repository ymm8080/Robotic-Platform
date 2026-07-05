"""Robot brand strategy implementations.

Strategy pattern for multi-brand VDA5050 robot support.
Each brand has its own strategy class handling state mapping,
action execution, battery normalization, and brand-specific quirks.
"""

from .base import BaseStrategy, BatteryInfo, BrandQuirk, DispatchResult, RobotState
from .geekplus import GeekPlusStrategy
from .hairobotics import HaiRoboticsStrategy
from .kuka import KukaStrategy
from .mir import MirStrategy
from .otto import OttoStrategy
from .quicktron import QuicktronStrategy
from .registry import StrategyRegistry, UnknownBrandError, get_registry

__all__ = [
    "BaseStrategy",
    "RobotState",
    "BatteryInfo",
    "BrandQuirk",
    "DispatchResult",
    "StrategyRegistry",
    "UnknownBrandError",
    "get_registry",
    "KukaStrategy",
    "MirStrategy",
    "OttoStrategy",
    "GeekPlusStrategy",
    "HaiRoboticsStrategy",
    "QuicktronStrategy",
]
