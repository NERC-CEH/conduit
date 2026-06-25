"""Tests for the SGAM ``apply_ufunc`` pixel seam (``satterc.dag.sgam._sgam``).

These cover the inner block-level parallelisation seam that replaced the explicit
``for i in range(len(plant_type))`` loop:

1. Regression — the seam reproduces, bit-for-bit, an independent per-pixel reference
   loop across *multiple, heterogeneous* pixels (distinct plant types, mixed-sign
   latitudes, and per-pixel init pools). A single-pixel smoke test cannot catch a
   pixel-misalignment bug, so the heterogeneity here is the point.
2. Strategy C stays open — feeding ``.chunk({"pixel": k})`` (dask-backed) inputs yields
   identical results, proving the seam is ready for a future dask execution backend
   without building it. Skipped when dask is absent.
3. Caching intact — the seam is internal to the node, so the cached pipeline still
   matches the uncached one.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from satterc.dag.sgam import (
    _SGAM_OUTPUT_NAMES,
    _build_pft_params_dataset,
    _pft_int_to_enum,
    _pft_params_from_dataset,
    _sgam,
)

N_WEEKS = 52
N_PIXELS = 3
WEEKLY_DATES = pd.date_range("2020-01-01", periods=N_WEEKS, freq="7D")
PIXELS = np.arange(N_PIXELS)

# Per-pixel metadata — deliberately distinct so a mapping bug (e.g. all pixels getting
# pixel 0's PFT or hemisphere) would change the outputs and fail the regression check.
PLANT_TYPE = np.array([0, 1, 3])  # tree, grass, crop -> distinct PftParams
LATITUDE = np.array([51.5, -33.0, 10.0])  # NH, SH, NH -> exercises hemisphere
LEAF_INIT = np.array([1.0, 2.0, 0.5])
STEM_INIT = np.array([5.0, 3.0, 1.0])
ROOT_INIT = np.array([2.0, 1.5, 0.8])


def _temporal(base: np.ndarray) -> xr.DataArray:
    """A (time, pixel) DataArray whose columns differ per pixel."""
    return xr.DataArray(
        base,
        dims=["time", "pixel"],
        coords={"time": WEEKLY_DATES, "pixel": PIXELS},
    )


def _static(values: np.ndarray) -> xr.DataArray:
    return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})


@pytest.fixture(scope="module")
def sgam_inputs() -> dict:
    """Heterogeneous multi-pixel inputs (distinct climate per pixel column)."""
    rng = np.random.default_rng(0)

    def _vary(center: float, spread: float) -> np.ndarray:
        # (time, pixel) with a per-pixel offset plus mild noise.
        offsets = np.linspace(-spread, spread, N_PIXELS)
        return (
            center + offsets[None, :] + rng.normal(0.0, spread / 4, (N_WEEKS, N_PIXELS))
        )

    plant_type = _static(PLANT_TYPE.astype(float))
    return dict(
        plant_type=plant_type,
        pft_params=_build_pft_params_dataset(plant_type),
        temperature_weekly=_temporal(_vary(15.0, 5.0)),
        gpp_weekly=_temporal(np.abs(_vary(5.0, 2.0))),
        soil_moisture_weekly=_temporal(np.abs(_vary(100.0, 30.0))),
        vpd_weekly=_temporal(np.abs(_vary(1000.0, 300.0))),
        lue_weekly=_temporal(np.abs(_vary(2.0, 0.5))),
        iwue_weekly=_temporal(np.abs(_vary(100.0, 20.0))),
        dates_weekly=WEEKLY_DATES,
        disturbances_weekly=_temporal(np.zeros((N_WEEKS, N_PIXELS))),
        leaf_pool_init=_static(LEAF_INIT),
        stem_pool_init=_static(STEM_INIT),
        root_pool_init=_static(ROOT_INIT),
        latitude=_static(LATITUDE),
    )


def _reference_loop(inputs: dict) -> dict[str, np.ndarray]:
    """Independent per-pixel reference, mirroring the pre-seam ``_sgam`` loop.

    Returns a dict of (time, pixel) numpy arrays, the anchor for the regression check.
    """
    from sgam import Sgam

    week_of_year = inputs["dates_weekly"].isocalendar().week.values
    pft_params = inputs["pft_params"]

    def col(name: str, i: int) -> np.ndarray:
        return inputs[name].values[:, i]

    per_pixel: list[dict] = []
    for i in range(N_PIXELS):
        pft_enum = _pft_int_to_enum(int(inputs["plant_type"].values[i]))
        params = _pft_params_from_dataset(pft_params, i)
        hemisphere = "NH" if inputs["latitude"].values[i] >= 0 else "SH"

        output = Sgam(
            plant_type=pft_enum,
            pft_params=params,
            use_dynamic_allocation=True,
            hemisphere=hemisphere,
        )(
            gpp=col("gpp_weekly", i),
            temperature=col("temperature_weekly", i),
            soil_moisture=col("soil_moisture_weekly", i),
            vpd=col("vpd_weekly", i),
            lue=col("lue_weekly", i),
            iwue=col("iwue_weekly", i),
            week_of_year=week_of_year,
            disturbances=col("disturbances_weekly", i),
            leaf_pool_init=float(inputs["leaf_pool_init"].values[i]),
            stem_pool_init=float(inputs["stem_pool_init"].values[i]),
            root_pool_init=float(inputs["root_pool_init"].values[i]),
            litter_pool_init=0.0,
            removed_init=0.0,
            strict_mass_balance=False,
        )
        per_pixel.append(
            {
                "leaf_pool_weekly": output.pools.leaf,
                "stem_pool_weekly": output.pools.stem,
                "root_pool_weekly": output.pools.root,
                "litter_pool_weekly": output.pools.litter,
                "removed_pool_weekly": output.pools.removed,
                "npp_leaf_weekly": output.npp.leaf,
                "npp_stem_weekly": output.npp.stem,
                "npp_root_weekly": output.npp.root,
                "turnover_leaf_weekly": output.turnover.leaf,
                "turnover_stem_weekly": output.turnover.stem,
                "turnover_root_weekly": output.turnover.root,
                "respiration_leaf_weekly": output.respiration.leaf,
                "respiration_stem_weekly": output.respiration.stem,
                "respiration_root_weekly": output.respiration.root,
                "disturbance_leaf_weekly": output.disturbance.leaf,
                "disturbance_stem_weekly": output.disturbance.stem,
                "disturbance_root_weekly": output.disturbance.root,
                "cue_weekly": output.diagnostics.cue,
                "allocation_leaf_weekly": output.diagnostics.allocation_leaf,
                "allocation_stem_weekly": output.diagnostics.allocation_stem,
                "allocation_root_weekly": output.diagnostics.allocation_root,
                "drought_modifier_weekly": output.diagnostics.drought_modifier,
                "lue_score_weekly": output.diagnostics.lue_score,
                "iwue_score_weekly": output.diagnostics.iwue_score,
            }
        )

    return {
        name: np.column_stack([p[name] for p in per_pixel])
        for name in _SGAM_OUTPUT_NAMES
    }


class TestRegression:
    """The seam reproduces the per-pixel reference loop, for every output."""

    @pytest.fixture(scope="class")
    def seam_result(self, sgam_inputs):
        return _sgam(**sgam_inputs)

    @pytest.fixture(scope="class")
    def reference(self, sgam_inputs) -> dict:
        return _reference_loop(sgam_inputs)

    @pytest.mark.parametrize("name", _SGAM_OUTPUT_NAMES)
    def test_matches_reference_loop(self, seam_result, reference, name):
        np.testing.assert_allclose(
            seam_result[name].transpose("time", "pixel").values, reference[name]
        )

    def test_canonical_dims_and_coords(self, seam_result):
        for da in seam_result.values():
            assert da.dims == ("time", "pixel")
            assert da.sizes == {"time": N_WEEKS, "pixel": N_PIXELS}
            # apply_ufunc drops the time coord; the seam must reattach it.
            assert "time" in da.coords
            assert "pixel" in da.coords
            np.testing.assert_array_equal(da.coords["time"].values, WEEKLY_DATES.values)

    def test_per_pixel_params_actually_differ(self, seam_result):
        # Distinct PFTs/hemispheres must produce distinct leaf-pool columns; identical
        # columns would mean per-pixel metadata was not threaded through the seam.
        leaf = seam_result["leaf_pool_weekly"].transpose("time", "pixel").values
        assert not np.allclose(leaf[:, 0], leaf[:, 1])
        assert not np.allclose(leaf[:, 1], leaf[:, 2])


class TestStrategyCStaysOpen:
    """Chunked (dask-backed) ``pixel`` inputs give identical results to eager numpy."""

    def test_chunked_pixel_equivalence(self, sgam_inputs):
        pytest.importorskip("dask")
        eager = _sgam(**sgam_inputs)

        chunked_inputs = dict(sgam_inputs)
        for key, val in sgam_inputs.items():
            if isinstance(val, xr.DataArray) and "pixel" in val.dims:
                chunked_inputs[key] = val.chunk({"pixel": 1})
        chunked = _sgam(**chunked_inputs)

        for name in _SGAM_OUTPUT_NAMES:
            out = chunked[name].compute().transpose("time", "pixel").values
            np.testing.assert_allclose(
                out, eager[name].transpose("time", "pixel").values
            )


class TestCachingIntact:
    """The cached sgam node matches the uncached one (seam is internal to the node)."""

    def test_cached_run_matches_uncached(self, tmp_path):
        from satterc import CacheSpec
        from satterc.dag.driver import build_driver

        def _mda(base: np.ndarray) -> xr.DataArray:
            return xr.DataArray(
                base,
                dims=["time", "pixel"],
                coords={"time": WEEKLY_DATES, "pixel": PIXELS},
            )

        def _sda(values: np.ndarray) -> xr.DataArray:
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})

        ones = np.ones((N_WEEKS, N_PIXELS))
        inputs = {
            "plant_type": _sda(PLANT_TYPE.astype(float)),  # drives the pft_params node
            "temperature_weekly": _mda(ones * 15.0),
            "gpp_weekly": _mda(ones * 5.0),
            "soil_moisture_weekly": _mda(ones * 100.0),
            "vpd_weekly": _mda(ones * 1000.0),
            "lue_weekly": _mda(ones * 2.0),
            "iwue_weekly": _mda(ones * 100.0),
            "disturbances_weekly": _mda(ones * 0.0),
            "dates_weekly": WEEKLY_DATES,
            "leaf_pool_init": _sda(LEAF_INIT),
            "stem_pool_init": _sda(STEM_INIT),
            "root_pool_init": _sda(ROOT_INIT),
            "latitude": _sda(LATITUDE),
        }
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(["models.sgam"], {}, cache=cache)
            return dr.execute(["leaf_pool_weekly"], inputs=inputs)  # type: ignore[reportArgumentType]

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        np.testing.assert_allclose(
            cached["leaf_pool_weekly"].values,
            uncached["leaf_pool_weekly"].values,
        )
        assert (tmp_path / "cache").exists()
