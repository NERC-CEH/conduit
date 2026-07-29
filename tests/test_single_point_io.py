"""Tests for single-point CSV/Parquet/JSON/TOML I/O modules."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from conduit.config import IOSpec
from conduit.formats import (
    dataset_to_frame,
    read_in_group,
    write_frame,
    write_in_group,
)
from conduit.io import load_inputs, save_outputs
from conduit.specs import SubsetSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N_DAYS = 20
RNG = np.random.default_rng(0)


def _make_daily_df() -> pd.DataFrame:
    times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
    return pd.DataFrame(
        {
            "temperature": RNG.normal(10.0, 3.0, N_DAYS),
            "precipitation": np.abs(RNG.normal(2.0, 1.0, N_DAYS)),
        },
        index=pd.Index(times, name="time"),
    )


@pytest.fixture
def daily_csv(tmp_path) -> tuple[Path, pd.DataFrame]:
    df = _make_daily_df()
    path = tmp_path / "daily.csv"
    df.to_csv(path)
    return path, df


@pytest.fixture
def daily_parquet(tmp_path) -> tuple[Path, pd.DataFrame]:
    df = _make_daily_df()
    path = tmp_path / "daily.parquet"
    df.to_parquet(path)
    return path, df


@pytest.fixture
def static_json(tmp_path) -> tuple[Path, dict]:
    data = {"elevation": 150.0, "land_cover": 3.0}
    path = tmp_path / "static.json"
    path.write_text(json.dumps(data))
    return path, data


@pytest.fixture
def static_toml(tmp_path) -> tuple[Path, dict]:
    data = {"elevation": 150.0, "land_cover": 3.0}
    path = tmp_path / "static.toml"
    path.write_text("elevation = 150.0\nland_cover = 3.0\n")
    return path, data


# ---------------------------------------------------------------------------
# read_in_group(..., 'table')
# ---------------------------------------------------------------------------


class TestLoadTimeseries:
    def test_csv_shape(self, daily_csv):
        path, _df = daily_csv
        ds = read_in_group(path, "table")
        assert ds.sizes == {"time": N_DAYS, "pixel": 1}

    def test_csv_dim_order(self, daily_csv):
        path, _ = daily_csv
        ds = read_in_group(path, "table")
        for var in ds.data_vars:
            assert ds[var].dims == ("time", "pixel")

    def test_csv_pixel_coord(self, daily_csv):
        path, _ = daily_csv
        ds = read_in_group(path, "table")
        assert list(ds.coords["pixel"].values) == [0]

    def test_csv_time_is_datetimeindex(self, daily_csv):
        path, _ = daily_csv
        ds = read_in_group(path, "table")
        assert isinstance(ds.indexes["time"], pd.DatetimeIndex)

    def test_csv_values_preserved(self, daily_csv):
        path, df = daily_csv
        ds = read_in_group(path, "table")
        np.testing.assert_allclose(
            ds["temperature"].values[:, 0], df["temperature"].values
        )

    def test_parquet_shape(self, daily_parquet):
        path, _df = daily_parquet
        ds = read_in_group(path, "table")
        assert ds.sizes == {"time": N_DAYS, "pixel": 1}

    def test_parquet_values_preserved(self, daily_parquet):
        path, df = daily_parquet
        ds = read_in_group(path, "table")
        np.testing.assert_allclose(
            ds["precipitation"].values[:, 0], df["precipitation"].values
        )

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "data.nc"
        path.touch()
        with pytest.raises(ValueError, match="for a table file"):
            read_in_group(path, "table")

    def test_time_column_not_named_time(self, tmp_path):
        """CSV where the index column has a non-standard name is handled."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        df = pd.DataFrame({"val": range(5)}, index=pd.Index(times, name="date"))
        path = tmp_path / "odd_name.csv"
        df.to_csv(path)
        ds = read_in_group(path, "table")
        assert "time" in ds.sizes

    def test_time_as_column_not_index(self, tmp_path):
        """CSV where 'time' is a regular column (not the index) is handled."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        df = pd.DataFrame({"time": times, "val": range(5)})
        path = tmp_path / "time_col.csv"
        df.to_csv(path, index=False)
        ds = read_in_group(path, "table")
        assert "time" in ds.sizes
        assert ds.sizes["time"] == 5


# ---------------------------------------------------------------------------
# read_in_group(..., 'scalar')
# ---------------------------------------------------------------------------


class TestLoadStatic:
    def _check_static_ds(self, ds: xr.Dataset, expected: dict):
        assert ds.sizes == {"pixel": 1}
        for k, v in expected.items():
            assert k in ds.data_vars
            np.testing.assert_allclose(ds[k].values, [v])
        assert list(ds.coords["pixel"].values) == [0]

    def test_json(self, static_json):
        path, data = static_json
        self._check_static_ds(read_in_group(path, "scalar"), data)

    def test_toml(self, static_toml):
        path, data = static_toml
        self._check_static_ds(read_in_group(path, "scalar"), data)

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "data.nc"
        path.touch()
        with pytest.raises(ValueError, match="for a scalar file"):
            read_in_group(path, "scalar")


# ---------------------------------------------------------------------------
# dataset_to_frame
# ---------------------------------------------------------------------------


class TestDatasetToDataframe:
    def _make_output_ds(self) -> xr.Dataset:
        times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
        data = RNG.normal(size=(N_DAYS, 1))
        da = xr.DataArray(
            data, dims=["time", "pixel"], coords={"time": times, "pixel": [0]}
        )
        return xr.Dataset({"gpp": da})

    def test_squeezes_pixel(self):
        ds = self._make_output_ds()
        df = dataset_to_frame(ds)
        assert "pixel" not in df.columns
        assert df.index.name == "time"

    def test_shape(self):
        ds = self._make_output_ds()
        df = dataset_to_frame(ds)
        assert df.shape == (N_DAYS, 1)

    def test_values_preserved(self):
        ds = self._make_output_ds()
        original = ds["gpp"].values[:, 0]
        df = dataset_to_frame(ds)
        np.testing.assert_allclose(np.asarray(df["gpp"].values), original)

    def test_no_pixel_dim_passes_through(self):
        """Dataset without a pixel dim is handled gracefully."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        ds = xr.Dataset(
            {"x": xr.DataArray(np.ones(5), dims=["time"], coords={"time": times})}
        )
        df = dataset_to_frame(ds)
        assert df.shape == (5, 1)

    def test_jax_arrays_materialise(self):
        jnp = pytest.importorskip("jax.numpy")
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        jax_data = jnp.ones((5, 1))
        da = xr.DataArray(
            jax_data, dims=["time", "pixel"], coords={"time": times, "pixel": [0]}
        )
        ds = xr.Dataset({"x": da})
        df = dataset_to_frame(ds)
        assert isinstance(df["x"].values, np.ndarray)


