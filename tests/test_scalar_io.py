"""Tests for single-point JSON/TOML I/O."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from catena.config import IOSpec
from catena.formats import read_in_group, write_in_group
from catena.io import load_inputs
from catena.specs import SubsetSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


class TestLoadInputs:
    def test_static_dataarray_shape(self, static_json):
        path, _ = static_json
        specs = {
            "static": IOSpec(
                path=str(path), vars=["elevation", "land_cover"], suffix=""
            )
        }
        da = load_inputs(specs)["elevation"]
        assert da.dims == ("pixel",)
        assert da.shape == (1,)


# ---------------------------------------------------------------------------
# point_dim: the synthetic single-point axis is named, not hardcoded
# ---------------------------------------------------------------------------


class TestPointDim:
    """``point_dim`` names the size-1 axis given to scalar inputs.

    It must match whatever the pipeline blocks/subsets over: ``subset_inputs``
    passes over any input lacking the configured dim, so a mismatch would silently
    skip these inputs and leave a phantom axis in the outputs.
    """

    def test_json_uses_point_dim(self, static_json):
        path, _ = static_json
        ds = read_in_group(path, "scalar", point_dim="location")
        assert ds["elevation"].dims == ("location",)
        assert "pixel" not in ds.dims

    def test_toml_uses_point_dim(self, static_toml):
        path, _ = static_toml
        ds = read_in_group(path, "scalar", point_dim="location")
        assert ds["elevation"].dims == ("location",)

    def test_defaults_to_pixel(self, static_json):
        path, _ = static_json
        assert read_in_group(path, "scalar")["elevation"].dims == ("pixel",)

    def test_dataset_group_ignores_point_dim(self, tmp_path):
        # The uniform signature means netcdf/zarr accept it; they must not act on it.
        rng = np.random.default_rng(0)
        ds = xr.Dataset(
            {"v": (["time", "pixel"], rng.normal(size=(5, 1)))},
            coords={
                "time": pd.date_range("2020-01-01", periods=5, freq="D"),
                "pixel": [0],
            },
        )
        path = tmp_path / "d.nc"
        write_in_group(ds, path, "dataset")
        assert read_in_group(path, "dataset", point_dim="location")["v"].dims == (
            "time",
            "pixel",
        )

    def test_load_inputs_threads_point_dim(self, static_json):
        path, _ = static_json
        specs = {"static": IOSpec(path=str(path), vars=["elevation"], suffix="")}
        inputs = load_inputs(specs, point_dim="location")
        assert inputs["elevation"].dims == ("location",)

    def test_subset_applies_over_point_dim(self, static_json):
        # The whole point: with the axis named "location", a [subset] over
        # "location" reaches the scalar input instead of skipping it.
        path, _ = static_json
        specs = {"static": IOSpec(path=str(path), vars=["elevation"], suffix="")}
        inputs = load_inputs(
            specs,
            subset_spec=SubsetSpec(start=0, stop=1, dim="location"),
            point_dim="location",
        )
        assert inputs["elevation"].sizes["location"] == 1
