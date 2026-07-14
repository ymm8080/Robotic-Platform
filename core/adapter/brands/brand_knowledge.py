"""Shared brand knowledge deduplication for dual strategy layers.

This module contains brand-specific facts that MUST be identical across both:
- core/adapter/brands/strategies.py (DISPATCH side)
- sap-bridge/strategies/*.py (SAP side)

Only facts that are genuinely shared and critical for both layers' operations
are extracted here. Facts that legitimately differ due to different responsibilities
are intentionally kept separate.

Brand keys match those used by both layers: "mir", "otto", "kuka",
"geekplus", "hairobotics", "quicktron".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

# ── Shared constants and mappings (immutable) ────────────────────────

# Battery conversion constants
_MILLIVOLT_TO_PERCENT = 0.004  # OTTO: 25000 mV ≈ 100%
_VOLT_TO_PERCENT = 2.083  # 48V nominal → 100%

# ── Immutable brand registry and accessor ─────────────────────────────


@dataclass(frozen=True)
class BrandKnowledge:
    """Brand-specific knowledge that MUST be identical across both strategy layers.

    frozen=True blocks attribute reassignment; __post_init__ additionally
    shallow-freezes the collection-typed fields (tuples + read-only mapping
    proxies) so shared knowledge cannot be mutated in place at runtime. Nested
    lists inside default_capability_vector remain mutable — deep-freezing is
    out of scope for Phase 0.
    """

    # Brand identifier (matches both core and SAP layer usage)
    brand: str

    # VDA5050 version support (MUST match SAP layer supported_versions)
    supported_versions: tuple[str, ...]

    # Default capability vector (MUST match core layer to_fleet_state())
    default_capability_vector: Mapping[str, Any]

    # Battery quirks - format and conversion constants
    battery_quirks: Mapping[str, Any] = field(default_factory=dict)

    # State field quirks (which fields to use for same meaning)
    field_mapping: Mapping[str, str] = field(default_factory=dict)

    # Robot model support list (for capability vector)
    supported_models: tuple[str, ...] = field(default_factory=tuple)

    # Error processing quirks
    error_quirks: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Shallow-freeze collection fields so the registry is read-only."""
        object.__setattr__(self, "supported_versions", tuple(self.supported_versions))
        object.__setattr__(self, "supported_models", tuple(self.supported_models))
        object.__setattr__(
            self, "default_capability_vector", MappingProxyType(self.default_capability_vector)
        )
        object.__setattr__(self, "battery_quirks", MappingProxyType(self.battery_quirks))
        object.__setattr__(self, "field_mapping", MappingProxyType(self.field_mapping))
        object.__setattr__(self, "error_quirks", MappingProxyType(self.error_quirks))

    def __hash__(self) -> int:
        """Hash for use in sets (e.g. validation)."""
        return hash(self.brand)


# ── Shared brand knowledge registry ──────────────────────────────────

BRAND_KNOWLEDGE: dict[str, BrandKnowledge] = {}


def get_brand_knowledge(brand: str) -> BrandKnowledge:
    """Get brand knowledge for the given brand.

    Args:
        brand: Brand identifier ("mir", "otto", "kuka", "geekplus", "hairobotics", "quicktron")

    Returns:
        BrandKnowledge object for the requested brand

    Raises:
        KeyError: If brand is not registered
    """
    if brand not in BRAND_KNOWLEDGE:
        raise KeyError(f"Brand '{brand}' not found in shared knowledge registry")
    return BRAND_KNOWLEDGE[brand]


def register_brand_knowledge(knowledge: BrandKnowledge) -> None:
    """Register brand knowledge in the shared registry.

    Args:
        knowledge: BrandKnowledge object to register

    Raises:
        ValueError: If brand already registered (prevents accidental overwrite)
    """
    if knowledge.brand in BRAND_KNOWLEDGE:
        raise ValueError(
            f"Brand '{knowledge.brand}' already registered "
            "- intentional changes require re-deploying"
        )

    BRAND_KNOWLEDGE[knowledge.brand] = knowledge


