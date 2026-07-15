"""KUKA brand adapter — KMP 1500/3000 VDA5050 v2.0 strategy."""

from __future__ import annotations

from core.adapter.brands._loader import load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_kuka_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the KUKA strategy."""
    strategy = load_strategy("kuka")
    return VDA5050FleetAdapter(strategy=strategy)
