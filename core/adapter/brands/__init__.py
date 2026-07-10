"""Brand adapter registry — factory functions for VDA5050 brand adapters.

Each brand adapter wraps a sap-bridge strategy inside a VDA5050FleetAdapter
so the coordinator can ingest vendor-native states through a uniform interface.

Usage::

    from core.adapter.brands import create_mir_adapter
    adapter = create_mir_adapter()
    coordinator.register_adapter(adapter)
"""
from __future__ import annotations

from core.adapter.brands.geekplus_adapter import create_geekplus_adapter
from core.adapter.brands.hairobotics_adapter import create_hairobotics_adapter
from core.adapter.brands.kuka_adapter import create_kuka_adapter
from core.adapter.brands.mir_adapter import create_mir_adapter
from core.adapter.brands.otto_adapter import create_otto_adapter
from core.adapter.brands.quicktron_adapter import create_quicktron_adapter

BRAND_FACTORIES: dict[str, callable] = {
    "mir": create_mir_adapter,
    "otto": create_otto_adapter,
    "kuka": create_kuka_adapter,
    "geekplus": create_geekplus_adapter,
    "hairobotics": create_hairobotics_adapter,
    "quicktron": create_quicktron_adapter,
}

__all__ = [
    "BRAND_FACTORIES",
    "create_mir_adapter",
    "create_otto_adapter",
    "create_kuka_adapter",
    "create_geekplus_adapter",
    "create_hairobotics_adapter",
    "create_quicktron_adapter",
]
