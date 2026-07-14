"""Database implementation of CalibrationProvider for sap-bridge.

This module provides the PostgreSQL-backed implementation of the
CalibrationProvider interface defined in core/platform/canonical_map_service.py.

Core remains zero-dependency on sap-bridge - this implementation lives here.
"""

from __future__ import annotations

import logging
from datetime import datetime

from core.platform.canonical_map_service import (
    BrandCalibration,
    CalibrationProvider,
    CalibrationService,
)

from db import connect

logger = logging.getLogger(__name__)


class DatabaseCalibrationProvider(CalibrationProvider):
    """PostgreSQL-backed calibration provider."""

    def get_calibration(
        self, brand: str, map_id: int | None = None, as_of: datetime | None = None
    ) -> BrandCalibration | None:
        """Get the latest valid calibration for a brand (and optional map_id)."""
        conn = None
        try:
            conn = connect()

            if map_id is not None:
                # Get specific calibration for this brand+map
                sql = """
                    SELECT id, brand, map_id, scale_x, scale_y, shear, rotation_deg,
                           translate_x, translate_y, reference_points,
                           residual_error_mm, calibrated_at, calibrated_by, valid_until
                    FROM brand_calibrations
                    WHERE brand = ? AND map_id = ?
                    ORDER BY calibrated_at DESC
                    LIMIT 1
                """
                cur = conn.execute(sql, (brand, map_id))
            else:
                # Get latest calibration for this brand across all maps
                sql = """
                    SELECT id, brand, map_id, scale_x, scale_y, shear, rotation_deg,
                           translate_x, translate_y, reference_points,
                           residual_error_mm, calibrated_at, calibrated_by, valid_until
                    FROM brand_calibrations
                    WHERE brand = ?
                    ORDER BY calibrated_at DESC
                    LIMIT 1
                """
                cur = conn.execute(sql, (brand,))

            row = cur.fetchone()
            if row is None:
                return None

            return BrandCalibration(
                id=row["id"],
                brand=row["brand"],
                map_id=row["map_id"],
                scale_x=row["scale_x"] or 1.0,
                scale_y=row["scale_y"] or 1.0,
                shear=row["shear"] or 0.0,
                rotation_deg=row["rotation_deg"] or 0.0,
                translate_x=row["translate_x"] or 0.0,
                translate_y=row["translate_y"] or 0.0,
                reference_points=row["reference_points"] or [],
                residual_error_mm=row["residual_error_mm"],
                calibrated_at=row["calibrated_at"],
                calibrated_by=row["calibrated_by"],
                valid_until=row["valid_until"],
            )

        except Exception as e:
            logger.error(f"Failed to load calibration for {brand}: {e}")
            return None
        finally:
            if conn:
                conn.close()


# Global instances for easy access
database_calibration_provider = DatabaseCalibrationProvider()
database_calibration_service = CalibrationService(database_calibration_provider)


def get_calibration(brand: str, map_id: int | None = None) -> BrandCalibration | None:
    """Convenience function to get calibration from sap-bridge layer."""
    return database_calibration_provider.get_calibration(brand, map_id)


def get_canonical_map_service() -> CalibrationService:
    """Get the canonical map service with database provider."""
    return database_calibration_service
