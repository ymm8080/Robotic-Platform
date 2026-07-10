"""Lazy strategy loader — avoids hard imports from sap-bridge.

The sap-bridge directory uses a hyphen in its name so it cannot be imported
with a normal ``import`` statement.  Instead we use ``importlib`` with a
sys.path entry pointing to the project root.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any


def _ensure_project_root() -> None:
    """Add the project root to sys.path so 'sap-bridge' can be found."""
    root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_strategy(brand: str) -> Any:
    """Import a brand strategy class from sap-bridge/strategies/.

    Returns an *instance* of the strategy class.
    """
    _ensure_project_root()

    _MODULE_MAP: dict[str, str] = {
        "mir": "sap-bridge.strategies.mir",
        "otto": "sap-bridge.strategies.otto",
        "kuka": "sap-bridge.strategies.kuka",
        "geekplus": "sap-bridge.strategies.geekplus",
        "hairobotics": "sap-bridge.strategies.hairobotics",
        "quicktron": "sap-bridge.strategies.quicktron",
    }

    _CLASS_MAP: dict[str, str] = {
        "mir": "MirStrategy",
        "otto": "OttoStrategy",
        "kuka": "KukaStrategy",
        "geekplus": "GeekPlusStrategy",
        "hairobotics": "HaiRoboticsStrategy",
        "quicktron": "QuicktronStrategy",
    }

    module_name = _MODULE_MAP.get(brand)
    class_name = _CLASS_MAP.get(brand)

    if module_name is None or class_name is None:
        raise ValueError(f"Unknown brand: {brand!r}")

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return cls()
