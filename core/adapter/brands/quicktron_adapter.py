"""Quicktron brand adapter — Quicktron Q100 VDA5050 v2.0 strategy."""
from __future__ import annotations

from core.adapter.brands._loader import _load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_quicktron_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the Quicktron strategy."""
    strategy = _load_strategy("quicktron")
    return VDA5050FleetAdapter(strategy=strategy)
