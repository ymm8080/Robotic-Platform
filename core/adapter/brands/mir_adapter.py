"""MiR brand adapter — wraps MiR250 VDA5050 v1.1 strategy."""
from __future__ import annotations

from core.adapter.brands._loader import _load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_mir_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the MiR strategy."""
    strategy = _load_strategy("mir")
    return VDA5050FleetAdapter(strategy=strategy)
