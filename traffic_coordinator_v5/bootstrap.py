"""Bootstrap — register VDA5050 brand adapters with the coordinator.

This module wires vendor-specific ``VDA5050FleetAdapter`` instances into
the platform loop. Each brand adapter translates vendor-native state
(VDA5050 MQTT uplink) into the unified FleetState the coordinator consumes.

Brand strategy classes live in ``core/adapter/brands/strategies.py`` and
are loaded via ``core/adapter/brands/_loader.py``.

Usage::

    from traffic_coordinator_v5.bootstrap import bootstrap_adapters
    bootstrap_adapters(coordinator)
"""

from __future__ import annotations

from core.adapter.brands._loader import load_strategy
from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.vda5050_fleet_adapter import VDA5050FleetAdapter
from core.coordinator import RobotPlatformCoordinator
from core.messages import FleetState, Pose, RobotMode

SUPPORTED_BRANDS = [
    "mir",
    "otto",
    "kuka",
    "geekplus",
    "hairobotics",
    "quicktron",
    "generic",
]


def _create_generic_adapter(brand: str) -> FleetAdapter:
    """Create a pass-through adapter for brands without a dedicated strategy.

    Used for ``generic`` and any brand that lacks a strategy class.
    The pass-through adapter expects ingest payloads that are already in
    the unified FleetState dict format.
    """
    adapter = FleetAdapter(brand=brand)

    def _passthrough(raw: dict) -> FleetState:
        return FleetState(
            robot_id=raw.get("robot_id", raw.get("robotId", "unknown")),
            boot_id=raw.get("boot_id", raw.get("bootId", "")),
            pose=Pose(
                x=float(raw.get("x", 0.0)),
                y=float(raw.get("y", 0.0)),
                theta=float(raw.get("theta", 0.0)),
                position_initialized=bool(
                    raw.get("position_initialized",
                            raw.get("positionInitialized", False))
                ),
                last_node_id=raw.get("last_node_id", raw.get("lane_id",
                                    raw.get("lastNodeId", ""))),
            ),
            velocity=float(raw.get("velocity", 0.0)),
            battery_percent=float(raw.get("battery_percent",
                                          raw.get("batteryPercent", 100.0))),
            mode=(
                RobotMode[raw["mode"]]
                if raw.get("mode") in RobotMode.__members__
                else RobotMode.IDLE
            ),
            errors=[str(e) for e in raw.get("errors", []) or []],
            sensor_health=float(raw.get("sensor_health", 1.0)),
        )

    adapter.map_vendor_state = _passthrough  # type: ignore[method-assign]
    return adapter


def _create_vda5050_adapter(brand: str) -> FleetAdapter:
    """Create a VDA5050FleetAdapter backed by a real brand strategy.

    Falls back to the generic pass-through adapter if no strategy class
    is registered for ``brand`` (e.g. ``generic``).
    """
    try:
        strategy = load_strategy(brand)
        return VDA5050FleetAdapter(strategy=strategy)
    except KeyError:
        return _create_generic_adapter(brand)


def bootstrap_adapters(
    coordinator: RobotPlatformCoordinator,
    brands: list[str] | None = None,
) -> dict[str, FleetAdapter]:
    """Register fleet adapters for each supported brand.

    Brands with dedicated strategy classes in ``core/adapter/brands/strategies.py``
    get ``VDA5050FleetAdapter`` instances that translate real VDA5050 messages.
    Brands without a strategy (e.g. ``generic``) get a pass-through adapter
    that accepts pre-normalized FleetState dicts.

    Returns a dict of ``{brand: adapter}`` for downstream use
    (e.g. HTTP ingest routing, MQTT topic binding).
    """
    brands = brands or SUPPORTED_BRANDS
    registered: dict[str, FleetAdapter] = {}

    for brand in brands:
        adapter = _create_vda5050_adapter(brand)
        coordinator.register_adapter(adapter)
        registered[brand] = adapter

    return registered
