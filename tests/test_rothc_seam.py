"""Tests for the RothC ``apply_ufunc`` pixel seam (``satterc.dag.rothc._rothc``).

These cover the inner block-level parallelisation seam that replaced the explicit
``for i in range(n_pixels)`` loop:

1. Regression — the seam reproduces, bit-for-bit, an independent per-pixel reference
   loop across *multiple, heterogeneous* pixels (varying per-pixel soil params and
   per-pixel climate). A single-pixel smoke test cannot catch a pixel-misalignment bug,
   so the heterogeneity here is the point.
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
from rothc_py import RothC, RothCParams, percent_modern_c

from satterc.dag.rothc import (
    _ROTHC_OUTPUT_KEYS,
    _ROTHC_OUTPUT_NAMES,
    _rothc,
)

N_MONTHS = 24
N_PIXELS = 3
MONTHLY_DATES = pd.date_range("2020-01-01", periods=N_MONTHS, freq="ME")
PIXELS = np.arange(N_PIXELS)

# Per-pixel soil parameters — deliberately distinct so a mapping bug (e.g. all pixels
# getting pixel 0's clay) would change the outputs and fail the regression check.
CLAY = np.array([30.0, 15.0, 45.0])
DEPTH = np.array([25.0, 30.0, 20.0])
IOM = np.array([2.0, 1.0, 3.5])


def _temporal(base: np.ndarray) -> xr.DataArray:
    """A (time, pixel) DataArray whose columns differ per pixel."""
    return xr.DataArray(
        base,
        dims=["time", "pixel"],
        coords={"time": MONTHLY_DATES, "pixel": PIXELS},
    )


def _static(values: np.ndarray) -> xr.DataArray:
    return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})


@pytest.fixture(scope="module")
def rothc_inputs() -> dict:
    """Heterogeneous multi-pixel inputs (distinct climate per pixel column)."""
    rng = np.random.default_rng(0)

    def _vary(center: float, spread: float) -> np.ndarray:
        # (time, pixel) with a per-pixel offset plus mild noise.
        offsets = np.linspace(-spread, spread, N_PIXELS)
        return (
            center
            + offsets[None, :]
            + rng.normal(0.0, spread / 4, (N_MONTHS, N_PIXELS))
        )

    return dict(
        temperature_monthly=_temporal(_vary(10.0, 4.0)),
        precipitation_monthly=_temporal(np.abs(_vary(50.0, 20.0))),
        evaporation_monthly=_temporal(np.abs(_vary(30.0, 10.0))),
        plant_cover_monthly=_temporal(np.ones((N_MONTHS, N_PIXELS), dtype=bool)),
        dpm_rpm_ratio_monthly=_temporal(np.full((N_MONTHS, N_PIXELS), 1.44)),
        soil_carbon_input_monthly=_temporal(np.abs(_vary(0.2, 0.1))),
        farmyard_manure_input_monthly=_temporal(np.zeros((N_MONTHS, N_PIXELS))),
        clay_content=_static(CLAY),
        soil_depth=_static(DEPTH),
        inert_organic_matter=_static(IOM),
        dates_monthly=MONTHLY_DATES,
        n_years_spinup=1,
    )


def _reference_loop(inputs: dict) -> dict[str, np.ndarray]:
    """Independent per-pixel reference, mirroring the pre-seam ``_rothc`` loop.

    Returns a dict of (time, pixel) numpy arrays, the anchor for the regression check.
    """
    n_spinup_months = inputs["n_years_spinup"] * 12
    start_date = inputs["dates_monthly"].to_pydatetime()[0]
    t_mod = percent_modern_c(start_date=start_date, n_months=N_MONTHS)

    def col(name: str, i: int) -> list:
        return inputs[name].values[:, i].tolist()

    per_pixel: list[dict] = []
    for i in range(N_PIXELS):
        params = RothCParams(
            clay=float(CLAY[i]), depth=float(DEPTH[i]), iom=float(IOM[i])
        )
        model = RothC(params)
        data = {
            "t_tmp": col("temperature_monthly", i),
            "t_rain": col("precipitation_monthly", i),
            "t_evap": col("evaporation_monthly", i),
            "t_PC": inputs["plant_cover_monthly"].values[:, i].astype(int).tolist(),
            "t_DPM_RPM": col("dpm_rpm_ratio_monthly", i),
            "t_C_Inp": col("soil_carbon_input_monthly", i),
            "t_FYM_Inp": col("farmyard_manure_input_monthly", i),
            "t_mod": t_mod,
        }
        spinup = {k: v[:n_spinup_months] for k, v in data.items()}
        _, outputs = model(data, spinup)  # type: ignore[reportArgumentType]
        per_pixel.append(outputs)

    return {
        name: np.column_stack([p[key] for p in per_pixel])
        for name, key in zip(_ROTHC_OUTPUT_NAMES, _ROTHC_OUTPUT_KEYS, strict=True)
    }


class TestRegression:
    """The seam reproduces the per-pixel reference loop, for every output."""

    @pytest.fixture(scope="class")
    def seam_result(self, rothc_inputs):
        return _rothc(**rothc_inputs)

    @pytest.fixture(scope="class")
    def reference(self, rothc_inputs) -> dict:
        return _reference_loop(rothc_inputs)

    @pytest.mark.parametrize("name", _ROTHC_OUTPUT_NAMES)
    def test_matches_reference_loop(self, seam_result, reference, name):
        np.testing.assert_allclose(
            seam_result[name].transpose("time", "pixel").values, reference[name]
        )

    def test_canonical_dims_and_coords(self, seam_result):
        for da in seam_result.values():
            assert da.dims == ("time", "pixel")
            assert da.sizes == {"time": N_MONTHS, "pixel": N_PIXELS}
            # apply_ufunc drops the time coord; the seam must reattach it.
            assert "time" in da.coords
            assert "pixel" in da.coords
            np.testing.assert_array_equal(
                da.coords["time"].values, MONTHLY_DATES.values
            )

    def test_per_pixel_params_actually_differ(self, seam_result):
        # Distinct clay/depth/iom must produce distinct SOC columns; identical columns
        # would mean per-pixel params were not threaded through the seam.
        soc = (
            seam_result["soil_organic_carbon_monthly"].transpose("time", "pixel").values
        )
        assert not np.allclose(soc[:, 0], soc[:, 1])
        assert not np.allclose(soc[:, 1], soc[:, 2])


class TestStrategyCStaysOpen:
    """Chunked (dask-backed) ``pixel`` inputs give identical results to eager numpy."""

    def test_chunked_pixel_equivalence(self, rothc_inputs):
        pytest.importorskip("dask")
        eager = _rothc(**rothc_inputs)

        chunked_inputs = dict(rothc_inputs)
        for key, val in rothc_inputs.items():
            if isinstance(val, xr.DataArray) and "pixel" in val.dims:
                chunked_inputs[key] = val.chunk({"pixel": 1})
        chunked = _rothc(**chunked_inputs)

        for name in _ROTHC_OUTPUT_NAMES:
            out = chunked[name].compute().transpose("time", "pixel").values
            np.testing.assert_allclose(
                out, eager[name].transpose("time", "pixel").values
            )


class TestCachingIntact:
    """The cached rothc node matches the uncached one (seam is internal to the node)."""

    def test_cached_run_matches_uncached(self, tmp_path):
        from satterc import CacheSpec
        from satterc.dag.driver import build_driver

        def _mda(v: float) -> xr.DataArray:
            return xr.DataArray(
                np.full((N_MONTHS, N_PIXELS), float(v)),
                dims=["time", "pixel"],
                coords={"time": MONTHLY_DATES, "pixel": PIXELS},
            )

        def _sda(values: np.ndarray) -> xr.DataArray:
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": PIXELS})

        inputs = {
            "temperature_monthly": _mda(10.0),
            "precipitation_monthly": _mda(50.0),
            "evaporation_monthly": _mda(30.0),
            "soil_carbon_input_monthly": _mda(0.2),
            "clay_content": _sda(CLAY),
            "soil_depth": _sda(DEPTH),
            "inert_organic_matter": _sda(IOM),
            "plant_type": _sda(np.ones(N_PIXELS)),  # for the bridge helper nodes
            "latitude": _sda(np.full(N_PIXELS, 51.5)),
            "dates_monthly": MONTHLY_DATES,
        }
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(["models.rothc"], {"n_years_spinup": 1}, cache=cache)
            return dr.execute(["soil_organic_carbon_monthly"], inputs=inputs)  # type: ignore[reportArgumentType]

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        np.testing.assert_allclose(
            cached["soil_organic_carbon_monthly"].values,
            uncached["soil_organic_carbon_monthly"].values,
        )
        assert (tmp_path / "cache").exists()
