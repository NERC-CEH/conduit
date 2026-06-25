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
            "sunshine_fraction",
            "lai",
            "gpp",
        }
        assert set(daily_ds.data_vars) == expected_vars

    def test_weekly_variables(self, weekly_ds):
        """Test weekly dataset contains expected variables."""
        expected_vars = {
            "co2",
            "fapar",
            "ppfd",
            "pressure",
            "vpd",
        }
        assert expected_vars.issubset(set(weekly_ds.data_vars))

    def test_monthly_variables(self, monthly_ds):
        """Test monthly dataset contains expected variables."""
        expected_vars = {
            "dummy_variable",
            "temperature",
            "precipitation",
        }
        assert expected_vars.issubset(set(monthly_ds.data_vars))

    def test_static_variables(self, static_ds):
        """Test static dataset contains expected variables."""
        expected_vars = {
            "elevation",
            "plant_type",
            "max_soil_moisture",
            "clay_content",
            "soil_depth",
            "organic_carbon_stocks",
            "root_pool_init",
            "leaf_pool_init",
            "stem_pool_init",
        }
        assert set(static_ds.data_vars) == expected_vars


class TestSyntheticDataValues:
    """Tests for synthetic data values."""

    def test_temperature_range(self, daily_ds):
        """Test temperature is in reasonable range for UK."""
        temp = daily_ds.temperature.values
        assert np.nanmin(temp) > -20
        assert np.nanmax(temp) < 40

    def test_precipitation_non_negative(self, daily_ds):
        """Test precipitation is non-negative."""
        precip = daily_ds.precipitation.values
        assert np.nanmin(precip) >= 0

    def test_sunshine_fraction_valid(self, daily_ds):
        """Test sunshine fraction is between 0 and 1."""
        sunshine = daily_ds.sunshine_fraction.values
        assert np.nanmin(sunshine) >= 0
        assert np.nanmax(sunshine) <= 1

    def test_lai_valid(self, daily_ds):
        """Test LAI is non-negative."""
        lai = daily_ds.lai.values
        assert np.nanmin(lai) >= 0

    def test_gpp_non_negative(self, daily_ds):
        """Test GPP is non-negative."""
        gpp = daily_ds.gpp.values
        assert np.nanmin(gpp) >= 0

    def test_plant_type_valid(self, static_ds):
        """Test plant type values are valid (1=grassland, 2=C3 crop, 3=woodland)."""
        assert np.all(np.isin(static_ds.plant_type.values, [1, 2, 3]))

    def test_elevation_reasonable(self, static_ds):
        """Test elevation is in reasonable range."""
        elev = static_ds.elevation.values
        assert np.nanmin(elev) >= 0
        assert np.nanmax(elev) < 1000

    def test_crs_metadata(self, daily_ds, static_ds):
        """Test CRS metadata is set correctly."""
        assert daily_ds.attrs.get("crs") == "EPSG:4326"
        assert static_ds.attrs.get("crs") == "EPSG:4326"
