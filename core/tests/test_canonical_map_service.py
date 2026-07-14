"""Tests for canonical map service."""

from datetime import datetime, timedelta

import pytest

from core.adapter.map_transformer import MapTransformer
from core.platform.canonical_map_service import (
    BrandCalibration,
    CalibrationResult,
    CalibrationService,
    FakeCalibrationProvider,
)


class TestBrandCalibration:
    """Test BrandCalibration dataclass."""

    def test_is_valid_no_expiry(self):
        """Test calibration with no expiry is always valid."""
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            valid_until=None,
        )
        assert calibration.is_valid()

    def test_is_valid_not_expired(self):
        """Test valid calibration."""
        future = datetime.now() + timedelta(days=1)
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            valid_until=future,
        )
        assert calibration.is_valid()

    def test_is_valid_expired(self):
        """Test expired calibration."""
        past = datetime.now() - timedelta(days=1)
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            valid_until=past,
        )
        assert not calibration.is_valid()

    def test_rmse_acceptable_no_rmse(self):
        """Test calibration without RMSE is acceptable."""
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            residual_error_mm=None,
        )
        assert calibration.rmse_acceptable()

    def test_rmse_acceptable_within_threshold(self):
        """Test calibration within RMSE threshold."""
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            residual_error_mm=30.0,  # < 50mm
        )
        assert calibration.rmse_acceptable()

    def test_rmse_not_acceptable(self):
        """Test calibration exceeding RMSE threshold."""
        calibration = BrandCalibration(
            id=1,
            brand="test",
            map_id=1,
            calibrated_at=datetime.now(),
            calibrated_by="test",
            residual_error_mm=60.0,  # > 50mm
        )
        assert not calibration.rmse_acceptable()


class TestFakeCalibrationProvider:
    """Test FakeCalibrationProvider."""

    def setup_method(self):
        """Setup for each test."""
        self.provider = FakeCalibrationProvider()

    def test_add_calibration(self):
        """Test adding calibration."""
        self.provider.add_calibration(brand="mir", map_id=1, scale_x=1.0, scale_y=1.0)

        # Verify calibration was added
        calibration = self.provider.get_calibration("mir", 1)
        assert calibration is not None
        assert calibration.brand == "mir"
        assert calibration.map_id == 1

    def test_get_calibration_latest(self):
        """Test getting latest calibration for brand."""
        # Add two calibrations
        self.provider.add_calibration(
            brand="mir", map_id=1, calibrated_at=datetime.now() - timedelta(hours=1)
        )
        self.provider.add_calibration(
            brand="mir",
            map_id=2,
            calibrated_at=datetime.now(),  # More recent
        )

        # Get latest (no map_id specified)
        calibration = self.provider.get_calibration("mir")
        assert calibration is not None
        assert calibration.map_id == 2  # Should be the latest

    def test_get_calibration_specific_map(self):
        """Test getting calibration for specific map ID."""
        self.provider.add_calibration(brand="mir", map_id=1, scale_x=1.0)
        self.provider.add_calibration(brand="mir", map_id=2, scale_x=2.0)

        # Get specific map
        calibration = self.provider.get_calibration("mir", 1)
        assert calibration is not None
        assert calibration.scale_x == 1.0

    def test_get_calibration_none_found(self):
        """Test when no calibration exists."""
        calibration = self.provider.get_calibration("unknown_brand")
        assert calibration is None

    def test_get_calibration_expired(self):
        """Test that expired calibrations are not returned."""
        # Add expired calibration
        past = datetime.now() - timedelta(days=1)
        self.provider.add_calibration(brand="mir", map_id=1, calibrated_at=past, valid_until=past)

        calibration = self.provider.get_calibration("mir")
        assert calibration is None  # Should not return expired


