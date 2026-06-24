"""Robot brand strategy implementations.

Strategy pattern for multi-brand VDA5050 robot support.
Each brand has its own strategy class handling state mapping,
action execution, battery normalization, and brand-specific quirks.
"""

from .base import BaseStrategy, RobotState, BatteryInfo, BrandQuirk
from .registry import StrategyRegistry, get_registry
from .kuka import KukaStrategy
from .mir import MirStrategy
from .otto import OttoStrategy
from .geekplus import GeekPlusStrategy
from .hairobotics import HaiRoboticsStrategy
from .quicktron import QuicktronStrategy

__all__ = [
    "BaseStrategy",
    "RobotState",
    "BatteryInfo",
    "BrandQuirk",
    "StrategyRegistry",
    "KukaStrategy",
    "MirStrategy",
    "OttoStrategy",
    "GeekPlusStrategy",
    "HaiRoboticsStrategy",
    "QuicktronStrategy",
]
