"""Tests for single-point CSV/Parquet/JSON/TOML I/O modules."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from conduit.config import IOSpec
from conduit.io import (
    dataset_to_dataframe,
    load_inputs,
    load_static,
    load_timeseries,
    save_timeseries,
)

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
# load_timeseries
# ---------------------------------------------------------------------------


class TestLoadTimeseries:
    def test_csv_shape(self, daily_csv):
        path, _df = daily_csv
        ds = load_timeseries(path)
        assert ds.sizes == {"time": N_DAYS, "pixel": 1}

    def test_csv_dim_order(self, daily_csv):
        path, _ = daily_csv
        ds = load_timeseries(path)
        for var in ds.data_vars:
            assert ds[var].dims == ("time", "pixel")

    def test_csv_pixel_coord(self, daily_csv):
        path, _ = daily_csv
        ds = load_timeseries(path)
        assert list(ds.coords["pixel"].values) == [0]

    def test_csv_time_is_datetimeindex(self, daily_csv):
        path, _ = daily_csv
        ds = load_timeseries(path)
        assert isinstance(ds.indexes["time"], pd.DatetimeIndex)

    def test_csv_values_preserved(self, daily_csv):
        path, df = daily_csv
        ds = load_timeseries(path)
        np.testing.assert_allclose(
            ds["temperature"].values[:, 0], df["temperature"].values
        )

    def test_parquet_shape(self, daily_parquet):
        path, _df = daily_parquet
        ds = load_timeseries(path)
        assert ds.sizes == {"time": N_DAYS, "pixel": 1}

    def test_parquet_values_preserved(self, daily_parquet):
        path, df = daily_parquet
        ds = load_timeseries(path)
        np.testing.assert_allclose(
            ds["precipitation"].values[:, 0], df["precipitation"].values
        )

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "data.nc"
        path.touch()
        with pytest.raises(ValueError, match="Unsupported format"):
            load_timeseries(path)

    def test_time_column_not_named_time(self, tmp_path):
        """CSV where the index column has a non-standard name is handled."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        df = pd.DataFrame({"val": range(5)}, index=pd.Index(times, name="date"))
        path = tmp_path / "odd_name.csv"
        df.to_csv(path)
        ds = load_timeseries(path)
        assert "time" in ds.sizes

    def test_time_as_column_not_index(self, tmp_path):
        """CSV where 'time' is a regular column (not the index) is handled."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        df = pd.DataFrame({"time": times, "val": range(5)})
        path = tmp_path / "time_col.csv"
        df.to_csv(path, index=False)
        ds = load_timeseries(path)
        assert "time" in ds.sizes
        assert ds.sizes["time"] == 5


# ---------------------------------------------------------------------------
# load_static
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
        self._check_static_ds(load_static(path), data)

    def test_toml(self, static_toml):
        path, data = static_toml
        self._check_static_ds(load_static(path), data)

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "data.nc"
        path.touch()
        with pytest.raises(ValueError, match="Unsupported format"):
            load_static(path)


# ---------------------------------------------------------------------------
# dataset_to_dataframe
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
        df = dataset_to_dataframe(ds)
        assert "pixel" not in df.columns
        assert df.index.name == "time"

    def test_shape(self):
        ds = self._make_output_ds()
        df = dataset_to_dataframe(ds)
        assert df.shape == (N_DAYS, 1)

    def test_values_preserved(self):
        ds = self._make_output_ds()
        original = ds["gpp"].values[:, 0]
        df = dataset_to_dataframe(ds)
        np.testing.assert_allclose(np.asarray(df["gpp"].values), original)

    def test_no_pixel_dim_passes_through(self):
        """Dataset without a pixel dim is handled gracefully."""
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        ds = xr.Dataset(
            {"x": xr.DataArray(np.ones(5), dims=["time"], coords={"time": times})}
        )
        df = dataset_to_dataframe(ds)
        assert df.shape == (5, 1)

    def test_jax_arrays_materialise(self):
        jnp = pytest.importorskip("jax.numpy")
        times = pd.date_range("2020-01-01", periods=5, freq="D")
        jax_data = jnp.ones((5, 1))
        da = xr.DataArray(
            jax_data, dims=["time", "pixel"], coords={"time": times, "pixel": [0]}
        )
        ds = xr.Dataset({"x": da})
        df = dataset_to_dataframe(ds)
        assert isinstance(df["x"].values, np.ndarray)


# ---------------------------------------------------------------------------
# save_timeseries
# ---------------------------------------------------------------------------


class TestSaveTimeseries:
    def _make_df(self) -> pd.DataFrame:
        times = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
        return pd.DataFrame({"gpp": RNG.normal(size=N_DAYS)}, index=times)

    def test_csv_roundtrip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "out.csv"
        save_timeseries(df, path)
        reloaded = pd.read_csv(path, index_col=0, parse_dates=True)
        np.testing.assert_allclose(
            np.asarray(reloaded["gpp"].values), np.asarray(df["gpp"].values)
        )

    def test_parquet_roundtrip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "out.parquet"
        save_timeseries(df, path)
        reloaded = pd.read_parquet(path)
        np.testing.assert_allclose(
            np.asarray(reloaded["gpp"].values), np.asarray(df["gpp"].values)
        )

    def test_unsupported_extension_raises(self, tmp_path):
        df = self._make_df()
        with pytest.raises(ValueError, match="Unsupported format"):
            save_timeseries(df, tmp_path / "out.nc")


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

    def test_dates_daily_present(self, sp_inputs):
        idx = sp_inputs["dates_daily"]
        assert isinstance(idx, pd.DatetimeIndex)
        assert len(idx) == N_DAYS


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
        df = dataset_to_dataframe(ds)
        save_timeseries(df, out_path)

        reloaded = pd.read_csv(out_path, index_col=0, parse_dates=True)
        np.testing.assert_allclose(np.asarray(reloaded["gpp"].values), original[:, 0])
