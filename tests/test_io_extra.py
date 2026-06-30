"""Tests for io.py paths not covered by existing tests.

Covers:
- load_dataset / _save_netcdf with Zarr files
- _validate_dates error paths
- get_outputs and save_outputs public API
- Multiple-CRS-dataset lat/lon computation
"""

import importlib.util

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from breadboard.config import IOSpec
from breadboard.io import (
    _save_netcdf,
    _validate_dates,
    _validate_temporal_alignment,
    get_final_vars,
    get_outputs,
    load_dataset,
    save_outputs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

N_TIMES = 10
N_PIXELS = 3

DAILY_TIMES = pd.date_range("2020-01-01", periods=N_TIMES, freq="D")
WEEKLY_TIMES = pd.date_range("2020-01-01", periods=N_TIMES, freq="7D")
MONTHLY_TIMES = pd.date_range("2020-01-01", periods=N_TIMES, freq="ME")
RNG = np.random.default_rng(0)

# Constants for cross-frequency alignment tests
DAILY_YEAR = pd.date_range("2020-01-01", periods=365, freq="D")
WEEKLY_ALIGNED = pd.date_range("2020-01-01", periods=52, freq="7D")
WEEKLY_PARTIAL = pd.date_range(
    "2020-01-08", periods=4, freq="7D"
)  # subset of WEEKLY_ALIGNED
WEEKLY_WRONG_DAY = pd.date_range(
    "2020-01-03", periods=5, freq="7D"
)  # Friday start, not on 7D grid from Jan 1
MONTHLY_ALIGNED = pd.date_range("2020-01-31", periods=12, freq="ME")  # month-end labels
MONTHLY_WRONG = pd.date_range("2020-01-01", periods=12, freq="MS")  # month-start labels


def _simple_ds(times=DAILY_TIMES, n_pixels=N_PIXELS):
    return xr.Dataset(
        {"var_a": (["time", "pixel"], RNG.random((len(times), n_pixels)))},
        coords={"time": times, "pixel": np.arange(n_pixels)},
    )


def _static_da(values):
    return xr.DataArray(
        values, dims=["pixel"], coords={"pixel": np.arange(len(values))}
    )


# ---------------------------------------------------------------------------
# Zarr I/O
# ---------------------------------------------------------------------------


_HAS_ZARR = importlib.util.find_spec("zarr") is not None


@pytest.mark.skipif(not _HAS_ZARR, reason="zarr not installed")
class TestZarrDataset:
    """load_dataset and _save_netcdf support Zarr files."""

    def test_save_and_load_zarr(self, tmp_path):
        ds = _simple_ds()
        zarr_path = tmp_path / "data.zarr"
        _save_netcdf(ds, zarr_path)
        loaded = load_dataset(zarr_path)
        assert set(loaded.data_vars) == {"var_a"}

    def test_zarr_round_trip_values(self, tmp_path):
        ds = _simple_ds()
        zarr_path = tmp_path / "data.zarr"
        _save_netcdf(ds, zarr_path)
        loaded = load_dataset(zarr_path)
        np.testing.assert_allclose(loaded["var_a"].values, ds["var_a"].values)

    def test_zarr_time_dimension_preserved(self, tmp_path):
        ds = _simple_ds()
        zarr_path = tmp_path / "data.zarr"
        _save_netcdf(ds, zarr_path)
        loaded = load_dataset(zarr_path)
        assert "time" in loaded.dims
        assert loaded.sizes["time"] == N_TIMES


class TestSaveNetcdfErrors:
    """_save_netcdf raises for unsupported extensions."""

    def test_unsupported_extension_raises(self, tmp_path):
        ds = _simple_ds()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            _save_netcdf(ds, tmp_path / "data.csv")

    def test_load_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "data.txt"
        p.touch()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            load_dataset(p)


# ---------------------------------------------------------------------------
# _validate_dates error paths
# ---------------------------------------------------------------------------


class TestValidateDatesErrors:
    """_validate_dates raises for non-DatetimeIndex and wrong frequency."""

    def test_frequency_mismatch_raises(self):
        hourly = pd.date_range("2020-01-01", periods=24, freq="h")
        ds = xr.Dataset(
            {"x": (["time"], np.ones(24))},
            coords={"time": hourly},
        )
        with pytest.raises(ValueError, match="Expected 'daily'"):
            _validate_dates(ds, "daily")

    def test_wrong_freq_for_monthly(self):
        daily = pd.date_range("2020-01-01", periods=30, freq="D")
        ds = xr.Dataset(
            {"x": (["time"], np.ones(30))},
            coords={"time": daily},
        )
        with pytest.raises(ValueError, match="Expected 'monthly'"):
            _validate_dates(ds, "monthly")

    def test_irregular_times_raises(self):
        # Irregular timestamps — pd.infer_freq returns None
        times = pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-10"])
        ds = xr.Dataset(
            {"x": (["time"], np.ones(3))},
            coords={"time": times},
        )
        with pytest.raises(ValueError, match="Could not determine frequency"):
            _validate_dates(ds, "daily")

    def test_daily_passes(self):
        ds = xr.Dataset(
            {"x": (["time"], np.ones(N_TIMES))},
            coords={"time": DAILY_TIMES},
        )
        idx = _validate_dates(ds, "daily")
        assert isinstance(idx, pd.DatetimeIndex)

    def test_weekly_passes(self):
        ds = xr.Dataset(
            {"x": (["time"], np.ones(N_TIMES))},
            coords={"time": WEEKLY_TIMES},
        )
        idx = _validate_dates(ds, "weekly")
        assert isinstance(idx, pd.DatetimeIndex)

    def test_monthly_passes(self):
        ds = xr.Dataset(
            {"x": (["time"], np.ones(N_TIMES))},
            coords={"time": MONTHLY_TIMES},
        )
        idx = _validate_dates(ds, "monthly")
        assert isinstance(idx, pd.DatetimeIndex)


# ---------------------------------------------------------------------------
# get_outputs
# ---------------------------------------------------------------------------


class TestGetOutputs:
    """get_outputs merges model result DataArrays into per-frequency Datasets."""

    @pytest.fixture
    def daily_results(self):
        times = DAILY_TIMES
        pixel = np.arange(N_PIXELS)
        return {
            "gpp_daily": xr.DataArray(
                RNG.random((N_TIMES, N_PIXELS)),
                dims=["time", "pixel"],
                coords={"time": times, "pixel": pixel},
                name="gpp",
            ),
            "aet_daily": xr.DataArray(
                RNG.random((N_TIMES, N_PIXELS)),
                dims=["time", "pixel"],
                coords={"time": times, "pixel": pixel},
                name="aet",
            ),
        }

    @pytest.fixture
    def output_specs(self, tmp_path):
        return {
            "daily": IOSpec(
                path=str(tmp_path / "out_daily.nc"),
                vars=["gpp", "aet"],
            )
        }

    def test_returns_dict(self, daily_results, output_specs):
        result = get_outputs(daily_results, output_specs)
        assert isinstance(result, dict)

    def test_output_has_expected_freq_key(self, daily_results, output_specs):
        result = get_outputs(daily_results, output_specs)
        assert "daily" in result

    def test_output_is_dataset(self, daily_results, output_specs):
        result = get_outputs(daily_results, output_specs)
        assert isinstance(result["daily"], xr.Dataset)

    def test_output_contains_expected_vars(self, daily_results, output_specs):
        result = get_outputs(daily_results, output_specs)
        ds = result["daily"]
        assert "gpp" in ds.data_vars
        assert "aet" in ds.data_vars

    def test_values_preserved(self, daily_results, output_specs):
        result = get_outputs(daily_results, output_specs)
        np.testing.assert_allclose(
            result["daily"]["gpp"].values,
            daily_results["gpp_daily"].values,
        )


# ---------------------------------------------------------------------------
# get_final_vars
# ---------------------------------------------------------------------------


class TestGetFinalVars:
    """get_final_vars converts output_specs into Hamilton node name lists."""

    def test_empty_specs_returns_empty_list(self):
        assert get_final_vars({}) == []

    def test_single_freq_single_var(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "d.nc"), vars=["gpp"])}
        assert get_final_vars(specs) == ["gpp_daily"]

    def test_single_freq_multiple_vars(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "d.nc"), vars=["gpp", "aet"])}
        assert get_final_vars(specs) == ["gpp_daily", "aet_daily"]

    def test_multiple_frequencies(self, tmp_path):
        specs = {
            "daily": IOSpec(path=str(tmp_path / "d.nc"), vars=["gpp"]),
            "weekly": IOSpec(path=str(tmp_path / "w.nc"), vars=["leaf_pool"]),
            "monthly": IOSpec(path=str(tmp_path / "m.nc"), vars=["soc"]),
        }
        assert get_final_vars(specs) == [
            "gpp_daily",
            "leaf_pool_weekly",
            "soc_monthly",
        ]

    def test_static_no_suffix(self, tmp_path):
        specs = {"static": IOSpec(path=str(tmp_path / "s.nc"), vars=["elevation"])}
        assert get_final_vars(specs) == ["elevation"]

    def test_static_mixed_with_temporal(self, tmp_path):
        specs = {
            "daily": IOSpec(path=str(tmp_path / "d.nc"), vars=["gpp"]),
            "static": IOSpec(path=str(tmp_path / "s.nc"), vars=["elevation", "clay"]),
        }
        result = get_final_vars(specs)
        assert result == ["gpp_daily", "elevation", "clay"]
        assert all("_static" not in v for v in result)


