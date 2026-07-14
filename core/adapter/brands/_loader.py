"""Brand strategy loader — creates strategy instances with calibration support.

Phase 2 adds calibration support: load_strategy() now can read calibration
data from the database and inject the appropriate MapTransformer.

Previously tried to import from ``sap-bridge/strategies/``, which does not
exist yet.  v5.0 Phase 2 moves all strategy classes into
``core/adapter/brands/strategies.py`` so the core has zero dependency on
the sap-bridge layer.

Relationship to ``sap-bridge/strategies/``:
  - This module (core/adapter/brands/): loads core strategy classes for the
    v5.0 traffic coordinator.  The core strategies are lightweight, standalone
    classes that have zero dependency on sap-bridge.
  - sap-bridge/strategies/: SAP integration layer with richer features
    (ABC base, version checking, BrandQuirk, DispatchResult).  Used
    by the SAP bridge service for OData/RFC/IDoc integration.
  - The two layers are intentionally separate.  This loader imports only from
    core/adapter/brands/strategies.py to maintain core's zero-dependency
    guarantee.

Each brand strategy implements the ``_StrategyLike`` protocol expected by
``VDA5050FleetAdapter`` (handle_state, to_fleet_state, to_capability_vector,
extract_errors, dispatch, brand).

Phase 2 Calibration:
  - When transformer=None, load_strategy() attempts to load calibration from DB
  - Calibration data is used to create a MapTransformer via from_points or from_affine
  - Fallback to identity transformer if no calibration or invalid/expired
"""

from __future__ import annotations

import logging

from core.adapter.brands.strategies import (  # noqa: E402
    GeekPlusStrategy,
    HaiRoboticsStrategy,
    KukaStrategy,
    MirStrategy,
    OttoStrategy,
    QuicktronStrategy,
)
from core.adapter.map_transformer import MapTransformer
from core.platform.canonical_map_service import (
    CalibrationProvider,
    CalibrationService,
    fake_calibration_provider,
)

logger = logging.getLogger(__name__)

_STRATEGY_FACTORY: dict[str, type] = {
    "mir": MirStrategy,
    "otto": OttoStrategy,
    "kuka": KukaStrategy,
    "geekplus": GeekPlusStrategy,
    "hairobotics": HaiRoboticsStrategy,
    "quicktron": QuicktronStrategy,
}


# Calibration provider injection
# In production, this would be injected via dependency injection
# For now, default to fake provider for testing
_calibration_provider: CalibrationProvider = fake_calibration_provider
# Initialize service immediately since we can't reference before assignment
_calibration_service = CalibrationService(_calibration_provider)


def set_calibration_provider(provider: CalibrationProvider) -> None:
    """Set the calibration provider (for test injection)."""
    global _calibration_provider, _calibration_service
    _calibration_provider = provider
    _calibration_service = CalibrationService(provider)


def load_strategy(
    brand: str,
    transformer: MapTransformer | None = None,
    map_id: int | None = None,
    max_rmse_mm: float = 50.0,
) -> object:
    """Return a brand strategy instance for use with VDA5050FleetAdapter.

    Phase 2: If transformer=None, attempts to load calibration from DB.
    Falls back to identity transformer if no calibration or invalid/expired.

    Args:
        brand: Robot brand name (e.g., "mir")
        transformer: Optional pre-created transformer. If None, loads from DB.
        map_id: Optional specific map version for calibration lookup.
        max_rmse_mm: Maximum acceptable RMSE in millimeters (default: 50mm = 5cm).

    Returns:
        Strategy instance with transformer= injected.
    """
    cls = _STRATEGY_FACTORY.get(brand)
    if cls is None:
        raise KeyError(
            f"No strategy defined for brand {brand!r}. Available: {list(_STRATEGY_FACTORY)}"
        )

    # If transformer provided, use it
    if transformer is not None:
        return cls(transformer=transformer)

    # Otherwise, try to load calibration
    service = _calibration_service or CalibrationService(_calibration_provider)
    result = service.load_transformer(brand=brand, map_id=map_id, max_rmse_mm=max_rmse_mm)

    # Log warnings
    for warning in result.warnings:
        logger.warning(f"[{brand}] {warning}")

    if result.fallback_reason:
        logger.info(f"[{brand}] Using identity transformer: {result.fallback_reason}")

    return cls(transformer=result.transformer)


def supported_brands() -> list[str]:
    """Return the list of brands that have dedicated strategy classes."""
    return list(_STRATEGY_FACTORY)
