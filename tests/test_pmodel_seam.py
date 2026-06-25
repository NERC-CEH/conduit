"""Tests for the P-Model ``apply_ufunc`` block seam (``satterc.dag.pmodel._pmodel``).

Unlike RothC/SGAM, the P-Model is a *whole-block* model: pyrealm vectorises over the
spatial axis internally, so there was never a per-pixel Python loop. The seam replaces a
bespoke ``xarray_io`` ``.data`` pull/repack with ``xr.apply_ufunc`` (no core dims, since
the model is element-wise), which keeps a future dask backend reachable.

1. Regression — because the P-Model is element-wise, running the whole ``(time, pixel)``
   block must equal running each pixel column independently and stacking. That per-pixel
   anchor is an independent calling pattern, so it catches any axis/coord mangling in the
   seam.
2. Strategy C stays open — ``.chunk({"pixel": k})`` (dask-backed) inputs give identical
   results. Skipped when dask is absent.
3. Caching intact — the seam is internal to the node, so the cached pipeline still
   matches the uncached one.
"""

import numpy as np
import pandas as pd
import pyrealm.pmodel
import pytest
import xarray as xr

from satterc.dag.pmodel import _pmodel

N_WEEKS = 52
N_PIXELS = 3
WEEKLY_DATES = pd.date_range("2020-01-01", periods=N_WEEKS, freq="7D")
PIXELS = np.arange(N_PIXELS)

METHODS = dict(
    method_optchi="prentice14",
    method_jmaxlim="wang17",
    method_kphio="temperature",
    method_arrhenius="simple",
)


def _temporal(base: np.ndarray) -> xr.DataArray:
    """A (time, pixel) DataArray whose columns differ per pixel."""
    return xr.DataArray(
        base,
        dims=["time", "pixel"],
        coords={"time": WEEKLY_DATES, "pixel": PIXELS},
    )


@pytest.fixture(scope="module")
def pmodel_inputs() -> dict:
    """Heterogeneous multi-pixel inputs (distinct climate per pixel column)."""
    rng = np.random.default_rng(0)

    def _vary(center: float, spread: float) -> np.ndarray:
        offsets = np.linspace(-spread, spread, N_PIXELS)
        return (
            center + offsets[None, :] + rng.normal(0.0, spread / 4, (N_WEEKS, N_PIXELS))
        )

    return dict(
        temperature_weekly=_temporal(_vary(15.0, 5.0)),
        vpd_weekly=_temporal(np.abs(_vary(1000.0, 300.0))),
        co2_weekly=_temporal(np.full((N_WEEKS, N_PIXELS), 400.0)),
        pressure_weekly=_temporal(np.full((N_WEEKS, N_PIXELS), 101325.0)),
        fapar_weekly=_temporal(np.clip(_vary(0.5, 0.2), 0, 1)),
        ppfd_weekly=_temporal(np.abs(_vary(500.0, 150.0))),
        mean_growth_temperature_weekly=_temporal(_vary(15.0, 5.0)),
        aridity_index_weekly=_temporal(np.clip(_vary(0.5, 0.2), 0, 2)),
        soil_moisture_weekly=_temporal(np.abs(_vary(100.0, 30.0))),
        **METHODS,
    )


def _reference_loop(inputs: dict) -> dict[str, np.ndarray]:
    """Independent per-pixel reference, exploiting the model's element-wise nature.

    Runs pyrealm column-by-column and stacks; this is the anchor for the regression
    check. For an element-wise model this must equal the whole-block seam result.
    """

    def col(name: str, i: int) -> np.ndarray:
        return inputs[name].values[:, i]

    per_pixel: dict[str, list] = {"gpp_weekly": [], "lue_weekly": [], "iwue_weekly": []}
    for i in range(N_PIXELS):
        env = pyrealm.pmodel.PModelEnvironment(
            tc=col("temperature_weekly", i),
            vpd=col("vpd_weekly", i),
            co2=col("co2_weekly", i),
            patm=col("pressure_weekly", i),
            fapar=col("fapar_weekly", i),
            ppfd=col("ppfd_weekly", i),
            theta=col("soil_moisture_weekly", i) / 300,
            mean_growth_temperature=col("mean_growth_temperature_weekly", i),
            aridity_index=col("aridity_index_weekly", i),
        )
        model = pyrealm.pmodel.PModel(
            env=env,
            method_optchi=inputs["method_optchi"],
            method_kphio=inputs["method_kphio"],
            method_arrhenius=inputs["method_arrhenius"],
            method_jmaxlim=inputs["method_jmaxlim"],
        )
        per_pixel["gpp_weekly"].append(np.nan_to_num(model.gpp, nan=0.0))
        per_pixel["lue_weekly"].append(np.nan_to_num(model.lue, nan=0.0))
        per_pixel["iwue_weekly"].append(np.nan_to_num(model.iwue, nan=0.0))

    return {name: np.column_stack(cols) for name, cols in per_pixel.items()}


