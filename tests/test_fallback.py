"""Tests for conduit.setup_utils.data_gen.fallback."""

import types

import numpy as np
import pandas as pd
import xarray as xr

from conduit.setup_utils.data_gen.fallback import (
    _infer_fallback_type,
    _make_daily_fallback,
    _make_static_fallback,
    build_fallback_module,
)

N_DAYS = 10
N_LAT, N_LON = 2, 3
N_PIXELS = N_LAT * N_LON

PIXEL_COORDS = pd.MultiIndex.from_product(
    [range(N_LAT), range(N_LON)], names=["y", "x"]
)
TIME_COORD = pd.date_range("2020-01-01", periods=N_DAYS, freq="D").values


# ---------------------------------------------------------------------------
# _infer_fallback_type
# ---------------------------------------------------------------------------


class TestInferFallbackType:
    def test_fraction_keyword_is_bounded(self):
        assert _infer_fallback_type("sunshine_fraction") == "bounded"

    def test_ratio_keyword_is_bounded(self):
        assert _infer_fallback_type("dpm_rpm_ratio") == "bounded"

    def test_fapar_keyword_is_bounded(self):
        assert _infer_fallback_type("fapar_weekly") == "bounded"

    def test_precipitation_keyword_is_positive(self):
        assert _infer_fallback_type("precipitation") == "positive"

    def test_lai_keyword_is_positive(self):
        assert _infer_fallback_type("lai_daily") == "positive"

    def test_gpp_keyword_is_positive(self):
        assert _infer_fallback_type("gpp_monthly") == "positive"

    def test_vpd_keyword_is_positive(self):
        assert _infer_fallback_type("vpd_weekly") == "positive"

    def test_pressure_keyword_is_positive(self):
        assert _infer_fallback_type("pressure_daily") == "positive"

    def test_ppfd_keyword_is_positive(self):
        assert _infer_fallback_type("ppfd") == "positive"

    def test_type_suffix_is_integer(self):
        assert _infer_fallback_type("plant_type") == "integer"

    def test_class_suffix_is_integer(self):
        assert _infer_fallback_type("land_class") == "integer"

    def test_flag_suffix_is_integer(self):
        assert _infer_fallback_type("cover_flag") == "integer"

    def test_unknown_name_is_gaussian(self):
        assert _infer_fallback_type("temperature") == "gaussian"
        assert _infer_fallback_type("elevation") == "gaussian"
        assert _infer_fallback_type("co2") == "gaussian"


# ---------------------------------------------------------------------------
# _make_daily_fallback
# ---------------------------------------------------------------------------


class TestMakeDailyFallback:
    def test_returns_callable(self):
        assert callable(_make_daily_fallback("some_var"))

    def test_function_name_is_var_daily(self):
        fn = _make_daily_fallback("temperature")
        assert fn.__name__ == "temperature_daily"

    def test_output_is_dataarray(self):
        fn = _make_daily_fallback("temperature")
        result = fn(TIME_COORD, PIXEL_COORDS)
        assert isinstance(result, xr.DataArray)

    def test_output_dims(self):
        fn = _make_daily_fallback("temperature")
        result = fn(TIME_COORD, PIXEL_COORDS)
        assert result.dims == ("time", "pixel")

    def test_output_shape(self):
        fn = _make_daily_fallback("some_var")
        result = fn(TIME_COORD, PIXEL_COORDS)
        assert result.sizes["time"] == N_DAYS
        assert result.sizes["pixel"] == N_PIXELS

    def test_bounded_values_in_range(self):
        fn = _make_daily_fallback("sunshine_fraction")
        result = fn(TIME_COORD, PIXEL_COORDS)
        assert np.all(result.values >= 0.0)
        assert np.all(result.values <= 1.0)

    def test_positive_values_non_negative(self):
        fn = _make_daily_fallback("precipitation")
        result = fn(TIME_COORD, PIXEL_COORDS)
        assert np.all(result.values >= 0.0)

    def test_integer_values_are_whole_numbers(self):
        fn = _make_daily_fallback("plant_type")
        result = fn(TIME_COORD, PIXEL_COORDS)
        np.testing.assert_array_equal(result.values, np.floor(result.values))


# ---------------------------------------------------------------------------
# _make_static_fallback
# ---------------------------------------------------------------------------


class TestMakeStaticFallback:
    def test_returns_callable(self):
        assert callable(_make_static_fallback("elevation"))

    def test_function_name_is_var_name(self):
        fn = _make_static_fallback("elevation")
        assert fn.__name__ == "elevation"

    def test_output_is_dataarray(self):
        fn = _make_static_fallback("elevation")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        assert isinstance(result, xr.DataArray)

    def test_output_dims(self):
        fn = _make_static_fallback("elevation")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        assert result.dims == ("pixel",)

    def test_output_pixel_count(self):
        fn = _make_static_fallback("elevation")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        assert result.sizes["pixel"] == N_PIXELS

    def test_bounded_static_in_range(self):
        fn = _make_static_fallback("sunshine_fraction")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        assert np.all(result.values >= 0.0)
        assert np.all(result.values <= 1.0)

    def test_positive_static_non_negative(self):
        fn = _make_static_fallback("precipitation")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        assert np.all(result.values >= 0.0)

    def test_integer_static_whole_numbers(self):
        fn = _make_static_fallback("plant_type")
        result = fn(N_LAT, N_LON, PIXEL_COORDS)
        np.testing.assert_array_equal(result.values, np.floor(result.values))


# ---------------------------------------------------------------------------
# build_fallback_module
# ---------------------------------------------------------------------------


class TestBuildFallbackModule:
    def test_returns_module(self):
        mod = build_fallback_module([], [])
        assert isinstance(mod, types.ModuleType)

    def test_daily_var_attaches_as_var_daily(self):
        mod = build_fallback_module(["temperature"], [])
        assert hasattr(mod, "temperature_daily")
        assert callable(mod.temperature_daily)

    def test_static_var_attaches_as_var_name(self):
        mod = build_fallback_module([], ["elevation"])
        assert hasattr(mod, "elevation")
        assert callable(mod.elevation)

    def test_multiple_vars_all_attached(self):
        mod = build_fallback_module(["rain", "temp"], ["elev", "clay"])
        assert hasattr(mod, "rain_daily")
        assert hasattr(mod, "temp_daily")
        assert hasattr(mod, "elev")
        assert hasattr(mod, "clay")