# ── Brand knowledge definitions (shared across both layers) ──────────


def _initialize_brand_knowledge() -> None:
    """Initialize the shared brand knowledge registry.

    This MUST be called at module load time to populate the registry.
    Each entry contains the shared facts that both strategy layers depend on.
    """

    # MiR shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="mir",
            supported_versions=["1.1.0"],  # MUST match SAP layer
            default_capability_vector={
                "payload_kg": 1350.0,
                "max_speed": 2.0,
                "supported_models": ["MiR250", "MiR600", "MiR1350"],
                "action_primitives": ["MOVE", "DOCK"],
                "env": {"max_grade": 0.05, "floor_threshold": 0.01, "min_friction": 0.4},
                "supports_reverse": True,
            },
            battery_quirks={
                "format": "percentage_direct",  # Reports batteryCharge as 0-100
                "voltage_field": "batteryVoltage",  # Field name for voltage if available
            },
            field_mapping={
                "mode_field": "operatingMode",  # Standard VDA5050 field
                "position_field": "agvPosition",  # Standard VDA5050 field
                "load_field": "loads",  # Standard VDA5050 field (plural)
            },
            supported_models=["MiR250", "MiR600", "MiR1350"],
            error_quirks={
                "driving_state": "DRIVING",  # Reports DRIVING instead of MOVING
                "waiting_before_idle": True,  # Sends WAITING before IDLE after job
            },
        )
    )

    # OTTO shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="otto",
            supported_versions=["2.0.0"],  # MUST match SAP layer
            default_capability_vector={
                "payload_kg": 1500.0,
                "max_speed": 2.0,
                "supported_models": ["OTTO 100", "OTTO 750", "OTTO 1500"],
                "action_primitives": ["MOVE", "DOCK"],
                "env": {"max_grade": 0.05, "floor_threshold": 0.01, "min_friction": 0.4},
                "supports_reverse": True,
            },
            battery_quirks={
                "format": "millivolt",  # Reports batteryVoltage in mV
                "conversion": _MILLIVOLT_TO_PERCENT,
                "charge_field": "batteryCharge",  # May report percentage alongside
                "mv_min": 48000,  # LiFePO4 empty voltage
                "mv_max": 54600,  # LiFePO4 full voltage
            },
            field_mapping={
                "mode_field": "operatingMode",  # Standard VDA5050 field
                "position_field": "agvPosition",  # Standard VDA5050 field
                "load_field": "loads",  # Standard VDA5050 field
            },
            supported_models=["OTTO 100", "OTTO 750", "OTTO 1500"],
            error_quirks={
                "charging_detection": "both",  # Detect charging via flag or voltage
                "voltage_threshold": 53500,  # >53.5V indicates charging
            },
        )
    )

    # KUKA shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="kuka",
            supported_versions=["2.0.0"],  # MUST match SAP layer
            default_capability_vector={
                "payload_kg": 1500.0,
                "max_speed": 2.0,
                "supported_models": ["KMP 600", "KMP 1500", "KMP 3000"],
                "action_primitives": ["MOVE", "DOCK", "PICK", "PLACE"],
                "env": {"max_grade": 0.03, "floor_threshold": 0.01, "min_friction": 0.4},
                "supports_reverse": True,
            },
            battery_quirks={
                "format": "percentage_direct",  # Reports batteryCharge as 0-100
                "voltage_field": "batteryVoltage",
                "health_field": "batteryHealth",  # Additional health metric
            },
            field_mapping={
                "mode_field": "operatingMode",  # Standard VDA5050 field
                "position_field": "agvPosition",  # Standard VDA5050 field
                # Note: singular vs plural, some versions use "load" not "loads"
                "load_field": "load",
            },
            supported_models=["KMP 600", "KMP 1500", "KMP 3000"],
            error_quirks={
                "battery_threshold": 5,  # ≤5% triggers automatic CHARGING state
            },
        )
    )

    # Geek+ shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="geekplus",
            supported_versions=["1.1.0", "2.0.0"],  # MUST match SAP layer (dual protocol)
            default_capability_vector={
                "payload_kg": 1000.0,
                "max_speed": 1.8,
                "supported_models": ["P500", "P800", "P1200", "RS5"],
                "action_primitives": ["MOVE", "PICK", "PLACE", "CHARGE"],
                "env": {"max_grade": 0.02, "floor_threshold": 0.005, "min_friction": 0.4},
                "supports_reverse": False,
            },
            battery_quirks={
                "format": "percentage_only",  # No voltage field, percentage only
                "charge_field": "batteryCharge",  # May use "percentage" as fallback
            },
            field_mapping={
                "mode_field": "sysStatus",  # Uses sysStatus instead of operatingMode
                "position_field": "agvPosition",  # Standard VDA5050 field
                "load_field": "load",  # May vary by protocol
            },
            supported_models=["P500", "P800", "P1200", "RS5"],
            error_quirks={
                # Protocol detection: P/S series proprietary, M/R VDA5050
                "series_split": "P/S_vda5050",
                "manufacturer_field": "GeekPlus",  # Specific field value required
            },
        )
    )

    # HaiRobotics shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="hairobotics",
            supported_versions=["2.0.0"],  # MUST match SAP layer
            default_capability_vector={
                "payload_kg": 600.0,
                "max_speed": 1.5,
                "supported_models": ["ACR A42", "ACR A42T", "HAIPICK A3"],
                "action_primitives": ["MOVE", "LIFT_FORK", "PICK", "PLACE"],
                "env": {"max_grade": 0.01, "floor_threshold": 0.005, "min_friction": 0.45},
                "supports_reverse": False,
            },
            battery_quirks={
                "format": "percentage_direct",  # Reports batteryCharge/soc as 0-100
                "charge_field": "batteryCharge",  # May use "soc" as fallback
            },
            field_mapping={
                "mode_field": "robotMode",  # Uses robotMode + taskStatusCode
                "position_field": "agvPosition",  # Standard VDA5050 field
                "load_field": "load",  # Typically tote-based
            },
            supported_models=["ACR A42", "ACR A42T", "HAIPICK A3"],
            error_quirks={
                "dual_protocol": "ACR_only_HAIQ",  # ACR uses HAIQ, others VDA5050
                "3d_storage": True,  # Needs awareness of aisle/column/height
            },
        )
    )

    # Quicktron shared knowledge
    register_brand_knowledge(
        BrandKnowledge(
            brand="quicktron",
            supported_versions=["1.1.0", "2.0.0"],  # MUST match SAP layer (format unconfirmed)
            default_capability_vector={
                "payload_kg": 1000.0,
                "max_speed": 2.0,
                "supported_models": ["QuickBin M100", "QuickBin M600", "QuickBin C200"],
                "action_primitives": ["MOVE", "LIFT_FORK", "PICK", "PLACE"],
                "env": {"max_grade": 0.03, "floor_threshold": 0.01, "min_friction": 0.4},
                "supports_reverse": True,
            },
            battery_quirks={
                "format": "adaptive",  # May report % or mV, auto-detected
                "charge_field": "batteryCharge",  # May use batteryPercent
                "mv_min": 21000,  # [GUESS] 24V system min
                "mv_max": 29200,  # [GUESS] 24V system max
            },
            field_mapping={
                "mode_field": "robotStatus",  # Uses robotStatus alongside operatingMode
                "position_field": "agvPosition",  # Standard VDA5050 field
                "load_field": "loads",  # Standard VDA5050 field
            },
            supported_models=["QuickBin M100", "QuickBin M600", "QuickBin C200"],
            error_quirks={
                "chinese_error_codes": True,  # E001 -> mapped to human-readable
                "bin_status": True,  # Has additional quickBinStatus field
            },
        )
    )


# ── Initialize on module load (ensure data is available immediately) ───

_initialize_brand_knowledge()