# ---------------------------------------------------------------------------
# save_outputs
# ---------------------------------------------------------------------------


class TestSaveOutputs:
    """save_outputs writes per-frequency Datasets to disk."""

    @pytest.fixture
    def daily_dataset(self):
        times = DAILY_TIMES
        pixel = np.arange(N_PIXELS)
        da = xr.DataArray(
            RNG.random((N_TIMES, N_PIXELS)),
            dims=["time", "pixel"],
            coords={"time": times, "pixel": pixel},
        )
        return xr.Dataset({"gpp": da})

    def test_saves_netcdf(self, tmp_path, daily_dataset):
        out_path = tmp_path / "out.nc"
        output_specs = {"daily": IOSpec(path=str(out_path), vars=["gpp"])}
        save_outputs({"daily": daily_dataset}, output_specs)
        assert out_path.exists()

    def test_saved_netcdf_loadable(self, tmp_path, daily_dataset):
        out_path = tmp_path / "out.nc"
        output_specs = {"daily": IOSpec(path=str(out_path), vars=["gpp"])}
        save_outputs({"daily": daily_dataset}, output_specs)
        loaded = xr.open_dataset(out_path)
        assert "gpp" in loaded.data_vars

    def test_saves_csv_for_non_gridded(self, tmp_path):
        times = DAILY_TIMES
        pixel = [0]
        da = xr.DataArray(
            RNG.random((N_TIMES, 1)),
            dims=["time", "pixel"],
            coords={"time": times, "pixel": pixel},
        )
        ds = xr.Dataset({"gpp": da})
        out_path = tmp_path / "out.csv"
        output_specs = {"daily": IOSpec(path=str(out_path), vars=["gpp"])}
        save_outputs({"daily": ds}, output_specs)
        assert out_path.exists()


