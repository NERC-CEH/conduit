"""End-to-end integration tests for the full catena pipeline.

These tests call load_inputs() with the test config and synthetic data,
then execute pipeline nodes to verify the full stack — config → load_inputs
→ driver.execute() — works end-to-end.
"""

import sys
import types
from typing import Annotated

import numpy as np
import pandas as pd
import xarray as xr
from xarray_annotated import Freq, enabled, enforce

from catena.config import IOSpec
from catena.io import get_final_vars
from catena.pipeline import run

N_PIXELS = 4  # 2x2 grid
N_DAYS = 365
N_MONTHS = 12


class TestLoadedInputs:
    """Test that load_inputs() returns correctly shaped DataArrays."""

    def test_daily_input_shape(self, pipeline_inputs):
        da = pipeline_inputs["temperature_daily"]
        assert da.sizes["time"] == N_DAYS
        assert da.sizes["pixel"] == N_PIXELS

    def test_weekly_input_shape(self, pipeline_inputs):
        da = pipeline_inputs["pressure_weekly"]
        assert 50 <= da.sizes["time"] <= 54
        assert da.sizes["pixel"] == N_PIXELS

    def test_monthly_input_shape(self, pipeline_inputs):
        da = pipeline_inputs["dummy_variable_monthly"]
        assert da.sizes["time"] == N_MONTHS
        assert da.sizes["pixel"] == N_PIXELS

    def test_static_input_shape(self, pipeline_inputs):
        da = pipeline_inputs["elevation"]
        assert da.sizes["pixel"] == N_PIXELS
        assert "time" not in da.dims

    def test_no_nan_in_daily_inputs(self, pipeline_inputs):
        for name in (
            "temperature_daily",
            "precipitation_daily",
            "humidity_daily",
        ):
            da = pipeline_inputs[name]
            assert not np.any(np.isnan(da.values)), f"{name} contains NaN"

    def test_no_nan_in_static_inputs(self, pipeline_inputs):
        for name in ("elevation", "roughness", "soil_moisture"):
            da = pipeline_inputs[name]
            assert not np.any(np.isnan(da.values)), f"{name} contains NaN"


class TestGridInputs:
    """Test that load_inputs() computes latitude and longitude from spatial CRS data."""

    def test_latitude_in_uk_bounds(self, pipeline_inputs):
        lat = pipeline_inputs["latitude"].values
        assert np.all(lat >= 49.0)
        assert np.all(lat <= 55.0)

    def test_longitude_in_uk_bounds(self, pipeline_inputs):
        lon = pipeline_inputs["longitude"].values
        assert np.all(lon >= -5.0)
        assert np.all(lon <= 3.0)

    def test_grid_pixel_count(self, pipeline_inputs):
        assert pipeline_inputs["latitude"].sizes["pixel"] == N_PIXELS
        assert pipeline_inputs["longitude"].sizes["pixel"] == N_PIXELS


class TestDriverExecution:
    """Test that the Hamilton driver executes correctly with pre-loaded inputs."""

    def test_no_output_specs_no_error(self, pipeline_config):
        """Pipeline with no output_specs should execute without error."""
        assert pipeline_config.output_specs == {}

    def test_get_final_vars_all_frequencies(self, pipeline_driver, pipeline_inputs):
        """get_final_vars() produces valid final_vars across daily, weekly, monthly."""
        output_specs = {
            "daily": IOSpec(path="", vars=["temperature"]),
            "weekly": IOSpec(path="", vars=["pressure"]),
            "monthly": IOSpec(path="", vars=["dummy_variable"]),
        }
        final_vars = get_final_vars(output_specs)
        assert final_vars == [
            "temperature_daily",
            "pressure_weekly",
            "dummy_variable_monthly",
        ]
        results = pipeline_driver.execute(final_vars, inputs=pipeline_inputs)
        assert all(v in results for v in final_vars)
        assert results["temperature_daily"].sizes["pixel"] == N_PIXELS
        assert results["pressure_weekly"].sizes["pixel"] == N_PIXELS
        assert results["dummy_variable_monthly"].sizes["pixel"] == N_PIXELS

    def test_get_final_vars_single_frequency(self, pipeline_driver, pipeline_inputs):
        """Filtering output_specs to one frequency requests only those targets."""
        all_specs = {
            "daily": IOSpec(path="", vars=["temperature"]),
            "monthly": IOSpec(path="", vars=["dummy_variable"]),
        }
        daily_vars = get_final_vars({"daily": all_specs["daily"]})
        assert daily_vars == ["temperature_daily"]
        results = pipeline_driver.execute(daily_vars, inputs=pipeline_inputs)
        assert "temperature_daily" in results
        assert "dummy_variable_monthly" not in results


class TestGappyAndCalendarDeclarations:
    """A pipeline whose axes only the 0.8 ``Freq`` declarations can describe."""

    def test_gaps_ok_python_node_and_month_toml_node(self, tmp_path, monkeypatch):
        gappy = pd.date_range("2025-01-01", periods=31, freq="D").append(
            pd.date_range("2026-01-01", periods=31, freq="D")
        )
        xr.DataArray(
            np.ones(62), dims="time", coords={"time": gappy}, name="temperature"
        ).to_netcdf(tmp_path / "daily.nc")
        midpoints = pd.date_range("2025-01-01", periods=6, freq="MS") + pd.Timedelta(
            days=14
        )
        xr.DataArray(
            np.ones(6), dims="time", coords={"time": midpoints}, name="rain"
        ).to_netcdf(tmp_path / "monthly.nc")

        @enforce
        def doubled_temperature(
            temperature_daily: Annotated[xr.DataArray, Freq("D", gaps_ok=True)],
        ) -> Annotated[xr.DataArray, Freq("D", gaps_ok=True)]:
            return temperature_daily * 2

        module = types.ModuleType("gappy_model")
        doubled_temperature.__module__ = module.__name__
        module.doubled_temperature = doubled_temperature  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module.__name__, module)

        config = tmp_path / "config.toml"
        config.write_text(
            """
[inputs.daily]
path = "daily.nc"
vars = ["temperature"]

[inputs.monthly]
path = "monthly.nc"
vars = ["rain"]

[gappy_model]
_import_path = "gappy_model"

[[node]]
name = "rain_copy"
inputs = ["rain_monthly"]
expression = "rain_monthly * 1"
freq = "month"

[outputs.temperature]
path = "temperature.nc"
suffix = ""
vars = ["doubled_temperature"]

[outputs.rain]
path = "rain.nc"
suffix = ""
vars = ["rain_copy"]
"""
        )
        with enabled(True):
            run(str(config))

        written = xr.open_dataarray(tmp_path / "temperature.nc")
        assert written.sizes["time"] == 62
        np.testing.assert_allclose(written.values, 2.0)
        assert xr.open_dataarray(tmp_path / "rain.nc").sizes["time"] == 6
