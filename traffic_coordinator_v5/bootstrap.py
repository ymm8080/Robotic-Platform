"""Bootstrap — register VDA5050 brand adapters with the coordinator.

This module wires vendor-specific FleetAdapter subclasses into the platform
loop.  Each brand adapter translates vendor-native state (VDA5050 / MQTT /
proprietary) into the unified FleetState the coordinator consumes.

Brand adapter classes are created in Phase 2 (``core/adapter/vda5050_fleet_adapter.py``
and ``core/adapter/brands/*_adapter.py``).  Until then, the bootstrap registers
a single generic adapter that passes through already-unified states.

Usage::

    from traffic_coordinator_v5.bootstrap import bootstrap_adapters
    bootstrap_adapters(coordinator)
"""
from __future__ import annotations

from core.adapter.fleet_adapter import FleetAdapter
from core.coordinator import RobotPlatformCoordinator


# Brand list the platform is expected to support (VDA5050 + proprietary).
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
    """Create a pass-through adapter for a brand.

    This is a placeholder until Phase 2 brand-specific adapters are built.
    The pass-through adapter expects ingest payloads that are already in
    the unified FleetState dict format.
    """
    adapter = FleetAdapter(brand=brand)

    # Override map_vendor_state to pass through unified payloads.
    # This lets the coordinator ingest pre-normalised states during
    # development and testing before real vendor adapters exist.
    def _passthrough(raw: dict) -> "core.messages.FleetState":  # noqa: F821
        from core.messages import FleetState, Pose, RobotMode

        return FleetState(
            robot_id=raw.get("robot_id", raw.get("robotId", "unknown")),
            boot_id=raw.get("boot_id", ""),
            pose=Pose(
                x=float(raw.get("x", 0.0)),
                y=float(raw.get("y", 0.0)),
                theta=float(raw.get("theta", 0.0)),
                position_initialized=bool(raw.get("position_initialized", False)),
                last_node_id=raw.get("last_node_id", raw.get("lane_id", "")),
            ),
            velocity=float(raw.get("velocity", 0.0)),
            battery_percent=float(raw.get("battery_percent", 100.0)),
            mode=RobotMode[raw.get("mode", "IDLE")] if raw.get("mode") in RobotMode.__members__ else RobotMode.IDLE,
            errors=[str(e) for e in raw.get("errors", []) or []],
            sensor_health=float(raw.get("sensor_health", 1.0)),
        )

    adapter.map_vendor_state = _passthrough  # type: ignore[method-assign]
    return adapter


def bootstrap_adapters(
    coordinator: RobotPlatformCoordinator,
    brands: list[str] | None = None,
) -> dict[str, FleetAdapter]:
    """Register fleet adapters for each supported brand.

    Returns a dict of ``{brand: adapter}`` for downstream use
    (e.g. HTTP ingest routing, MQTT topic binding).
    """
    brands = brands or SUPPORTED_BRANDS
    registered: dict[str, FleetAdapter] = {}

    for brand in brands:
        # TODO Phase 2: dispatch to brand-specific factory once adapters exist
        adapter = _create_generic_adapter(brand)
        coordinator.register_adapter(adapter)
        registered[brand] = adapter

    return registered
