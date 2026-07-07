"""Tests for the input-Dataset compatibility suite (`conduit.checks`)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from conduit.checks import (
    CHECKS,
    InputCheckError,
    coords_equal,
    crs_equal,
    run_input_checks,
    spatial_grid_equal,
    time_equal,
    time_subset,
)
from conduit.config import CheckSpec


def _ts_ds(times, name="v"):
    """A tiny time-indexed dataset."""
    return xr.Dataset(
        {name: ("time", np.arange(len(times), dtype=float))},
        coords={"time": pd.DatetimeIndex(times)},
    )


DAILY = pd.date_range("2020-01-01", periods=10, freq="D")


# ---------------------------------------------------------------------------
# time_equal
# ---------------------------------------------------------------------------


class TestTimeEqual:
    def test_identical_passes(self):
        time_equal(_ts_ds(DAILY), _ts_ds(DAILY, name="w"))

    def test_single_dataset_passes(self):
        time_equal(_ts_ds(DAILY))

    def test_differing_index_raises(self):
        with pytest.raises(ValueError, match="dataset 1 time index differs"):
            time_equal(_ts_ds(DAILY), _ts_ds(DAILY[:5]))

    def test_missing_time_dim_raises(self):
        ds = xr.Dataset({"v": ("x", [1.0, 2.0])}, coords={"x": [0, 1]})
        with pytest.raises(ValueError, match="no time dimension"):
            time_equal(_ts_ds(DAILY), ds)


# ---------------------------------------------------------------------------
# time_subset
# ---------------------------------------------------------------------------


class TestTimeSubset:
    def test_subset_passes(self):
        time_subset(_ts_ds(DAILY), _ts_ds(DAILY[2:6]))

    def test_superfluous_timestamp_raises(self):
        extra = DAILY.append(pd.DatetimeIndex(["2021-01-01"]))
        with pytest.raises(ValueError, match="absent from dataset 0"):
            time_subset(_ts_ds(DAILY), _ts_ds(extra))

    def test_wrong_arity_raises(self):
        with pytest.raises(ValueError, match="exactly 2 datasets"):
            time_subset(_ts_ds(DAILY))

    def test_missing_time_dim_raises(self):
        ds = xr.Dataset({"v": ("x", [1.0])}, coords={"x": [0]})
        with pytest.raises(ValueError, match="no time dimension"):
            time_subset(_ts_ds(DAILY), ds)


# ---------------------------------------------------------------------------
# spatial_grid_equal / crs_equal (reuse gridded fixtures)
# ---------------------------------------------------------------------------


class TestSpatialGridEqual:
    def test_matching_grid_passes(self, daily_ds, static_ds):
        spatial_grid_equal(daily_ds, static_ds)

    def test_single_dataset_passes(self, daily_ds):
        spatial_grid_equal(daily_ds)

    def test_mismatched_crs_raises(self, daily_ds):
        from conduit.gridded.io import MisalignedGridError

        other = daily_ds.rio.write_crs("EPSG:3857")
        with pytest.raises(MisalignedGridError):
            spatial_grid_equal(daily_ds, other)


class TestCrsEqual:
    def test_matching_crs_passes(self, daily_ds, static_ds):
        crs_equal(daily_ds, static_ds)

    def test_mismatched_crs_raises(self, daily_ds):
        other = daily_ds.rio.write_crs("EPSG:3857")
        with pytest.raises(ValueError, match="CRS"):
            crs_equal(daily_ds, other)

    def test_single_dataset_passes(self, daily_ds):
        crs_equal(daily_ds)


# ---------------------------------------------------------------------------
# coords_equal
# ---------------------------------------------------------------------------


class TestCoordsEqual:
    def test_matching_passes(self, daily_ds, static_ds):
        coords_equal(daily_ds, static_ds, coords=["x", "y"])

    def test_within_atol_passes(self, daily_ds):
        shifted = daily_ds.assign_coords(x=daily_ds["x"] + 1e-9)
        coords_equal(daily_ds, shifted, coords=["x"], atol=1e-6)

    def test_beyond_atol_raises(self, daily_ds):
        shifted = daily_ds.assign_coords(x=daily_ds["x"] + 1.0)
        with pytest.raises(ValueError, match="values differ"):
            coords_equal(daily_ds, shifted, coords=["x"], atol=1e-6)

    def test_missing_coord_raises(self, daily_ds, static_ds):
        with pytest.raises(ValueError, match="missing"):
            coords_equal(daily_ds, static_ds, coords=["nonexistent"])

    def test_shape_mismatch_raises(self, daily_ds):
        smaller = daily_ds.isel(x=slice(0, 1))
        with pytest.raises(ValueError, match="shape"):
            coords_equal(daily_ds, smaller, coords=["x"])

    def test_datetime_coord_exact_match_passes(self):
        # Non-float coords take the exact-comparison branch.
        coords_equal(_ts_ds(DAILY), _ts_ds(DAILY, name="w"), coords=["time"])

    def test_datetime_coord_mismatch_raises(self):
        shifted = _ts_ds(DAILY + pd.Timedelta(days=1))
        with pytest.raises(ValueError, match="values differ"):
            coords_equal(_ts_ds(DAILY), shifted, coords=["time"])

    def test_missing_coord_in_later_dataset_raises(self, daily_ds):
        renamed = daily_ds.rename(x="col")
        with pytest.raises(ValueError, match="missing from dataset 1"):
            coords_equal(daily_ds, renamed, coords=["x"])

    def test_single_dataset_passes(self, daily_ds):
        coords_equal(daily_ds, coords=["x"])


# ---------------------------------------------------------------------------
# Registry + run_input_checks
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_expected_checks_registered(self):
        assert set(CHECKS) == {
            "time_equal",
            "time_subset",
            "spatial_grid_equal",
            "crs_equal",
            "coords_equal",
        }

    def test_arities(self):
        assert CHECKS["time_subset"].arity == 2
        assert CHECKS["time_equal"].arity == "variadic"


class TestRunInputChecks:
    def test_passing_checks_return_none(self):
        raw = {"a": _ts_ds(DAILY), "b": _ts_ds(DAILY, name="w")}
        run_input_checks(raw, [CheckSpec("time_equal", ["a", "b"])])

    def test_variadic_single_input_is_noop(self):
        raw = {"a": _ts_ds(DAILY)}
        run_input_checks(raw, [CheckSpec("time_equal", ["a"])])

    def test_failures_aggregate(self):
        raw = {
            "a": _ts_ds(DAILY),
            "b": _ts_ds(DAILY[:5]),
            "c": _ts_ds(DAILY[2:8]),
        }
        specs = [
            CheckSpec("time_equal", ["a", "b"]),
            CheckSpec("time_subset", ["b", "a"]),
        ]
        with pytest.raises(InputCheckError) as exc:
            run_input_checks(raw, specs)
        msg = str(exc.value)
        assert "2 input check(s) failed" in msg
        assert "time_equal" in msg
        assert "time_subset" in msg

    def test_unknown_arity_backstop(self):
        # Direct call bypassing the parser: fixed-arity self-guard still fires.
        with pytest.raises(ValueError, match="exactly 2"):
            run_input_checks(
                {"a": _ts_ds(DAILY), "b": _ts_ds(DAILY), "c": _ts_ds(DAILY)},
                [CheckSpec("time_subset", ["a", "b", "c"])],
            )

    def test_kwargs_forwarded(self, daily_ds):
        shifted = daily_ds.assign_coords(x=daily_ds["x"] + 0.5)
        raw = {"a": daily_ds, "b": shifted}
        # atol wide enough to pass
        run_input_checks(
            raw, [CheckSpec("coords_equal", ["a", "b"], {"coords": ["x"], "atol": 1.0})]
        )
        # atol too tight to pass
        with pytest.raises(InputCheckError):
            run_input_checks(
                raw,
                [
                    CheckSpec(
                        "coords_equal", ["a", "b"], {"coords": ["x"], "atol": 1e-6}
                    )
                ],
            )


class TestRunInputChecksHook:
    """The cli/run.py `_run_input_checks` orchestration hook."""

    def _parsed(self, subset):
        from conduit.config import ParsedConfig, SubsetSpec

        return ParsedConfig(
            modules=[],
            driver_config={},
            input_specs={},
            subset_spec=SubsetSpec(pixel_start=0, pixel_end=1) if subset else None,
            checks=[CheckSpec("time_equal", ["a"])],
        )

    def test_no_checks_is_noop(self):
        from conduit.cli.run import _run_input_checks
        from conduit.config import ParsedConfig

        parsed = ParsedConfig(modules=[], driver_config={}, checks=[])
        assert _run_input_checks(parsed) == 0

    def test_subset_skips_with_warning(self):
        from conduit.cli.run import _run_input_checks

        parsed = self._parsed(subset=True)
        with pytest.warns(UserWarning, match="input checks skipped under \\[subset\\]"):
            assert _run_input_checks(parsed) == 0