# ---------------------------------------------------------------------------
# _validate_temporal_alignment
# ---------------------------------------------------------------------------


class TestValidateTemporalAlignment:
    """_validate_temporal_alignment checks coarser dates ⊆ expected resample labels."""

    def test_aligned_daily_weekly_passes(self):
        _validate_temporal_alignment({"daily": DAILY_YEAR, "weekly": WEEKLY_ALIGNED})

    def test_aligned_daily_monthly_passes(self):
        _validate_temporal_alignment({"daily": DAILY_YEAR, "monthly": MONTHLY_ALIGNED})

    def test_aligned_weekly_monthly_passes(self):
        weekly = pd.date_range("2020-01-01", periods=52, freq="7D")
        monthly = pd.date_range("2020-01-31", periods=12, freq="ME")
        _validate_temporal_alignment({"weekly": weekly, "monthly": monthly})

    def test_only_daily_no_check(self):
        _validate_temporal_alignment({"daily": DAILY_YEAR})

    def test_only_monthly_no_check(self):
        _validate_temporal_alignment({"monthly": MONTHLY_ALIGNED})

    def test_empty_no_check(self):
        _validate_temporal_alignment({})

    def test_partial_subset_passes(self):
        # Coarse data covering only part of the fine date range is valid
        _validate_temporal_alignment({"daily": DAILY_YEAR, "weekly": WEEKLY_PARTIAL})

    def test_wrong_weekday_raises(self):
        with pytest.raises(ValueError, match="Temporal alignment check failed"):
            _validate_temporal_alignment(
                {"daily": DAILY_YEAR, "weekly": WEEKLY_WRONG_DAY}
            )

    def test_wrong_month_convention_raises(self):
        with pytest.raises(ValueError, match="Temporal alignment check failed"):
            _validate_temporal_alignment(
                {"daily": DAILY_YEAR, "monthly": MONTHLY_WRONG}
            )

    def test_coarse_outside_fine_range_raises(self):
        weekly_outside = pd.date_range("2022-01-01", periods=5, freq="7D")
        with pytest.raises(ValueError, match="Temporal alignment check failed"):
            _validate_temporal_alignment(
                {"daily": DAILY_YEAR, "weekly": weekly_outside}
            )

    def test_error_message_names_frequencies(self):
        with pytest.raises(ValueError, match="'daily' → 'weekly'"):
            _validate_temporal_alignment(
                {"daily": DAILY_YEAR, "weekly": WEEKLY_WRONG_DAY}
            )