class TestRegression:
    """The block seam reproduces the per-pixel reference, for every output."""

    @pytest.fixture(scope="class")
    def seam_result(self, pmodel_inputs):
        return _pmodel(**pmodel_inputs)

    @pytest.fixture(scope="class")
    def reference(self, pmodel_inputs) -> dict:
        return _reference_loop(pmodel_inputs)

    @pytest.mark.parametrize("name", ["gpp_weekly", "lue_weekly", "iwue_weekly"])
    def test_matches_reference_loop(self, seam_result, reference, name):
        np.testing.assert_allclose(
            seam_result[name].transpose("time", "pixel").values, reference[name]
        )

    def test_canonical_dims_and_coords(self, seam_result):
        for da in seam_result.values():
            assert da.dims == ("time", "pixel")
            assert da.sizes == {"time": N_WEEKS, "pixel": N_PIXELS}
            assert "time" in da.coords
            assert "pixel" in da.coords
            np.testing.assert_array_equal(da.coords["time"].values, WEEKLY_DATES.values)

    def test_per_pixel_inputs_actually_differ(self, seam_result):
        # Distinct climate columns must produce distinct GPP columns; identical columns
        # would mean the block was collapsed or broadcast incorrectly.
        gpp = seam_result["gpp_weekly"].transpose("time", "pixel").values
        assert not np.allclose(gpp[:, 0], gpp[:, 1])
        assert not np.allclose(gpp[:, 1], gpp[:, 2])


class TestStrategyCStaysOpen:
    """Chunked (dask-backed) ``pixel`` inputs give identical results to eager numpy."""

    def test_chunked_pixel_equivalence(self, pmodel_inputs):
        pytest.importorskip("dask")
        eager = _pmodel(**pmodel_inputs)

        chunked_inputs = dict(pmodel_inputs)
        for key, val in pmodel_inputs.items():
            if isinstance(val, xr.DataArray) and "pixel" in val.dims:
                chunked_inputs[key] = val.chunk({"pixel": 1})
        chunked = _pmodel(**chunked_inputs)

        for name in ["gpp_weekly", "lue_weekly", "iwue_weekly"]:
            out = chunked[name].compute().transpose("time", "pixel").values
            np.testing.assert_allclose(
                out, eager[name].transpose("time", "pixel").values
            )


class TestCachingIntact:
    """The cached pmodel node matches the uncached one (seam is internal to the node)."""

    def test_cached_run_matches_uncached(self, tmp_path):
        from satterc import CacheSpec
        from satterc.dag.driver import build_driver

        def _mda(v: float) -> xr.DataArray:
            return xr.DataArray(
                np.full((N_WEEKS, N_PIXELS), float(v)),
                dims=["time", "pixel"],
                coords={"time": WEEKLY_DATES, "pixel": PIXELS},
            )

        inputs = {
            "temperature_weekly": _mda(15.0),
            "vpd_weekly": _mda(1000.0),
            "co2_weekly": _mda(400.0),
            "pressure_weekly": _mda(101325.0),
            "fapar_weekly": _mda(0.5),
            "ppfd_weekly": _mda(500.0),
            "aridity_index_weekly": _mda(0.5),
            "soil_moisture_weekly": _mda(100.0),
        }
        # mean_growth_temperature_weekly is itself a node (derived from daily
        # temperature); override it directly so the cached test needs no upstream.
        overrides = {"mean_growth_temperature_weekly": _mda(15.0)}
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(["models.pmodel"], {}, cache=cache)
            return dr.execute(  # type: ignore[reportArgumentType]
                ["gpp_weekly"], inputs=inputs, overrides=overrides
            )

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        np.testing.assert_allclose(
            cached["gpp_weekly"].values, uncached["gpp_weekly"].values
        )
        assert (tmp_path / "cache").exists()
