"""Unit tests for the resample pipeline module.

The resample function is wrapped by @resolve (a Hamilton class-based decorator)
and cannot be called as a plain Python function. Tests exercise it via a minimal
Hamilton driver with DataArrays injected directly as inputs.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

from satterc.config import ResampleSpec
from satterc.dag import resample


def _make_daily_da(n_days: int = 365, n_pixel: int = 4, seed: int = 0) -> xr.DataArray:
    """Create a synthetic daily DataArray with (time, pixel) dims."""
    rng = np.random.default_rng(seed)
    time_index = pd.date_range("2020-01-01", periods=n_days, freq="D")
    data = rng.standard_normal((n_days, n_pixel))
    return xr.DataArray(
        data,
        dims=("time", "pixel"),
        coords={"time": time_index, "pixel": np.arange(n_pixel)},
    )


def _make_weekly_da(n_weeks: int = 52, n_pixel: int = 4, seed: int = 1) -> xr.DataArray:
    """Create a synthetic weekly DataArray with (time, pixel) dims."""
    rng = np.random.default_rng(seed)
    time_index = pd.date_range("2020-01-01", periods=n_weeks, freq="7D")
    data = rng.standard_normal((n_weeks, n_pixel))
    return xr.DataArray(
        data,
        dims=("time", "pixel"),
        coords={"time": time_index, "pixel": np.arange(n_pixel)},
    )


def _build_driver(*specs: ResampleSpec) -> driver.Driver:
    return (
        driver.Builder()
        .with_modules(resample)
        .with_config({"resample_specs": list(specs), ENABLE_POWER_USER_MODE: True})
        .build()
    )


@pytest.fixture(scope="module")
def daily_to_weekly_driver():
    return _build_driver(
        ResampleSpec(vars=["temperature"], source_freq="daily", target_freq="weekly")
    )


@pytest.fixture(scope="module")
def daily_to_monthly_driver():
    return _build_driver(
        ResampleSpec(vars=["temperature"], source_freq="daily", target_freq="monthly")
    )


@pytest.fixture(scope="module")
def weekly_to_monthly_driver():
    return _build_driver(
        ResampleSpec(vars=["temperature"], source_freq="weekly", target_freq="monthly")
    )


class TestDailyToWeeklyMean:
    """Tests for daily → weekly mean resampling."""

    @pytest.fixture(scope="class")
    def result(self, daily_to_weekly_driver):
        da = _make_daily_da(n_days=365)
        return daily_to_weekly_driver.execute(
            ["temperature_weekly"],
            inputs={"temperature_daily": da},
        )["temperature_weekly"]

    def test_output_is_dataarray(self, result):
        assert isinstance(result, xr.DataArray)

    def test_pixel_dimension_preserved(self, result):
        assert "pixel" in result.dims
        assert result.sizes["pixel"] == 4

    def test_weekly_output_shape(self, result):
        n_weeks = result.sizes["time"]
        assert 50 <= n_weeks <= 54

    def test_output_frequency_is_weekly(self, result):
        inferred = pd.infer_freq(result.coords["time"].values)
        assert inferred is not None
        assert inferred.startswith(("W", "7D"))

    def test_values_are_means(self):
        da = _make_daily_da(n_days=14, n_pixel=1)
        result = _build_driver(
            ResampleSpec(
                vars=["temperature"], source_freq="daily", target_freq="weekly"
            )
        ).execute(
            ["temperature_weekly"],
            inputs={"temperature_daily": da},
        )["temperature_weekly"]
        expected_week1 = da.isel(time=slice(0, 7)).mean("time").values
        np.testing.assert_allclose(result.isel(time=0).values, expected_week1)


class TestDailyToWeeklySum:
    """Tests for daily → weekly sum resampling."""

    @pytest.fixture(scope="class")
    def result(self):
        da = _make_daily_da(n_days=14, n_pixel=1)
        return _build_driver(
            ResampleSpec(
                vars=["precipitation"],
                source_freq="daily",
                target_freq="weekly",
                aggfunc="sum",
            )
        ).execute(
            ["precipitation_weekly"],
            inputs={"precipitation_daily": da},
        )["precipitation_weekly"]

    def test_output_is_dataarray(self, result):
        assert isinstance(result, xr.DataArray)

    def test_values_are_sums(self, result):
        da = _make_daily_da(n_days=14, n_pixel=1)
        expected_week1 = da.isel(time=slice(0, 7)).sum("time").values
        np.testing.assert_allclose(result.isel(time=0).values, expected_week1)


class TestMixedAggfuncs:
    """Multiple variables with different aggfuncs in a single driver."""

    def test_mean_and_sum_coexist(self):
        dr = _build_driver(
            ResampleSpec(
                vars=["temperature"],
                source_freq="daily",
                target_freq="weekly",
                aggfunc="mean",
            ),
            ResampleSpec(
                vars=["precipitation"],
                source_freq="daily",
                target_freq="weekly",
                aggfunc="sum",
            ),
        )
        da = _make_daily_da(n_days=14, n_pixel=1)
        result = dr.execute(
            ["temperature_weekly", "precipitation_weekly"],
            inputs={"temperature_daily": da, "precipitation_daily": da},
        )
        expected_mean = da.isel(time=slice(0, 7)).mean("time").values
        expected_sum = da.isel(time=slice(0, 7)).sum("time").values
        np.testing.assert_allclose(
            result["temperature_weekly"].isel(time=0).values, expected_mean
        )
        np.testing.assert_allclose(
            result["precipitation_weekly"].isel(time=0).values, expected_sum
        )


class TestDailyToMonthly:
    """Tests for daily → monthly resampling."""

    @pytest.fixture(scope="class")
    def result(self, daily_to_monthly_driver):
        da = _make_daily_da(n_days=365)
        return daily_to_monthly_driver.execute(
            ["temperature_monthly"],
            inputs={"temperature_daily": da},
        )["temperature_monthly"]

    def test_output_is_dataarray(self, result):
        assert isinstance(result, xr.DataArray)

    def test_pixel_dimension_preserved(self, result):
        assert "pixel" in result.dims
        assert result.sizes["pixel"] == 4

    def test_monthly_output_shape(self, result):
        assert result.sizes["time"] == 12

    def test_output_frequency_is_monthly(self, result):
        inferred = pd.infer_freq(result.coords["time"].values)
        assert inferred is not None
        assert inferred.startswith(("ME", "MS"))


class TestWeeklyToMonthly:
    """Tests for weekly → monthly resampling."""

    @pytest.fixture(scope="class")
    def result(self, weekly_to_monthly_driver):
        da = _make_weekly_da(n_weeks=52)
        return weekly_to_monthly_driver.execute(
            ["temperature_monthly"],
            inputs={"temperature_weekly": da},
        )["temperature_monthly"]

    def test_output_is_dataarray(self, result):
        assert isinstance(result, xr.DataArray)

    def test_pixel_dimension_preserved(self, result):
        assert "pixel" in result.dims
        assert result.sizes["pixel"] == 4

    def test_monthly_output_shape(self, result):
        assert result.sizes["time"] == 12


class TestResampleSpecValidation:
    """Tests for ResampleSpec.from_config validation."""

    def test_unsupported_direction_raises(self):
        with pytest.raises(ValueError, match="Unsupported resample direction"):
            ResampleSpec.from_config(
                {"vars": ["x"], "from_freq": "monthly", "to_freq": "daily"}
            )

    def test_unsupported_aggfunc_raises(self):
        with pytest.raises(ValueError, match="Unsupported aggfunc"):
            ResampleSpec.from_config(
                {
                    "vars": ["x"],
                    "from_freq": "daily",
                    "to_freq": "weekly",
                    "aggfunc": "banana",
                }
            )

    def test_default_aggfunc_is_mean(self):
        spec = ResampleSpec.from_config(
            {"vars": ["x"], "from_freq": "daily", "to_freq": "weekly"}
        )
        assert spec.aggfunc == "mean"

    def test_freq_property(self):
        spec = ResampleSpec(vars=["x"], source_freq="daily", target_freq="weekly")
        assert spec.freq == "7D"
        spec2 = ResampleSpec(vars=["x"], source_freq="daily", target_freq="monthly")
        assert spec2.freq == "1ME"
