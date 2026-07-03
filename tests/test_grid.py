"""
Tests for grid (lat/lon) computation in load_inputs().

The grid computation previously lived in pipeline/grid.py as Hamilton nodes.
It now lives inside load_inputs() as plain function calls, using
_compute_lat_lon() and _check_common_grid() from conduit.io.
"""

import numpy as np
import pytest

from conduit.config import IOSpec
from conduit.gridded.io import MisalignedGridError, _check_common_grid
from conduit.io import load_inputs


class TestCheckCommonGrid:
    """Tests for _check_common_grid()."""

    def test_identical_datasets_pass(self, daily_ds, static_ds):
        _check_common_grid(daily_ds, static_ds)

    def test_mismatched_crs_raises(self, daily_ds):
        ds2 = daily_ds.copy()
        ds2 = ds2.assign_attrs({"crs": "EPSG:4327"})
        with pytest.raises(MisalignedGridError, match="Mismatched CRS"):
            _check_common_grid(daily_ds, ds2)

    def test_labels_appear_in_error(self, daily_ds):
        ds2 = daily_ds.copy()
        ds2 = ds2.assign_attrs({"crs": "EPSG:4327"})
        with pytest.raises(MisalignedGridError, match="daily"):
            _check_common_grid(daily_ds, ds2, label1="daily", label2="other")


class TestLoadInputsGrid:
    """Test that load_inputs() computes latitude and longitude when CRS data is present."""

    def test_latitude_present(self, pipeline_inputs):
        assert "latitude" in pipeline_inputs

    def test_longitude_present(self, pipeline_inputs):
        assert "longitude" in pipeline_inputs

    def test_latitude_in_uk_bounds(self, pipeline_inputs):
        lat = pipeline_inputs["latitude"].values
        assert np.all(lat >= 49.0)
        assert np.all(lat <= 55.0)

    def test_longitude_in_uk_bounds(self, pipeline_inputs):
        lon = pipeline_inputs["longitude"].values
        assert np.all(lon >= -5.0)
        assert np.all(lon <= 3.0)

    def test_pixel_count(self, pipeline_inputs):
        assert pipeline_inputs["latitude"].sizes["pixel"] == 4  # 2x2 grid
        assert pipeline_inputs["longitude"].sizes["pixel"] == 4

    def test_no_nan_in_lat(self, pipeline_inputs):
        assert not np.any(np.isnan(pipeline_inputs["latitude"].values))

    def test_no_nan_in_lon(self, pipeline_inputs):
        assert not np.any(np.isnan(pipeline_inputs["longitude"].values))


class TestLoadInputsNoGrid:
    """Test that load_inputs() omits lat/lon when there is no CRS data."""

    def test_no_grid_without_crs(self, tmp_path):
        import pandas as pd

        times = pd.date_range("2020-01-01", periods=5, freq="D")
        df = pd.DataFrame({"temp": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=times)
        df.index.name = "time"
        csv_path = tmp_path / "daily.csv"
        df.to_csv(csv_path)

        specs = {"daily": IOSpec(path=str(csv_path), vars=["temp"])}
        inputs = load_inputs(specs)

        assert "latitude" not in inputs
        assert "longitude" not in inputs
        assert "temp_daily" in inputs
