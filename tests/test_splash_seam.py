"""Tests for the SPLASH ``apply_ufunc`` block seam (``satterc.dag.splash._splash``).

Like the P-Model, SPLASH is a *whole-block* pyrealm model — it vectorises over the
spatial axis internally and loops only over ``time`` (soil moisture carries state day to
day). The seam replaces a bespoke ``xarray_io`` ``.data`` pull with ``xr.apply_ufunc``
(``time`` as the core dim, ``pixel`` the broadcast dim, ``vectorize=False`` so pyrealm
still vectorises the block), which both keeps a future dask backend reachable *and* fixes
a live correctness bug: the old code passed ``latitude[0]``/``elevation[0]``/
``max_soil_moisture[0]`` to pyrealm, so every pixel silently received pixel 0's static
parameters.

1. Regression — the seam reproduces an independent *whole-block* pyrealm call with the
   statics correctly broadcast per pixel (the anchor pins the apply_ufunc plumbing:
   moveaxis, core-dim handling, coord reattach, transpose).
2. Bug fix — feeding identical climate to two pixels with *different* latitudes yields
   *different* outputs; the old ``[0]``-indexing would have tied them together.
3. Strategy C stays open — ``.chunk({"pixel": k})`` (dask-backed) inputs give identical
   results. Skipped when dask is absent.
4. Caching intact — the seam is internal to the node, so the cached pipeline still
   matches the uncached one.
"""

import numpy as np
import pandas as pd
import pyrealm.core.calendar
import pyrealm.splash.splash
import pytest
import xarray as xr

from satterc.dag.splash import _splash

N_DAYS = 366  # 2020 is a leap year; SPLASH needs a full year for spin-up
N_PIXELS = 3
DAILY_DATES = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
PIXELS = np.arange(N_PIXELS)
MAX_ITER = 50
MAX_DIFF = 0.01

# Per-pixel statics — deliberately distinct so the old [0]-indexing bug (every pixel
# getting pixel 0's lat/elv/kWm) would change the outputs and fail the regression check.
LATITUDE = np.array([51.5, -33.0, 10.0])  # NH, SH, near-equator
ELEVATION = np.array([50.0, 800.0, 2000.0])
MAX_SM = np.array([150.0, 120.0, 180.0])

_DAY = np.arange(N_DAYS)
_SEASON = np.sin(2 * np.pi * _DAY / 365)


def _temporal(base: np.ndarray) -> xr.DataArray:
    return xr.DataArray(
        base,
        dims=["time", "pixel"],
        coords={"time": DAILY_DATES, "pixel": PIXELS},
    )


def _static(values: np.ndarray) -> xr.DataArray:
    return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})


@pytest.fixture(scope="module")
def splash_inputs() -> dict:
    """Heterogeneous multi-pixel inputs; smooth seasonal climate so spin-up converges."""
    # Per-pixel temperature offsets; sunshine/precip seasonal but pixel-invariant.
    temp = 10.0 + 8.0 * _SEASON[:, None] + np.array([0.0, -5.0, 3.0])[None, :]
    sf = np.clip(0.5 + 0.05 * _SEASON, 0, 1)
    return dict(
        sunshine_fraction_daily=_temporal(np.tile(sf[:, None], (1, N_PIXELS))),
        temperature_daily=_temporal(temp),
        precipitation_daily=_temporal(np.full((N_DAYS, N_PIXELS), 2.0)),
        elevation=_static(ELEVATION),
        latitude=_static(LATITUDE),
        max_soil_moisture=_static(MAX_SM),
        dates_daily=DAILY_DATES,
        soil_moisture_init_max_iter=MAX_ITER,
        soil_moisture_init_max_diff=MAX_DIFF,
    )


def _reference_block(inputs: dict) -> dict[str, np.ndarray]:
    """Independent whole-block pyrealm reference with statics correctly broadcast.

    Returns a dict of (time, pixel) numpy arrays, the anchor for the regression check.
    ``lat``/``elv`` go in as ``(1, pixel)`` (broadcast over time); ``kWm`` as ``(pixel,)``
    — the layout pyrealm requires and the bug fix relies on.
    """
    calendar = pyrealm.core.calendar.Calendar(inputs["dates_daily"].values)
    model = pyrealm.splash.splash.SplashModel(
        lat=inputs["latitude"].values[None, :],
        elv=inputs["elevation"].values[None, :],
        sf=inputs["sunshine_fraction_daily"].values,
        tc=inputs["temperature_daily"].values,
        pn=inputs["precipitation_daily"].values,
        dates=calendar,
        kWm=inputs["max_soil_moisture"].values,
    )
    init = model.estimate_initial_soil_moisture(
        max_iter=MAX_ITER, max_diff=MAX_DIFF, verbose=False
    )
    aet, moisture, runoff = model.calculate_soil_moisture(init)
    return {
        "actual_evapotranspiration_daily": aet,
        "soil_moisture_daily": moisture,
        "runoff_daily": runoff,
    }


