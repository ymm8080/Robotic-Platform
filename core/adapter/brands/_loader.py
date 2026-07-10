"""Brand strategy loader — creates strategy instances from local definitions.

Previously tried to import from ``sap-bridge/strategies/``, which does not
exist yet.  v5.0 Phase 2 moves all strategy classes into
``core/adapter/brands/strategies.py`` so the core has zero dependency on
the sap-bridge layer.

Each brand strategy implements the ``_StrategyLike`` protocol expected by
``VDA5050FleetAdapter`` (handle_state, to_fleet_state, to_capability_vector,
extract_errors, dispatch, brand).
"""

from __future__ import annotations

from core.adapter.brands.strategies import (  # noqa: E402
    GeekPlusStrategy,
    HaiRoboticsStrategy,
    KukaStrategy,
    MirStrategy,
    OttoStrategy,
    QuicktronStrategy,
)
from core.adapter.map_transformer import MapTransformer

_STRATEGY_FACTORY: dict[str, type] = {
    "mir": MirStrategy,
    "otto": OttoStrategy,
    "kuka": KukaStrategy,
    "geekplus": GeekPlusStrategy,
    "hairobotics": HaiRoboticsStrategy,
    "quicktron": QuicktronStrategy,
}


def load_strategy(
    brand: str, transformer: MapTransformer | None = None
) -> object:
    """Return a brand strategy instance for use with VDA5050FleetAdapter.

    Returns ``None`` for brands without a dedicated strategy
    (e.g. "generic"), where the caller should fall back to the
    generic pass-through adapter.
    """
    cls = _STRATEGY_FACTORY.get(brand)
    if cls is None:
        raise KeyError(
            f"No strategy defined for brand {brand!r}. "
            f"Available: {list(_STRATEGY_FACTORY)}"
        )
    return cls(transformer=transformer)


def supported_brands() -> list[str]:
    """Return the list of brands that have dedicated strategy classes."""
    return list(_STRATEGY_FACTORY)
