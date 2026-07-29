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


class TestResampleTimeDim:
    """The time axis is detected, not assumed to be called ``time``."""

    def test_time_axis_need_not_be_called_time(self):
        da = _daily_da(14, 1).rename({"time": "acquired"})
        out = resample(da, freq="7D")
        assert out.sizes["acquired"] == 2

    def test_explicit_dim_overrides_detection(self):
        da = _daily_da(14, 1).rename({"time": "acquired"})
        out = resample(da, freq="7D", dim="acquired")
        assert out.sizes["acquired"] == 2

    def test_no_time_axis_raises(self):
        da = xr.DataArray(
            np.zeros((3, 2)),
            dims=("band", "pixel"),
            coords={"band": ["r", "g", "b"], "pixel": [0, 1]},
        )
        with pytest.raises(ValueError, match="has no time dimension"):
            resample(da, freq="7D")

    def test_ambiguous_time_axis_raises(self):
        da = xr.DataArray(
            np.zeros((4, 3)),
            dims=("time", "lead_time"),
            coords={
                "time": pd.date_range("2020-01-01", periods=4, freq="D"),
                "lead_time": pd.date_range("2020-06-01", periods=3, freq="D"),
            },
        )
        with pytest.raises(ValueError, match="multiple time dimensions"):
            resample(da, freq="7D")


class TestResamplePresetPipeline:
    """[[resample]] desugars to a passthrough node; the built driver executes it."""

    def _driver(self, entry: dict):
        parsed = Config({"resample": [entry]}).parse()
        assert parsed.modules == ["node"]  # no dedicated resample module
        return build_driver(
            parsed.modules, parsed.driver_config, node_specs=parsed.node_specs
        )

    def test_weekly_offset(self):
        dr = self._driver(
            {"vars": ["temperature"], "from": "daily", "to": "weekly", "freq": "7D"}
        )
        da = _daily_da(14, 1)
        out = dr.execute(["temperature_weekly"], inputs={"temperature_daily": da})[
            "temperature_weekly"
        ]
        expected = da.isel(time=slice(0, 7)).mean("time").values
        np.testing.assert_allclose(out.isel(time=0).values, expected)

    def test_freq_is_independent_of_the_to_label(self):
        # ``to`` only names the output node; ``freq`` alone sets the frequency.
        dr = self._driver(
            {
                "vars": ["temperature"],
                "from": "daily",
                "to": "custom",
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
                "from": "daily",
                "to": "weekly",
                "freq": "7D",
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
            {"vars": ["a", "b"], "from": "daily", "to": "weekly", "freq": "7D"}
        )
        da = _daily_da(14, 1)
        results = dr.execute(
            ["a_weekly", "b_weekly"],
            inputs={"a_daily": da, "b_daily": da},
        )
        assert set(results) == {"a_weekly", "b_weekly"}


class TestResampleSpecValidation:
    """ResampleSpec.from_config validation."""

    def test_default_aggfunc_is_mean(self):
        from conduit.config import ResampleSpec

        spec = ResampleSpec.from_config(
            {"vars": ["x"], "from": "daily", "to": "weekly", "freq": "7D"}
        )
        assert spec.aggfunc == "mean"

    def test_unsupported_aggfunc_raises(self):
        from conduit.config import ResampleSpec

        with pytest.raises(ValueError, match="Unsupported aggfunc"):
            ResampleSpec.from_config(
                {
                    "vars": ["x"],
                    "from": "daily",
                    "to": "weekly",
                    "freq": "7D",
                    "aggfunc": "banana",
                }
            )

    @pytest.mark.parametrize("missing", ["vars", "from", "to", "freq"])
    def test_missing_required_key_raises(self, missing):
        from conduit.config import ResampleSpec

        entry = {"vars": ["x"], "from": "daily", "to": "weekly", "freq": "7D"}
        del entry[missing]
        with pytest.raises(ValueError, match=f"missing required key.*{missing}"):
            ResampleSpec.from_config(entry)

    def test_any_direction_is_allowed_given_a_freq(self):
        # There is no table of "supported directions" any more: the labels are
        # arbitrary and ``freq`` says what actually happens.
        from conduit.config import ResampleSpec

        spec = ResampleSpec.from_config(
            {"vars": ["x"], "from": "monthly", "to": "seasonal", "freq": "QE"}
        )
        assert (spec.source, spec.target, spec.freq) == ("monthly", "seasonal", "QE")

    def test_invalid_freq_raises(self):
        from conduit.config import ResampleSpec

        with pytest.raises(ValueError, match="invalid frequency 'banana'"):
            ResampleSpec.from_config(
                {"vars": ["x"], "from": "daily", "to": "weekly", "freq": "banana"}
            )