# ---------------------------------------------------------------------------
# write_frame
# ---------------------------------------------------------------------------


class TestSaveTimeseries:
    def _make_df(self) -> pd.DataFrame:
        times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
        return pd.DataFrame({"gpp": RNG.normal(size=N_DAYS)}, index=times)

    def test_csv_roundtrip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "out.csv"
        write_frame(df, path)
        reloaded = pd.read_csv(path, index_col=0, parse_dates=True)
        np.testing.assert_allclose(
            np.asarray(reloaded["gpp"].values), np.asarray(df["gpp"].values)
        )

    def test_parquet_roundtrip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "out.parquet"
        write_frame(df, path)
        reloaded = pd.read_parquet(path)
        np.testing.assert_allclose(
            np.asarray(reloaded["gpp"].values), np.asarray(df["gpp"].values)
        )

    def test_unsupported_extension_raises(self, tmp_path):
        df = self._make_df()
        with pytest.raises(ValueError, match="for a table file"):
            write_frame(df, tmp_path / "out.nc")


# ---------------------------------------------------------------------------
# Hamilton node integration: input module produces correct shapes
# ---------------------------------------------------------------------------


class TestLoadInputs:
    """Test load_inputs() with flat (CSV/JSON) single-point data."""

    @pytest.fixture
    def sp_inputs(self, daily_csv, static_json):
        daily_path, _ = daily_csv
        static_path, _ = static_json
        specs = {
            "daily": IOSpec(
                path=str(daily_path),
                vars=["temperature", "precipitation"],
            ),
            "static": IOSpec(
                path=str(static_path), vars=["elevation", "land_cover"], suffix=""
            ),
        }
        return load_inputs(specs)

    def test_daily_dataarray_shape(self, sp_inputs):
        da = sp_inputs["temperature_daily"]
        assert da.dims == ("time", "pixel")
        assert da.shape == (N_DAYS, 1)

    def test_daily_dataarray_pixel_coord(self, sp_inputs):
        da = sp_inputs["precipitation_daily"]
        assert list(da.coords["pixel"].values) == [0]

    def test_static_dataarray_shape(self, sp_inputs):
        da = sp_inputs["elevation"]
        assert da.dims == ("pixel",)
        assert da.shape == (1,)

    def test_time_axis_length(self, sp_inputs):
        assert sp_inputs["temperature_daily"].sizes["time"] == N_DAYS


# ---------------------------------------------------------------------------
# End-to-end: inputs -> outputs round-trip (no models)
# ---------------------------------------------------------------------------


