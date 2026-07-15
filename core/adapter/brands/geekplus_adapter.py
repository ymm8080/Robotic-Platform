"""Geek+ brand adapter — Geek+ C200 VDA5050 v2.0 strategy."""

from __future__ import annotations

from core.adapter.brands._loader import load_strategy
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter


def create_geekplus_adapter() -> VDA5050FleetAdapter:
    """Create a VDA5050FleetAdapter pre-configured with the Geek+ strategy."""
    strategy = load_strategy("geekplus")
    return VDA5050FleetAdapter(strategy=strategy)