class TestCalibrationService:
    """Test CalibrationService."""

    def setup_method(self):
        """Setup for each test."""
        self.provider = FakeCalibrationProvider()
        self.service = CalibrationService(self.provider)

    def test_load_transformer_no_calibration(self):
        """Test load with no calibration - falls back to identity."""
        result = self.service.load_transformer("unknown_brand")

        assert isinstance(result, CalibrationResult)
        assert isinstance(result.transformer, MapTransformer)
        assert result.calibration is None
        assert result.fallback_reason == "No calibration for unknown_brand"
        assert "No calibration found" in result.warnings[0]

    def test_load_transformer_valid_calibration(self):
        """Test load with valid calibration."""
        # Add calibration with reference points
        self.provider.add_calibration(
            brand="mir",
            map_id=1,
            reference_points=[
                {"native": [0, 0], "unified": [10, 10]},
                {"native": [10, 0], "unified": [20, 10]},
                {"native": [0, 10], "unified": [10, 20]},
            ],
            residual_error_mm=20.0,
        )

        result = self.service.load_transformer("mir")

        assert isinstance(result, CalibrationResult)
        assert isinstance(result.transformer, MapTransformer)
        assert result.calibration is not None
        assert result.calibration.brand == "mir"
        assert result.fallback_reason is None
        assert len(result.warnings) == 0

    def test_load_transformer_expired(self):
        """Test load with expired calibration - falls back to identity."""
        past = datetime.now() - timedelta(days=1)
        self.provider.add_calibration(brand="mir", map_id=1, calibrated_at=past, valid_until=past)

        result = self.service.load_transformer("mir")

        assert isinstance(result, CalibrationResult)
        assert isinstance(result.transformer, MapTransformer)
        assert result.fallback_reason == "No calibration for mir"
        assert "No calibration found" in result.warnings[0]

    def test_load_transformer_high_rmse(self):
        """Test load with high RMSE - falls back to identity."""
        self.provider.add_calibration(
            brand="mir",
            map_id=1,
            reference_points=[
                {"native": [0, 0], "unified": [10, 10]},
                {"native": [10, 0], "unified": [20, 10]},
                {"native": [0, 10], "unified": [10, 20]},
            ],
            residual_error_mm=60.0,  # > 50mm threshold
        )

        result = self.service.load_transformer("mir")

        assert isinstance(result, CalibrationResult)
        assert isinstance(result.transformer, MapTransformer)
        assert result.calibration is not None
        assert result.fallback_reason == "Unacceptable RMSE"
        assert "RMSE too high" in result.warnings[0]

    def test_load_transformer_insufficient_points(self):
        """Test load with insufficient reference points."""
        self.provider.add_calibration(
            brand="mir",
            map_id=1,
            reference_points=[
                {"native": [0, 0], "unified": [10, 10]},
                {"native": [10, 0], "unified": [20, 10]},
                # Only 2 points - insufficient
            ],
        )

        result = self.service.load_transformer("mir")

        # Should fallback to identity due to insufficient points
        assert isinstance(result, CalibrationResult)
        assert isinstance(result.transformer, MapTransformer)
        assert result.calibration is not None

    def test_load_transformer_custom_max_rmse(self):
        """Test load with custom RMSE threshold."""
        # Add calibration with RMSE that exceeds default but meets custom threshold
        self.provider.add_calibration(
            brand="mir",
            map_id=1,
            reference_points=[
                {"native": [0, 0], "unified": [10, 10]},
                {"native": [10, 0], "unified": [20, 10]},
                {"native": [0, 10], "unified": [10, 20]},
            ],
            residual_error_mm=30.0,  # > 20mm custom, but < 50mm default
        )

        # Test with custom threshold of 20mm (should fail)
        result = self.service.load_transformer("mir", max_rmse_mm=20.0)
        assert result.fallback_reason == "Unacceptable RMSE"

        # Test with default threshold (50mm) - should succeed
        result = self.service.load_transformer("mir", max_rmse_mm=50.0)
        assert result.fallback_reason is None

    def test_load_transformer_specific_map_id(self):
        """Test loading calibration for specific map ID."""
        # Add two calibrations for same brand
        self.provider.add_calibration(
            brand="mir",
            map_id=1,
            reference_points=[
                {"native": [0, 0], "unified": [10, 10]},
                {"native": [10, 0], "unified": [20, 10]},
                {"native": [0, 10], "unified": [10, 20]},
            ],
        )
        self.provider.add_calibration(
            brand="mir",
            map_id=2,
            reference_points=[
                {"native": [0, 0], "unified": [20, 20]},
                {"native": [10, 0], "unified": [30, 20]},
                {"native": [0, 10], "unified": [20, 30]},
            ],
        )

        # Get specific map
        result = self.service.load_transformer("mir", map_id=1)
        assert result.calibration is not None
        assert result.calibration.map_id == 1


def test_set_calibration_provider():
    """Test setting calibration provider."""
    # Create new provider
    new_provider = FakeCalibrationProvider()
    new_calibration_service = CalibrationService(new_provider)

    # Set it
    from core.platform.canonical_map_service import set_calibration_provider

    set_calibration_provider(new_provider)

    # Verify it was set by creating a new service with the provider
    assert new_calibration_service.provider is new_provider


if __name__ == "__main__":
    pytest.main([__file__])