class TestOutputRoundtrip:
    """Write a synthetic output Dataset and verify CSV save/reload."""

    def test_daily_csv_roundtrip(self, tmp_path):
        times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
        original = RNG.normal(size=(N_DAYS, 1))
        da = xr.DataArray(
            original,
            dims=["time", "pixel"],
            coords={"time": times, "pixel": [0]},
            name="gpp",
        )
        ds = xr.Dataset({"gpp": da})

        out_path = tmp_path / "out_daily.csv"
        df = dataset_to_frame(ds)
        write_frame(df, out_path)

        reloaded = pd.read_csv(out_path, index_col=0, parse_dates=True)
        np.testing.assert_allclose(np.asarray(reloaded["gpp"].values), original[:, 0])


# ---------------------------------------------------------------------------
# point_dim: the synthetic single-point axis is named, not hardcoded
# ---------------------------------------------------------------------------


class TestPointDim:
    """``point_dim`` names the size-1 axis given to table/scalar inputs.

    It must match whatever the pipeline blocks/subsets over: ``subset_inputs``
    passes over any input lacking the configured dim, so a mismatch would silently
    skip these inputs and leave a phantom axis in the outputs.
    """

    def test_csv_uses_point_dim(self, daily_csv):
        path, _ = daily_csv
        ds = read_in_group(path, "table", point_dim="location")
        assert ds["temperature"].dims == ("time", "location")
        assert list(ds.coords["location"].values) == [0]
        assert "pixel" not in ds.dims

    def test_parquet_uses_point_dim(self, daily_parquet):
        path, _ = daily_parquet
        ds = read_in_group(path, "table", point_dim="location")
        assert ds["temperature"].dims == ("time", "location")

    def test_json_uses_point_dim(self, static_json):
        path, _ = static_json
        ds = read_in_group(path, "scalar", point_dim="location")
        assert ds["elevation"].dims == ("location",)
        assert "pixel" not in ds.dims

    def test_toml_uses_point_dim(self, static_toml):
        path, _ = static_toml
        ds = read_in_group(path, "scalar", point_dim="location")
        assert ds["elevation"].dims == ("location",)

    def test_defaults_to_pixel(self, daily_csv, static_json):
        csv_path, _ = daily_csv
        json_path, _ = static_json
        assert read_in_group(csv_path, "table")["temperature"].dims == (
            "time",
            "pixel",
        )
        assert read_in_group(json_path, "scalar")["elevation"].dims == ("pixel",)

    def test_dataset_group_ignores_point_dim(self, tmp_path):
        # The uniform signature means netcdf/zarr accept it; they must not act on it.
        ds = xr.Dataset(
            {"v": (["time", "pixel"], RNG.normal(size=(N_DAYS, 1)))},
            coords={
                "time": pd.date_range("2020-01-01", periods=N_DAYS, freq="D"),
                "pixel": [0],
            },
        )
        path = tmp_path / "d.nc"
        write_in_group(ds, path, "dataset", point_dim="location")
        assert read_in_group(path, "dataset", point_dim="location")["v"].dims == (
            "time",
            "pixel",
        )

    def test_load_inputs_threads_point_dim(self, daily_csv, static_json):
        csv_path, _ = daily_csv
        json_path, _ = static_json
        specs = {
            "daily": IOSpec(path=str(csv_path), vars=["temperature"]),
            "static": IOSpec(path=str(json_path), vars=["elevation"], suffix=""),
        }
        inputs = load_inputs(specs, point_dim="location")
        assert inputs["temperature_daily"].dims == ("time", "location")
        assert inputs["elevation"].dims == ("location",)

    def test_subset_applies_over_point_dim(self, daily_csv):
        # The whole point: with the axis named "location", a [subset] over
        # "location" reaches the table input instead of skipping it.
        csv_path, _ = daily_csv
        specs = {"daily": IOSpec(path=str(csv_path), vars=["temperature"])}
        inputs = load_inputs(
            specs,
            subset_spec=SubsetSpec(start=0, stop=1, dim="location"),
            point_dim="location",
        )
        assert inputs["temperature_daily"].sizes["location"] == 1

    def test_write_squeezes_point_dim(self, tmp_path):
        times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
        ds = xr.Dataset(
            {"gpp": (["time", "location"], RNG.normal(size=(N_DAYS, 1)))},
            coords={"time": times, "location": [0]},
        )
        out = tmp_path / "out.csv"
        save_outputs(
            {"daily": ds},
            {"daily": IOSpec(path=str(out), vars=["gpp"])},
            point_dim="location",
        )
        reloaded = pd.read_csv(out, index_col=0, parse_dates=True)
        assert list(reloaded.columns) == ["gpp"]
        assert len(reloaded) == N_DAYS
