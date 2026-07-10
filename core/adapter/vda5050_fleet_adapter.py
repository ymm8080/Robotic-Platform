"""VDA5050 Fleet Adapter — bridges sap-bridge brand strategies to the core coordinator.

This adapter wraps a brand strategy (duck-typed: must provide ``handle_state()``,
``to_fleet_state()``, ``to_capability_vector()``, ``brand``, ``extract_errors()``)
and implements the ``FleetAdapter`` interface so the coordinator can ingest
VDA5050/MQTT state updates without knowing about vendor-specific message formats.

Usage::

    from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter
    adapter = VDA5050FleetAdapter(strategy=mir_strategy)
    coordinator.register_adapter(adapter)
"""
from __future__ import annotations

from typing import Any, Protocol

from core.adapter.fleet_adapter import FleetAdapter
from core.messages import FleetState


class _StrategyLike(Protocol):
    """Structural interface a strategy object must satisfy (no import needed)."""

    brand: str

    def handle_state(self, state: dict) -> Any:
        """Map raw vendor state dict → strategy-native RobotState."""
        ...

    def to_fleet_state(self, robot_state: Any) -> FleetState:
        """Convert strategy-native RobotState → core FleetState."""
        ...

    def to_capability_vector(self) -> CapabilityVector:  # noqa: F821
        """Return brand-specific CapabilityVector."""
        ...

    def extract_errors(self, state: dict) -> list[dict]:
        """Extract and normalize error list from raw state."""
        ...

    def dispatch(self, order: dict) -> Any:
        """Build brand-specific dispatch payload for an order."""
        ...


class VDA5050FleetAdapter(FleetAdapter):
    """FleetAdapter that delegates vendor-state translation to a brand strategy.

    The strategy object is typically a ``BaseStrategy`` subclass from
    ``sap-bridge/strategies/``, but any object matching ``_StrategyLike`` works.
    """

    def __init__(self, strategy: _StrategyLike) -> None:
        super().__init__(brand=strategy.brand)
        self._strategy = strategy

    # ── FleetAdapter abstract overrides ──────────────────────────

    def map_vendor_state(self, raw: dict) -> FleetState:
        """Translate a VDA5050 state dict into a unified FleetState.

        Delegates to the brand strategy: raw → RobotState → FleetState.
        """
        robot_state = self._strategy.handle_state(raw)
        return self._strategy.to_fleet_state(robot_state)

    def map_vendor_errors(self, raw_errors: list) -> list[str]:
        """Map VDA5050 error dicts to v5.0 error strings."""
        error_dicts = self._strategy.extract_errors(
            {"errors": raw_errors} if raw_errors else {}
        )
        return [
            f"{e.get('errorType', 'UNKNOWN')}:{e.get('errorLevel', 'WARN')}:"
            f"{e.get('errorDescription', '')}"
            for e in error_dicts
        ]

    # ── accessors ────────────────────────────────────────────────

    @property
    def strategy(self) -> _StrategyLike:
        """The wrapped brand strategy."""
        return self._strategy