_OUTPUT_NAMES = (
    "actual_evapotranspiration_daily",
    "soil_moisture_daily",
    "runoff_daily",
)


class TestRegression:
    """The block seam reproduces the whole-block pyrealm reference, for every output."""

    @pytest.fixture(scope="class")
    def seam_result(self, splash_inputs):
        return _splash(**splash_inputs)

    @pytest.fixture(scope="class")
    def reference(self, splash_inputs) -> dict:
        return _reference_block(splash_inputs)

    @pytest.mark.parametrize("name", _OUTPUT_NAMES)
    def test_matches_reference(self, seam_result, reference, name):
        np.testing.assert_allclose(
            seam_result[name].transpose("time", "pixel").values, reference[name]
        )

    def test_canonical_dims_and_coords(self, seam_result):
        for da in seam_result.values():
            assert da.dims == ("time", "pixel")
            assert da.sizes == {"time": N_DAYS, "pixel": N_PIXELS}
            # apply_ufunc drops the time coord; the seam must reattach it.
            assert "time" in da.coords
            assert "pixel" in da.coords
            np.testing.assert_array_equal(da.coords["time"].values, DAILY_DATES.values)


class TestPerPixelStaticsThreaded:
    """The fix: each pixel uses its own latitude (old code used pixel 0's for all)."""

    def test_identical_climate_different_latitude_differs(self, splash_inputs):
        # Two pixels, identical climate, opposite-hemisphere latitudes. Solar fluxes
        # depend on latitude, so correct per-pixel threading must split the columns;
        # the old latitude[0] bug would have made them identical.
        n = 2
        px = np.arange(n)
        col_sf = np.clip(0.5 + 0.05 * _SEASON, 0, 1)
        col_tc = 10.0 + 8.0 * _SEASON

        def md(v):
            return xr.DataArray(
                v, dims=["time", "pixel"], coords={"time": DAILY_DATES, "pixel": px}
            )

        def sd(v):
            return xr.DataArray(
                np.asarray(v, dtype=float), dims=["pixel"], coords={"pixel": px}
            )

        result = _splash(
            sunshine_fraction_daily=md(np.tile(col_sf[:, None], (1, n))),
            temperature_daily=md(np.tile(col_tc[:, None], (1, n))),
            precipitation_daily=md(np.full((N_DAYS, n), 2.0)),
            elevation=sd([100.0, 100.0]),
            latitude=sd([51.5, -51.5]),
            max_soil_moisture=sd([150.0, 150.0]),
            dates_daily=DAILY_DATES,
            soil_moisture_init_max_iter=MAX_ITER,
            soil_moisture_init_max_diff=MAX_DIFF,
        )
        sm = result["soil_moisture_daily"].transpose("time", "pixel").values
        assert not np.allclose(sm[:, 0], sm[:, 1])


class TestStrategyCStaysOpen:
    """Chunked (dask-backed) ``pixel`` inputs give identical results to eager numpy."""

    def test_chunked_pixel_equivalence(self, splash_inputs):
        pytest.importorskip("dask")
        eager = _splash(**splash_inputs)

        chunked_inputs = dict(splash_inputs)
        for key, val in splash_inputs.items():
            if isinstance(val, xr.DataArray) and "pixel" in val.dims:
                chunked_inputs[key] = val.chunk({"pixel": 1})
        chunked = _splash(**chunked_inputs)

        for name in _OUTPUT_NAMES:
            out = chunked[name].compute().transpose("time", "pixel").values
            np.testing.assert_allclose(
                out, eager[name].transpose("time", "pixel").values
            )


class TestCachingIntact:
    """The cached splash node matches the uncached one (seam is internal to the node)."""

    def test_cached_run_matches_uncached(self, tmp_path, splash_inputs):
        from satterc import CacheSpec
        from satterc.dag.driver import build_driver

        inputs = {
            k: v
            for k, v in splash_inputs.items()
            if k not in ("soil_moisture_init_max_iter", "soil_moisture_init_max_diff")
        }
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(
                ["models.splash"],
                {
                    "soil_moisture_init_max_iter": MAX_ITER,
                    "soil_moisture_init_max_diff": MAX_DIFF,
                },
                cache=cache,
            )
            return dr.execute(["soil_moisture_daily"], inputs=inputs)  # type: ignore[reportArgumentType]

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        np.testing.assert_allclose(
            cached["soil_moisture_daily"].values,
            uncached["soil_moisture_daily"].values,
        )
        assert (tmp_path / "cache").exists()
