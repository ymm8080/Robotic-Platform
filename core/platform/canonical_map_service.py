"""Canonical map service — calibration data interface for core.

This module defines the interface for accessing brand calibration data without
creating a hard dependency on sap-bridge's database layer.

Phase 2 requires core to read calibration data from the PostgreSQL database,
 but core must remain zero-dep on sap-bridge. This module provides a clean
 abstraction:
 - Protocol definition (CalibrationProvider)
 - In-memory fake for testing
 - Database implementation lives in sap-bridge (not core)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.adapter.map_transformer import MapTransformer


@dataclass
class BrandCalibration:
    """Brand calibration data from the database."""

    id: int
    brand: str
    map_id: int
    calibrated_at: datetime
    calibrated_by: str
    scale_x: float = 1.0
    scale_y: float = 1.0
    shear: float = 0.0
    rotation_deg: float = 0.0
    translate_x: float = 0.0
    translate_y: float = 0.0
    reference_points: list[dict[str, Any]] = None
    residual_error_mm: float | None = None
    valid_until: datetime | None = None

    def is_valid(self, as_of: datetime | None = None) -> bool:
        """Check if calibration is still valid (not expired)."""
        if as_of is None:
            as_of = datetime.now()
        if self.valid_until is None:
            return True  # No expiry set
        return as_of < self.valid_until

    def rmse_acceptable(self, max_mm: float = 50.0) -> bool:
        """Check if RMSE is within acceptable bounds (default: 50mm = 5cm)."""
        if self.residual_error_mm is None:
            return True  # No RMSE measurement yet
        return self.residual_error_mm <= max_mm


class CalibrationProvider(ABC):
    """Abstract interface for accessing calibration data."""

    @abstractmethod
    def get_calibration(
        self, brand: str, map_id: int | None = None, as_of: datetime | None = None
    ) -> BrandCalibration | None:
        """Get the latest valid calibration for a brand (and optional map_id).

        Args:
            brand: Robot brand name (e.g., "mir")
            map_id: Optional specific map version. If None, returns the latest.
            as_of: Check validity as of this datetime. None = now.

        Returns:
            BrandCalibration if found and valid, None otherwise.
        """
        pass


@dataclass
class CalibrationResult:
    """Result of calibration loading with metadata."""

    transformer: MapTransformer
    calibration: BrandCalibration | None
    fallback_reason: str | None = None  # Why fallback occurred
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class CalibrationService:
    """Service to load calibration data and create MapTransformers."""

    def __init__(self, provider: CalibrationProvider):
        self.provider = provider

    def load_transformer(
        self,
        brand: str,
        map_id: int | None = None,
        as_of: datetime | None = None,
        max_rmse_mm: float = 50.0,
    ) -> CalibrationResult:
        """Load calibration data and create transformer for a brand.

        Returns CalibrationResult with either:
        - transformer from calibration + calibration data
        - fallback transformer (identity) + explanation
        """
        calibration = self.provider.get_calibration(brand, map_id, as_of)
        warnings = []

        if calibration is None:
            warnings.append(f"No calibration found for brand {brand!r}")
            return CalibrationResult(
                transformer=MapTransformer.identity(brand),
                calibration=None,
                fallback_reason=f"No calibration for {brand}",
                warnings=warnings,
            )

        # Check expiry
        if not calibration.is_valid(as_of):
            warnings.append(
                f"Calibration expired {calibration.valid_until} (now: {as_of or datetime.now()})"
            )
            return CalibrationResult(
                transformer=MapTransformer.identity(brand),
                calibration=calibration,
                fallback_reason="Expired calibration",
                warnings=warnings,
            )

        # Check RMSE
        if not calibration.rmse_acceptable(max_rmse_mm):
            warnings.append(f"RMSE too high: {calibration.residual_error_mm}mm > {max_rmse_mm}mm")
            return CalibrationResult(
                transformer=MapTransformer.identity(brand),
                calibration=calibration,
                fallback_reason="Unacceptable RMSE",
                warnings=warnings,
            )

        # Valid calibration - create transformer
        try:
            # Extract reference points in expected format
            native_points = []
            unified_points = []

            if calibration.reference_points:
                for pair in calibration.reference_points:
                    # Format: [{"native": [x, y], "unified": [x, y]}]
                    if "native" in pair and "unified" in pair:
                        native_points.append(tuple(pair["native"]))
                        unified_points.append(tuple(pair["unified"]))

            if native_points and unified_points and len(native_points) >= 3:
                transformer = MapTransformer.from_points(
                    brand=brand, native_points=native_points, unified_points=unified_points
                )
            else:
                # Fallback to affine parameters if no valid points
                # Standard affine: a=sx*cos(θ), b=-sx*sin(θ), c=sy*sin(θ), d=sy*cos(θ)
                from math import cos, radians, sin

                theta = radians(calibration.rotation_deg)
                transformer = MapTransformer.from_affine(
                    brand=brand,
                    a=calibration.scale_x * cos(theta),
                    b=-calibration.scale_x * sin(theta),
                    c=calibration.scale_y * sin(theta),
                    d=calibration.scale_y * cos(theta),
                    tx=calibration.translate_x,
                    ty=calibration.translate_y,
                )

            return CalibrationResult(
                transformer=transformer, calibration=calibration, warnings=warnings
            )

        except Exception as e:
            warnings.append(f"Failed to create transformer: {e}")
            return CalibrationResult(
                transformer=MapTransformer.identity(brand),
                calibration=calibration,
                fallback_reason=f"Transformer creation failed: {e}",
                warnings=warnings,
            )


class FakeCalibrationProvider(CalibrationProvider):
    """Fake calibration provider for testing without database."""

    def __init__(self):
        self.calibrations: dict[str, BrandCalibration] = {}

    def add_calibration(self, brand: str, map_id: int, **kwargs) -> None:
        """Add a fake calibration for testing."""
        from datetime import datetime, timedelta

        # Extract or set default calibrated_at
        if "calibrated_at" not in kwargs:
            kwargs["calibrated_at"] = datetime.now()

        calibration = BrandCalibration(
            id=len(self.calibrations) + 1,
            brand=brand,
            map_id=map_id,
            calibrated_at=kwargs["calibrated_at"],
            calibrated_by=kwargs.get("calibrated_by", "test"),
            **{k: v for k, v in kwargs.items() if k != "calibrated_at" and k != "calibrated_by"},
        )

        # Set default valid_until if not provided
        if calibration.valid_until is None:
            calibration.valid_until = datetime.now() + timedelta(days=90)
        key = f"{brand}:{map_id}"
        self.calibrations[key] = calibration

    def get_calibration(
        self, brand: str, map_id: int | None = None, as_of: datetime | None = None
    ) -> BrandCalibration | None:
        if map_id is None:
            # Find latest for brand
            candidates = [
                cal
                for cal in self.calibrations.values()
                if cal.brand == brand and cal.is_valid(as_of)
            ]
            if candidates:
                return max(candidates, key=lambda c: c.calibrated_at)
            return None

        key = f"{brand}:{map_id}"
        calibration = self.calibrations.get(key)
        if calibration and calibration.is_valid(as_of):
            return calibration
        return None

# Global instances
fake_calibration_provider = FakeCalibrationProvider()
_calibration_provider: CalibrationProvider = fake_calibration_provider
_calibration_service = CalibrationService(_calibration_provider)


def set_calibration_provider(provider: CalibrationProvider) -> None:
    """Set the calibration provider (for test injection)."""
    global _calibration_provider, _calibration_service
    _calibration_provider = provider
    _calibration_service = CalibrationService(provider)
