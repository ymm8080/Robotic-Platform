"""OTTO brand adapter — OTTO 100/1500 VDA5050 v2.0 strategy."""
from __future__ import annotations

from core.adapter.brands._loader import _load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_otto_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the OTTO strategy."""
    strategy = _load_strategy("otto")
    return VDA5050FleetAdapter(strategy=strategy)
