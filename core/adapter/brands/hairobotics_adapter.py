"""Hai Robotics brand adapter — HaiPick A42 VDA5050 v2.0 strategy."""
from __future__ import annotations

from core.adapter.brands._loader import load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_hairobotics_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the Hai Robotics strategy."""
    strategy = load_strategy("hairobotics")
    return VDA5050FleetAdapter(strategy=strategy)
