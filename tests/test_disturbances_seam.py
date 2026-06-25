"""Tests for the disturbance-detection ``apply_ufunc`` block seam
(``satterc.dag.sgam._disturbances_daily``).

``sgam.Disturbances.forward`` is a *whole-block* computation: it diffs GPP/LAI along the
time axis and is otherwise element-wise over pixels, so it vectorises over ``pixel``
exactly like SPLASH. The seam replaces a bespoke ``xarray_io`` ``.data`` pull with
``xr.apply_ufunc`` (``time`` the core dim, ``pixel`` the broadcast dim,
``vectorize=False`` so the kernel still vectorises the whole block), retiring the last
use of ``xarray_io``.

1. Regression — the seam reproduces an independent *whole-block* ``Disturbances.forward``
   call on the full ``(time, pixel)`` arrays (the anchor pins the apply_ufunc plumbing:
   moveaxis, core-dim handling, coord reattach, transpose).
2. Canonical dims/coords — every output ``(time, pixel)`` with the ``time`` coord
   reattached.
3. Per-pixel inputs differ — distinct disturbance days per column give distinct outputs.
4. Strategy C stays open — ``.chunk({"pixel": k})`` (dask-backed) inputs give identical
   results. Skipped when dask is absent.
5. Caching intact — the seam is internal to the node, so the cached pipeline still
   matches the uncached one.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from sgam import Disturbances

from satterc.dag.sgam import _disturbances_daily

N_DAYS = 120
N_PIXELS = 3
DAILY_DATES = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
PIXELS = np.arange(N_PIXELS)

# A disturbance fires when, on a warm day, GPP and LAI both drop by > 30% vs the
# previous day. Put the drop on a *different* day per pixel so columns differ.
DROP_DAYS = np.array([40, 60, 80])
GROWING_SEASON_LIMIT = 10.0
DISTURBANCE_THRESHOLD = 0.3


def _build_climate() -> dict[str, np.ndarray]:
    """Warm, smooth climate with one sharp GPP+LAI crash per pixel (distinct days)."""
    temperature = np.full((N_DAYS, N_PIXELS), 20.0)  # always above growing-season limit
    gpp = np.full((N_DAYS, N_PIXELS), 5.0)
    lai = np.full((N_DAYS, N_PIXELS), 2.0)
    for p, day in enumerate(DROP_DAYS):
        gpp[day:, p] = 1.0  # 80% drop on `day`
        lai[day:, p] = 0.4  # 80% drop on `day`
    return {"temperature": temperature, "gpp": gpp, "lai": lai}


def _temporal(base: np.ndarray) -> xr.DataArray:
    return xr.DataArray(
        base,
        dims=["time", "pixel"],
        coords={"time": DAILY_DATES, "pixel": PIXELS},
    )


def _static(values: np.ndarray) -> xr.DataArray:
    return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})


@pytest.fixture(scope="module")
def disturbance_inputs() -> dict:
    climate = _build_climate()
    return dict(
        temperature_daily=_temporal(climate["temperature"]),
        gpp_daily=_temporal(climate["gpp"]),
        lai_daily=_temporal(climate["lai"]),
    )


def _reference_block(inputs: dict) -> np.ndarray:
    """Independent whole-block reference: call Disturbances.forward on (time, pixel)."""
    detector = Disturbances(
        growing_season_limit=GROWING_SEASON_LIMIT,
        disturbance_threshold=DISTURBANCE_THRESHOLD,
    )
    return detector.forward(
        inputs["temperature_daily"].values,
        inputs["gpp_daily"].values,
        inputs["lai_daily"].values,
        aggregate=False,
    )


class TestRegression:
    """The block seam reproduces the whole-block Disturbances reference."""

    @pytest.fixture(scope="class")
    def seam_result(self, disturbance_inputs):
        return _disturbances_daily(**disturbance_inputs)

    @pytest.fixture(scope="class")
    def reference(self, disturbance_inputs) -> np.ndarray:
        return _reference_block(disturbance_inputs)

    def test_matches_reference(self, seam_result, reference):
        np.testing.assert_allclose(
            seam_result.transpose("time", "pixel").values, reference
        )

    def test_canonical_dims_and_coords(self, seam_result):
        assert seam_result.dims == ("time", "pixel")
        assert seam_result.sizes == {"time": N_DAYS, "pixel": N_PIXELS}
        # apply_ufunc drops the time coord; the seam must reattach it.
        assert "time" in seam_result.coords
        assert "pixel" in seam_result.coords
        np.testing.assert_array_equal(
            seam_result.coords["time"].values, DAILY_DATES.values
        )

    def test_per_pixel_inputs_differ(self, seam_result):
        # The crash is on a different day per pixel, so the disturbance columns must
        # differ; identical columns would mean the block was collapsed/broadcast wrong.
        sev = seam_result.transpose("time", "pixel").values
        assert not np.allclose(sev[:, 0], sev[:, 1])
        assert not np.allclose(sev[:, 1], sev[:, 2])
        # And a disturbance is actually detected on each pixel's drop day.
        for p, day in enumerate(DROP_DAYS):
            assert sev[day, p] > 0.0


class TestStrategyCStaysOpen:
    """Chunked (dask-backed) ``pixel`` inputs give identical results to eager numpy."""

    def test_chunked_pixel_equivalence(self, disturbance_inputs):
        pytest.importorskip("dask")
        eager = _disturbances_daily(**disturbance_inputs)

        chunked_inputs = {
            key: val.chunk({"pixel": 1}) for key, val in disturbance_inputs.items()
        }
        chunked = _disturbances_daily(**chunked_inputs)

        np.testing.assert_allclose(
            chunked.compute().transpose("time", "pixel").values,
            eager.transpose("time", "pixel").values,
        )


class TestCachingIntact:
    """The cached disturbances node matches the uncached one (seam is node-internal)."""

    def test_cached_run_matches_uncached(self, tmp_path, disturbance_inputs):
        from satterc import CacheSpec
        from satterc.dag.driver import build_driver

        # disturbances_daily also depends on plant_type/latitude (declared but unused).
        inputs = dict(disturbance_inputs)
        inputs["plant_type"] = _static(np.zeros(N_PIXELS, dtype=float))
        inputs["latitude"] = _static(np.array([51.5, -33.0, 10.0]))
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(["models.sgam"], {}, cache=cache)
            return dr.execute(["disturbances_daily"], inputs=inputs)  # type: ignore[reportArgumentType]

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        np.testing.assert_allclose(
            cached["disturbances_daily"].values,
            uncached["disturbances_daily"].values,
        )
        assert (tmp_path / "cache").exists()
