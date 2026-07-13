"""Tests for io.py paths not covered by existing tests.

Covers:
- load_dataset / _save_netcdf with Zarr files
- time-dimension detection (``time_dims``) and the single-time-dim invariant
- get_outputs and save_outputs public API
- Multiple-CRS-dataset lat/lon computation
"""

import importlib.util

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from conduit.config import IOSpec
from conduit.io import (
    _save_netcdf,
    get_final_vars,
    get_outputs,
    load_dataset,
    load_inputs,
    save_outputs,
    sole_time_dim,
    time_dims,
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


def _simple_ds(times=DAILY_TIMES, n_pixels=N_PIXELS):
    return xr.Dataset(
        {"var_a": (["time", "pixel"], RNG.random((len(times), n_pixels)))},
        coords={"time": times, "pixel": np.arange(n_pixels)},
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
# Section labels are inert
# ---------------------------------------------------------------------------


class TestSectionLabelsAreInert:
    """A section's label names its nodes and does nothing else.

    ``load_inputs`` emits data variables only — no ``dates_{label}`` index, no
    frequency inference. Frequency validation is opt-in via a consumer's ``Freq``
    declaration (see tests/test_freq.py), so a section labelled ``daily`` carrying
    weekly or irregular timestamps is loaded without complaint.
    """

    def _spec(self, tmp_path, times, label):
        path = tmp_path / f"{label}.nc"
        _simple_ds(times).to_netcdf(path)
        return {label: IOSpec(path=str(path), vars=["var_a"])}

    @pytest.mark.parametrize(
        ("label", "times"),
        [
            ("daily", DAILY_TIMES),
            ("weekly", WEEKLY_TIMES),
            ("monthly", MONTHLY_TIMES),
            ("arbitrary", DAILY_TIMES),
        ],
    )
    def test_only_data_vars_are_emitted(self, tmp_path, label, times):
        inputs = load_inputs(self._spec(tmp_path, times, label))
        assert set(inputs) == {f"var_a_{label}"}

    def test_label_frequency_not_enforced(self, tmp_path):
        # A section called "daily" holding weekly timestamps: not an error.
        inputs = load_inputs(self._spec(tmp_path, WEEKLY_TIMES, "daily"))
        assert inputs["var_a_daily"].sizes["time"] == N_TIMES

    def test_irregular_times_accepted(self, tmp_path):
        times = pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-10"])
        inputs = load_inputs(self._spec(tmp_path, times, "daily"))
        assert inputs["var_a_daily"].sizes["time"] == 3


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

    def test_bare_names_via_empty_suffix(self, tmp_path):
        specs = {
            "static": IOSpec(path=str(tmp_path / "s.nc"), vars=["elevation"], suffix="")
        }
        assert get_final_vars(specs) == ["elevation"]

    def test_bare_section_mixed_with_temporal(self, tmp_path):
        specs = {
            "daily": IOSpec(path=str(tmp_path / "d.nc"), vars=["gpp"]),
            "static": IOSpec(
                path=str(tmp_path / "s.nc"), vars=["elevation", "clay"], suffix=""
            ),
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
# vars: omitted means "load everything"
# ---------------------------------------------------------------------------


class TestOmittedVars:
    """An input section with no ``vars`` binds every variable in the file."""

    def test_input_section_without_vars_loads_all(self, synthetic_data_dir):
        from synthetic_data import DAILY_VARS

        inputs = load_inputs(
            {"daily": IOSpec(path=str(synthetic_data_dir / "daily.nc"))}
        )
        # Every file variable is bound, through the section's suffix.
        for var in DAILY_VARS:
            assert f"{var}_daily" in inputs

    def test_omitted_vars_honours_an_explicit_suffix(self, synthetic_data_dir):
        from synthetic_data import STATIC_VARS

        inputs = load_inputs(
            {"static": IOSpec(path=str(synthetic_data_dir / "static.nc"), suffix="")}
        )
        for var in STATIC_VARS:
            assert var in inputs


# ---------------------------------------------------------------------------
# Single time-dimension invariant
# ---------------------------------------------------------------------------


class TestSingleTimeDim:
    """load_inputs enforces at most one time dimension per input dataset."""

    def test_time_dims_detects_datetime_dimension(self):
        ds = _simple_ds()  # dims (time, pixel), only `time` is datetime
        assert time_dims(ds) == ["time"]

    def test_time_dims_ignores_non_datetime_dims(self):
        ds = xr.Dataset(
            {"x": (("band",), np.arange(3))}, coords={"band": ["r", "g", "b"]}
        )
        assert time_dims(ds) == []

    def test_time_dims_accepts_a_dataarray(self):
        assert time_dims(_simple_ds()["var_a"]) == ["time"]

    def test_time_dims_detects_a_cftime_axis(self):
        # A non-standard calendar gives a CFTimeIndex, not datetime64 — the second
        # limb of the detector, and the one no other test exercises.
        times = xr.date_range(
            "2020-01-01", periods=5, freq="D", calendar="noleap", use_cftime=True
        )
        ds = xr.Dataset(
            {"var_a": (("time",), np.zeros(5))},
            coords={"time": times},
        )
        assert not np.issubdtype(ds.time.dtype, np.datetime64)  # not the first limb
        assert time_dims(ds) == ["time"]
        assert sole_time_dim(ds, "ds") == "time"

    def test_sole_time_dim_returns_the_one_axis(self):
        assert sole_time_dim(_simple_ds(), "ds") == "time"

    def test_sole_time_dim_raises_without_a_time_axis(self):
        ds = xr.Dataset(
            {"x": (("band",), np.arange(3))}, coords={"band": ["r", "g", "b"]}
        )
        with pytest.raises(ValueError, match="has no time dimension"):
            sole_time_dim(ds, "ds")

    def test_sole_time_dim_raises_on_ambiguity(self):
        ds = xr.Dataset(
            {"f": (("time", "lead_time"), np.zeros((4, 3)))},
            coords={
                "time": pd.date_range("2020-01-01", periods=4, freq="D"),
                "lead_time": pd.date_range("2020-06-01", periods=3, freq="D"),
            },
        )
        with pytest.raises(ValueError, match="multiple time dimensions"):
            sole_time_dim(ds, "ds")

    def test_two_time_dims_raises(self, tmp_path):
        # A cube with two datetime axes (e.g. observation time + forecast lead time).
        t1 = pd.date_range("2020-01-01", periods=4, freq="D")
        t2 = pd.date_range("2020-06-01", periods=3, freq="D")
        ds = xr.Dataset(
            {"forecast": (("time", "lead_time"), np.zeros((4, 3)))},
            coords={"time": t1, "lead_time": t2},
        )
        path = tmp_path / "two_time.nc"
        ds.to_netcdf(path, engine="netcdf4")
        specs = {"fc": IOSpec(path=str(path), vars=["forecast"])}
        with pytest.raises(ValueError, match="multiple time dimensions"):
            load_inputs(specs)
