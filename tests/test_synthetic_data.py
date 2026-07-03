"""Tests for synthetic data generation and pipeline inputs."""

import numpy as np


class TestSyntheticDataGeneration:
    """Tests for synthetic data generation."""

    def test_daily_time_dimension(self, daily_ds):
        """Test daily dataset has correct time dimension."""
        assert len(daily_ds.time) == 365

    def test_weekly_time_dimension(self, weekly_ds):
        """Test weekly dataset has approximately 52 weeks for 365 days."""
        n_weeks = len(weekly_ds.time)
        assert 50 <= n_weeks <= 54

    def test_monthly_time_dimension(self, monthly_ds):
        """Test monthly dataset has correct time dimension."""
        assert len(monthly_ds.time) == 12

    def test_spatial_grid(self, daily_ds):
        """Test spatial grid dimensions."""
        assert daily_ds.sizes["y"] == 2
        assert daily_ds.sizes["x"] == 2

    def test_daily_variables(self, daily_ds):
        """Test daily dataset contains expected variables."""
        expected_vars = {
            "temperature",
            "precipitation",
            "humidity",
            "wind_speed",
            "cloud_fraction",
        }
        assert set(daily_ds.data_vars) == expected_vars

    def test_weekly_variables(self, weekly_ds):
        """Test weekly dataset contains expected variables."""
        expected_vars = {
            "pressure",
            "radiation",
            "albedo",
            "snow_depth",
            "aerosol",
        }
        assert set(weekly_ds.data_vars) == expected_vars

    def test_monthly_variables(self, monthly_ds):
        """Test monthly dataset contains expected variables."""
        assert set(monthly_ds.data_vars) == {"dummy_variable"}

    def test_static_variables(self, static_ds):
        """Test static dataset contains expected variables."""
        expected_vars = {
            "elevation",
            "surface_type",
            "roughness",
            "soil_moisture",
            "land_fraction",
        }
        assert set(static_ds.data_vars) == expected_vars


class TestSyntheticDataValues:
    """Tests for the fixture generator's explicit per-variable value contracts.

    Each variable is assigned a value shape: ``humidity``/``cloud_fraction`` are
    bounded to [0, 1]; ``precipitation``/``wind_speed`` are non-negative;
    ``surface_type`` is integer-valued.
    """

    def test_bounded_vars_in_unit_interval(self, daily_ds):
        for name in ("humidity", "cloud_fraction"):
            assert np.nanmin(daily_ds[name].values) >= 0, name
            assert np.nanmax(daily_ds[name].values) <= 1, name

    def test_positive_vars_non_negative(self, daily_ds):
        for name in ("precipitation", "wind_speed"):
            assert np.nanmin(daily_ds[name].values) >= 0, name

    def test_integer_typed_var_is_integer_valued(self, static_ds):
        surface_type = static_ds.surface_type.values
        assert np.all(surface_type == np.round(surface_type))

    def test_no_nan_in_generated_data(self, daily_ds, static_ds):
        assert not np.any(np.isnan(daily_ds.temperature.values))
        assert not np.any(np.isnan(static_ds.elevation.values))

    def test_crs_metadata(self, daily_ds, static_ds):
        """Test CRS metadata is set correctly."""
        assert daily_ds.attrs.get("crs") == "EPSG:4326"
        assert static_ds.attrs.get("crs") == "EPSG:4326"
