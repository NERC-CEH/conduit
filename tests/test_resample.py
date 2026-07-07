"""Tests for the resample transform and the [[resample]] preset pipeline.

``[[resample]]`` is now a preset that desugars to fan-out passthrough ``[[node]]``
entries applying `conduit.transforms.resample`; there is no dedicated DAG module.
These tests cover the transform directly and end-to-end via a built driver.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from conduit.config import Config
from conduit.dag.driver import build_driver
from conduit.transforms import resample


def _daily_da(n_days: int = 14, n_pixel: int = 1, seed: int = 0) -> xr.DataArray:
    rng = np.random.default_rng(seed)
    return xr.DataArray(
        rng.standard_normal((n_days, n_pixel)),
        dims=("time", "pixel"),
        coords={
            "time": pd.date_range("2020-01-01", periods=n_days, freq="D"),
            "pixel": np.arange(n_pixel),
        },
    )


class TestResampleTransform:
    """The plain transform function `conduit.transforms.resample`."""

    def test_mean_values(self):
        da = _daily_da(14, 1)
        out = resample(da, freq="7D", aggfunc="mean")
        expected = da.isel(time=slice(0, 7)).mean("time").values
        np.testing.assert_allclose(out.isel(time=0).values, expected)

    def test_sum_values(self):
        da = _daily_da(14, 1)
        out = resample(da, freq="7D", aggfunc="sum")
        expected = da.isel(time=slice(0, 7)).sum("time").values
        np.testing.assert_allclose(out.isel(time=0).values, expected)

    def test_pixel_dimension_preserved(self):
        out = resample(_daily_da(365, 4), freq="7D")
        assert "pixel" in out.dims
        assert out.sizes["pixel"] == 4

    def test_units_attr_preserved(self):
        da = _daily_da(14, 1)
        da.attrs["units"] = "g m-2 d-1"
        out = resample(da, freq="1ME", aggfunc="mean")
        assert out.attrs["units"] == "g m-2 d-1"

    def test_monthly_frequency(self):
        out = resample(_daily_da(365, 1), freq="1ME")
        assert out.sizes["time"] == 12
        inferred = pd.infer_freq(out.coords["time"].values)
        assert inferred is not None
        assert inferred.startswith(("ME", "MS"))


class TestResamplePresetPipeline:
    """[[resample]] desugars to a passthrough node; the built driver executes it."""

    def _driver(self, entry: dict):
        parsed = Config({"resample": [entry]}).parse()
        assert parsed.modules == ["node"]  # no dedicated resample module
        return build_driver(parsed.modules, parsed.driver_config)

    def test_default_direction_offset(self):
        dr = self._driver(
            {"vars": ["temperature"], "from_freq": "daily", "to_freq": "weekly"}
        )
        da = _daily_da(14, 1)
        out = dr.execute(["temperature_weekly"], inputs={"temperature_daily": da})[
            "temperature_weekly"
        ]
        expected = da.isel(time=slice(0, 7)).mean("time").values
        np.testing.assert_allclose(out.isel(time=0).values, expected)

    def test_explicit_freq_overrides_default(self):
        dr = self._driver(
            {
                "vars": ["temperature"],
                "from_freq": "daily",
                "to_freq": "custom",
                "freq": "1ME",
            }
        )
        out = dr.execute(
            ["temperature_custom"], inputs={"temperature_daily": _daily_da(365, 1)}
        )["temperature_custom"]
        assert out.sizes["time"] == 12

    def test_aggfunc_sum(self):
        dr = self._driver(
            {
                "vars": ["precip"],
                "from_freq": "daily",
                "to_freq": "weekly",
                "aggfunc": "sum",
            }
        )
        da = _daily_da(14, 1)
        out = dr.execute(["precip_weekly"], inputs={"precip_daily": da})[
            "precip_weekly"
        ]
        expected = da.isel(time=slice(0, 7)).sum("time").values
        np.testing.assert_allclose(out.isel(time=0).values, expected)

    def test_multiple_vars_fan_out(self):
        dr = self._driver(
            {"vars": ["a", "b"], "from_freq": "daily", "to_freq": "weekly"}
        )
        da = _daily_da(14, 1)
        results = dr.execute(
            ["a_weekly", "b_weekly"],
            inputs={"a_daily": da, "b_daily": da},
        )
        assert set(results) == {"a_weekly", "b_weekly"}


class TestResampleSpecValidation:
    """ResampleSpec.from_config validation and offset resolution."""

    def test_default_aggfunc_is_mean(self):
        from conduit.config import ResampleSpec

        spec = ResampleSpec.from_config(
            {"vars": ["x"], "from_freq": "daily", "to_freq": "weekly"}
        )
        assert spec.aggfunc == "mean"

    def test_unsupported_aggfunc_raises(self):
        from conduit.config import ResampleSpec

        with pytest.raises(ValueError, match="Unsupported aggfunc"):
            ResampleSpec.from_config(
                {
                    "vars": ["x"],
                    "from_freq": "daily",
                    "to_freq": "weekly",
                    "aggfunc": "banana",
                }
            )

    def test_offset_from_default_map(self):
        from conduit.config import ResampleSpec

        spec = ResampleSpec(vars=["x"], source_freq="daily", target_freq="weekly")
        assert spec.offset == "7D"

    def test_explicit_freq_used_as_offset(self):
        from conduit.config import ResampleSpec

        spec = ResampleSpec(
            vars=["x"], source_freq="daily", target_freq="10day", freq="10D"
        )
        assert spec.offset == "10D"

    def test_unknown_direction_without_freq_raises(self):
        from conduit.config import ResampleSpec

        with pytest.raises(ValueError, match="No default offset"):
            ResampleSpec.from_config(
                {"vars": ["x"], "from_freq": "monthly", "to_freq": "daily"}
            )
