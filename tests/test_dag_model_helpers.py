"""Tests for model helper functions and model execution.

Covers:
- satterc.dag.rothc  — plant_cover_monthly, dpm_rpm_ratio_monthly, farmyard_manure_input_monthly
- satterc.dag.sgam   — _pft_int_to_enum, _build_pft_params_dataset, _pft_params_from_dataset, pft_params
- satterc.dag.pmodel — mean_growth_temperature_weekly
- model execution smoke tests for splash, pmodel (via pipeline_inputs session fixture)
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from satterc.dag import pmodel as pmodel_module
from satterc.dag import rothc as rothc_module
from satterc.dag import sgam as sgam_module

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

N_PIXELS = 3
N_MONTHS = 24
N_DAYS = 365

PIXEL_COORDS = np.arange(N_PIXELS)
MONTHLY_DATES = pd.date_range("2020-01-01", periods=N_MONTHS, freq="ME")
DAILY_DATES = pd.date_range("2020-01-01", periods=N_DAYS, freq="D")
RNG = np.random.default_rng(42)


def _static(values):
    pixel = np.arange(len(values))
    return xr.DataArray(values, dims=["pixel"], coords={"pixel": pixel})


def _monthly(data):
    return xr.DataArray(
        data,
        dims=["time", "pixel"],
        coords={"time": MONTHLY_DATES, "pixel": PIXEL_COORDS},
    )


def _daily(data):
    return xr.DataArray(
        data,
        dims=["time", "pixel"],
        coords={"time": DAILY_DATES, "pixel": PIXEL_COORDS},
    )


# ---------------------------------------------------------------------------
# RothC helpers
# ---------------------------------------------------------------------------


class TestRothcBridgeFunctions:
    """plant_cover_monthly, dpm_rpm_ratio_monthly, farmyard_manure_input_monthly."""

    @pytest.fixture(scope="class")
    def plant_type_mixed(self):
        return _static(np.array([0.0, 1.0, 2.0, 3.0]))

    @pytest.fixture(scope="class")
    def latitude_nh(self):
        pixel = np.arange(4)
        return xr.DataArray(
            np.array([51.0, 52.0, 53.0, 54.0]), dims=["pixel"], coords={"pixel": pixel}
        )

    @pytest.fixture(scope="class")
    def latitude_sh(self):
        pixel = np.arange(1)
        return xr.DataArray(np.array([-33.0]), dims=["pixel"], coords={"pixel": pixel})

    def test_plant_cover_shape(self, plant_type_mixed, latitude_nh):
        result = rothc_module.plant_cover_monthly(
            plant_type_mixed, latitude_nh, MONTHLY_DATES
        )
        assert result.sizes["pixel"] == 4
        assert result.sizes["time"] == N_MONTHS

    def test_plant_cover_is_dataarray(self, plant_type_mixed, latitude_nh):
        result = rothc_module.plant_cover_monthly(
            plant_type_mixed, latitude_nh, MONTHLY_DATES
        )
        assert isinstance(result, xr.DataArray)

    def test_plant_cover_non_crop_always_one(self, latitude_nh):
        plant_type = _static(np.array([0.0, 1.0, 2.0]))
        lat = xr.DataArray(
            np.array([51.0, 52.0, 53.0]), dims=["pixel"], coords={"pixel": np.arange(3)}
        )
        result = rothc_module.plant_cover_monthly(plant_type, lat, MONTHLY_DATES)
        assert np.all(result.values == 1)

    def test_plant_cover_crop_bare_nh_winter(self, plant_type_mixed, latitude_nh):
        result = rothc_module.plant_cover_monthly(
            plant_type_mixed, latitude_nh, MONTHLY_DATES
        )
        crop_cover = result.sel(pixel=3).values
        months = [d.month for d in MONTHLY_DATES]
        winter_idx = [i for i, m in enumerate(months) if m in (11, 12, 1, 2)]
        for idx in winter_idx:
            assert crop_cover[idx] == 0, (
                f"Expected crop cover=0 in NH winter month {months[idx]}"
            )
        summer_idx = [i for i, m in enumerate(months) if m not in (11, 12, 1, 2)]
        for idx in summer_idx:
            assert crop_cover[idx] == 1, (
                f"Expected crop cover=1 in NH summer month {months[idx]}"
            )

    def test_plant_cover_crop_bare_sh_winter(self, latitude_sh):
        plant_type = _static(np.array([3.0]))
        result = rothc_module.plant_cover_monthly(
            plant_type, latitude_sh, MONTHLY_DATES
        )
        crop_cover = result.sel(pixel=0).values
        months = [d.month for d in MONTHLY_DATES]
        winter_idx = [i for i, m in enumerate(months) if m in (5, 6, 7, 8)]
        for idx in winter_idx:
            assert crop_cover[idx] == 0, (
                f"Expected crop cover=0 in SH winter month {months[idx]}"
            )
        summer_idx = [i for i, m in enumerate(months) if m not in (5, 6, 7, 8)]
        for idx in summer_idx:
            assert crop_cover[idx] == 1, (
                f"Expected crop cover=1 in SH summer month {months[idx]}"
            )

    def test_dpm_rpm_ratio_shape(self, plant_type_mixed):
        result = rothc_module.dpm_rpm_ratio_monthly(plant_type_mixed, MONTHLY_DATES)
        assert result.sizes["pixel"] == 4
        assert result.sizes["time"] == N_MONTHS

    def test_dpm_rpm_ratio_positive(self, plant_type_mixed):
        result = rothc_module.dpm_rpm_ratio_monthly(plant_type_mixed, MONTHLY_DATES)
        assert np.all(result.values > 0)

    def test_dpm_rpm_ratio_values_by_type(self, plant_type_mixed):
        result = rothc_module.dpm_rpm_ratio_monthly(plant_type_mixed, MONTHLY_DATES)
        np.testing.assert_allclose(result.sel(pixel=0).values, 0.25)
        np.testing.assert_allclose(result.sel(pixel=1).values, 1.44)
        np.testing.assert_allclose(result.sel(pixel=2).values, 0.67)
        np.testing.assert_allclose(result.sel(pixel=3).values, 1.44)

    def test_dpm_rpm_ratio_config_override(self, plant_type_mixed):
        result = rothc_module.dpm_rpm_ratio_monthly(
            plant_type_mixed, MONTHLY_DATES, dpm_rpm_ratio_grass=0.67
        )
        np.testing.assert_allclose(result.sel(pixel=1).values, 0.67)

    def test_farmyard_manure_shape(self, plant_type_mixed):
        result = rothc_module.farmyard_manure_input_monthly(
            plant_type_mixed, MONTHLY_DATES
        )
        assert result.sizes["pixel"] == 4
        assert result.sizes["time"] == N_MONTHS

    def test_farmyard_manure_all_zeros(self, plant_type_mixed):
        result = rothc_module.farmyard_manure_input_monthly(
            plant_type_mixed, MONTHLY_DATES
        )
        assert np.all(result.values == 0.0)


# ---------------------------------------------------------------------------
# SGAM helpers
# ---------------------------------------------------------------------------


class TestSgamHelpers:
    """_pft_int_to_enum, _build_pft_params_dataset, pft_params."""

    def test_pft_int_to_enum_returns_enum(self):
        from sgam.pft import PlantFunctionalType

        result = sgam_module._pft_int_to_enum(0)
        assert isinstance(result, PlantFunctionalType)

    def test_pft_int_to_enum_all_valid_indices(self):
        from sgam.pft import PlantFunctionalType

        n_pfts = len(list(PlantFunctionalType))
        for i in range(n_pfts):
            result = sgam_module._pft_int_to_enum(i)
            assert isinstance(result, PlantFunctionalType)

    def test_build_pft_params_dataset_is_dataset(self):
        plant_type = _static(np.array([0.0, 1.0, 2.0]))
        result = sgam_module._build_pft_params_dataset(plant_type)
        assert isinstance(result, xr.Dataset)

    def test_build_pft_params_dataset_pixel_dim(self):
        plant_type = _static(np.array([0.0, 1.0]))
        result = sgam_module._build_pft_params_dataset(plant_type)
        assert "pixel" in result.dims
        assert result.sizes["pixel"] == 2

    def test_build_pft_params_dataset_has_allocation_fields(self):
        plant_type = _static(np.array([0.0]))
        result = sgam_module._build_pft_params_dataset(plant_type)
        for field in [
            "leaf_base_allocation",
            "stem_base_allocation",
            "root_base_allocation",
        ]:
            assert field in result.data_vars

    def test_build_pft_params_dataset_has_turnover_fields(self):
        plant_type = _static(np.array([0.0]))
        result = sgam_module._build_pft_params_dataset(plant_type)
        for field in ["leaf_turnover_rate", "stem_turnover_rate", "root_turnover_rate"]:
            assert field in result.data_vars

    def test_pft_params_from_dataset_round_trips(self):
        from sgam.pft import PftParams

        plant_type = _static(np.array([0.0, 1.0]))
        ds = sgam_module._build_pft_params_dataset(plant_type)
        params = sgam_module._pft_params_from_dataset(ds, 0)
        assert isinstance(params, PftParams)

    def test_pft_params_function_wraps_build(self):
        plant_type = _static(np.array([0.0, 1.0, 2.0]))
        result = sgam_module.pft_params(plant_type)
        assert isinstance(result, xr.Dataset)
        assert result.sizes["pixel"] == 3


# ---------------------------------------------------------------------------
# P-model helpers
# ---------------------------------------------------------------------------


class TestPmodelHelpers:
    """mean_growth_temperature_weekly."""

    def test_returns_dataarray(self):
        da = _daily(RNG.normal(10, 5, (N_DAYS, N_PIXELS)))
        result = pmodel_module.mean_growth_temperature_weekly(da)
        assert isinstance(result, xr.DataArray)

    def test_temporal_coarsening(self):
        da = _daily(np.full((N_DAYS, N_PIXELS), 15.0))
        result = pmodel_module.mean_growth_temperature_weekly(da)
        # Resampled to weekly: ~52 time steps from 365 daily
        assert result.sizes["time"] < N_DAYS
        assert result.sizes["pixel"] == N_PIXELS

    def test_below_zero_becomes_nan(self):
        n_days = 7
        data = np.full((n_days, 1), -5.0)
        da = xr.DataArray(
            data,
            dims=["time", "pixel"],
            coords={
                "time": pd.date_range("2020-01-01", periods=n_days, freq="D"),
                "pixel": [0],
            },
        )
        result = pmodel_module.mean_growth_temperature_weekly(da)
        assert np.all(np.isnan(result.values))

    def test_above_zero_preserved(self):
        n_days = 7
        value = 20.0
        data = np.full((n_days, 1), value)
        da = xr.DataArray(
            data,
            dims=["time", "pixel"],
            coords={
                "time": pd.date_range("2020-01-01", periods=n_days, freq="D"),
                "pixel": [0],
            },
        )
        result = pmodel_module.mean_growth_temperature_weekly(da)
        np.testing.assert_allclose(result.values[~np.isnan(result.values)], value)


# ---------------------------------------------------------------------------
# Splash model execution
# ---------------------------------------------------------------------------


class TestPmodelExecution:
    """Smoke test: _pmodel() runs end-to-end with minimal synthetic inputs."""

    @pytest.fixture(scope="class")
    def pmodel_result(self):
        from satterc.dag.pmodel import _pmodel

        n_weeks = 52
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_weeks, freq="7D")
        pixel = np.arange(n_pixels)

        def _da(data):
            return xr.DataArray(
                data, dims=["time", "pixel"], coords={"time": time, "pixel": pixel}
            )

        return _pmodel(
            temperature_weekly=_da(np.full((n_weeks, n_pixels), 15.0)),
            vpd_weekly=_da(np.full((n_weeks, n_pixels), 1000.0)),
            co2_weekly=_da(np.full((n_weeks, n_pixels), 400.0)),
            pressure_weekly=_da(np.full((n_weeks, n_pixels), 101325.0)),
            fapar_weekly=_da(np.full((n_weeks, n_pixels), 0.5)),
            ppfd_weekly=_da(np.full((n_weeks, n_pixels), 500.0)),
            mean_growth_temperature_weekly=_da(np.full((n_weeks, n_pixels), 15.0)),
            aridity_index_weekly=_da(np.full((n_weeks, n_pixels), 0.5)),
            soil_moisture_weekly=_da(np.full((n_weeks, n_pixels), 100.0)),
            method_optchi="prentice14",
            method_jmaxlim="wang17",
            method_kphio="temperature",
            method_arrhenius="simple",
        )

    def test_returns_dict(self, pmodel_result):
        assert isinstance(pmodel_result, dict)

    def test_output_keys(self, pmodel_result):
        assert "gpp_weekly" in pmodel_result
        assert "lue_weekly" in pmodel_result
        assert "iwue_weekly" in pmodel_result

    def test_gpp_is_dataarray(self, pmodel_result):
        assert isinstance(pmodel_result["gpp_weekly"], xr.DataArray)

    def test_gpp_non_negative(self, pmodel_result):
        assert np.all(pmodel_result["gpp_weekly"].values >= 0)

    def test_output_shape(self, pmodel_result):
        gpp = pmodel_result["gpp_weekly"]
        assert gpp.sizes["time"] == 52
        assert gpp.sizes["pixel"] == 1


class TestRothcExecution:
    """Smoke test: _rothc() runs end-to-end with minimal synthetic inputs."""

    @pytest.fixture(scope="class")
    def rothc_result(self):
        from satterc.dag.rothc import _rothc

        n_months = 24
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_months, freq="ME")
        pixel = np.arange(n_pixels)

        def _da(data):
            return xr.DataArray(
                data, dims=["time", "pixel"], coords={"time": time, "pixel": pixel}
            )

        def _static_da(values):
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": pixel})

        return _rothc(
            temperature_monthly=_da(np.full((n_months, n_pixels), 10.0)),
            precipitation_monthly=_da(np.full((n_months, n_pixels), 50.0)),
            evaporation_monthly=_da(np.full((n_months, n_pixels), 30.0)),
            plant_cover_monthly=_da(np.ones((n_months, n_pixels), dtype=bool)),
            dpm_rpm_ratio_monthly=_da(np.full((n_months, n_pixels), 1.44)),
            soil_carbon_input_monthly=_da(np.full((n_months, n_pixels), 0.2)),
            farmyard_manure_input_monthly=_da(np.zeros((n_months, n_pixels))),
            clay_content=_static_da(np.array([30.0])),
            soil_depth=_static_da(np.array([25.0])),
            inert_organic_matter=_static_da(np.array([2.0])),
            n_years_spinup=1,
            dates_monthly=time,
        )

    def test_returns_dict(self, rothc_result):
        assert isinstance(rothc_result, dict)

    def test_output_keys_present(self, rothc_result):
        for key in [
            "decomposable_plant_material_monthly",
            "resistant_plant_material_monthly",
            "microbial_biomass_monthly",
            "humified_organic_matter_monthly",
            "soil_organic_carbon_monthly",
        ]:
            assert key in rothc_result

    def test_soc_is_dataarray(self, rothc_result):
        assert isinstance(rothc_result["soil_organic_carbon_monthly"], xr.DataArray)

    def test_soc_positive(self, rothc_result):
        assert np.all(rothc_result["soil_organic_carbon_monthly"].values > 0)

    def test_output_shape(self, rothc_result):
        soc = rothc_result["soil_organic_carbon_monthly"]
        assert soc.sizes["time"] == 24
        assert soc.sizes["pixel"] == 1


class TestPmodelDriverExecution:
    """Covers the pmodel() public wrapper (line 120) via Hamilton driver execution."""

    def test_driver_executes_gpp(self):
        from satterc.dag.driver import build_driver

        # 364 days = exactly 52 weeks: ensures the daily→weekly resample produces
        # 52 time steps matching the provided weekly arrays.
        n_weeks = 52
        n_days = 364
        n_pixels = 1
        time_weekly = pd.date_range("2020-01-01", periods=n_weeks, freq="7D")
        time_daily = pd.date_range("2020-01-01", periods=n_days, freq="D")
        pixel = np.arange(n_pixels)

        def _wda(v):
            return xr.DataArray(
                np.full((n_weeks, n_pixels), v),
                dims=["time", "pixel"],
                coords={"time": time_weekly, "pixel": pixel},
            )

        dr = build_driver(
            ["models.pmodel"],
            {
                "method_optchi": "prentice14",
                "method_jmaxlim": "wang17",
                "method_kphio": "temperature",
                "method_arrhenius": "simple",
            },
        )
        result = dr.execute(
            ["gpp_weekly", "lue_weekly", "iwue_weekly"],
            inputs={
                "temperature_weekly": _wda(15.0),
                "temperature_daily": xr.DataArray(
                    np.full((n_days, n_pixels), 15.0),
                    dims=["time", "pixel"],
                    coords={"time": time_daily, "pixel": pixel},
                ),
                "vpd_weekly": _wda(1000.0),
                "co2_weekly": _wda(400.0),
                "pressure_weekly": _wda(101325.0),
                "fapar_weekly": _wda(0.5),
                "ppfd_weekly": _wda(500.0),
                "aridity_index_weekly": _wda(0.5),
                "soil_moisture_weekly": _wda(100.0),
            },
        )
        gpp = result["gpp_weekly"]
        assert isinstance(gpp, xr.DataArray)
        assert np.all(gpp.values >= 0)


class TestRothcDriverExecution:
    """Covers the rothc() public wrapper (line 157) via Hamilton driver execution."""

    def test_driver_executes_soc(self):
        from satterc.dag.driver import build_driver

        n_months = 24
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_months, freq="ME")
        pixel = np.arange(n_pixels)

        def _mda(v):
            return xr.DataArray(
                np.full((n_months, n_pixels), float(v)),
                dims=["time", "pixel"],
                coords={"time": time, "pixel": pixel},
            )

        def _sda(v):
            return xr.DataArray(
                np.full(n_pixels, float(v)),
                dims=["pixel"],
                coords={"pixel": pixel},
            )

        dr = build_driver(["models.rothc"], {"n_years_spinup": 1})
        result = dr.execute(
            ["soil_organic_carbon_monthly"],
            inputs={
                "temperature_monthly": _mda(10.0),
                "precipitation_monthly": _mda(50.0),
                "evaporation_monthly": _mda(30.0),
                "soil_carbon_input_monthly": _mda(0.2),
                "clay_content": _sda(30.0),
                "soil_depth": _sda(25.0),
                "inert_organic_matter": _sda(2.0),
                "plant_type": _sda(1.0),  # needed for helper nodes
                "latitude": _sda(51.5),
                "dates_monthly": time,
            },
        )
        soc = result["soil_organic_carbon_monthly"]
        assert isinstance(soc, xr.DataArray)
        assert np.all(soc.values > 0)


class TestSgamInnerExecution:
    """Smoke test: _sgam() runs end-to-end with minimal synthetic inputs."""

    def test_sgam_inner_returns_dict(self):
        from satterc.dag.sgam import _build_pft_params_dataset, _sgam

        n_weeks = 52
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_weeks, freq="7D")
        pixel = np.arange(n_pixels)

        plant_type_da = xr.DataArray([0.0], dims=["pixel"], coords={"pixel": pixel})
        pft_params_ds = _build_pft_params_dataset(plant_type_da)

        def _da(v):
            return xr.DataArray(
                np.full((n_weeks, n_pixels), v),
                dims=["time", "pixel"],
                coords={"time": time, "pixel": pixel},
            )

        def _sda(v):
            return xr.DataArray(
                np.full(n_pixels, v),
                dims=["pixel"],
                coords={"pixel": pixel},
            )

        result = _sgam(
            plant_type=plant_type_da,
            pft_params=pft_params_ds,
            temperature_weekly=_da(15.0),
            gpp_weekly=_da(5.0),
            soil_moisture_weekly=_da(100.0),
            vpd_weekly=_da(1000.0),
            lue_weekly=_da(2.0),
            iwue_weekly=_da(100.0),
            dates_weekly=time,
            disturbances_weekly=_da(0.0),
            leaf_pool_init=_sda(1.0),
            stem_pool_init=_sda(5.0),
            root_pool_init=_sda(2.0),
            latitude=_sda(51.5),
        )
        assert isinstance(result, dict)
        assert "leaf_pool_weekly" in result
        assert "soil_organic_carbon_monthly" not in result

    def test_sgam_outputs_non_negative_pools(self):
        from satterc.dag.sgam import _build_pft_params_dataset, _sgam

        n_weeks = 52
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_weeks, freq="7D")
        pixel = np.arange(n_pixels)

        plant_type_da = xr.DataArray([0.0], dims=["pixel"], coords={"pixel": pixel})
        pft_params_ds = _build_pft_params_dataset(plant_type_da)

        def _da(v):
            return xr.DataArray(
                np.full((n_weeks, n_pixels), v),
                dims=["time", "pixel"],
                coords={"time": time, "pixel": pixel},
            )

        def _sda(v):
            return xr.DataArray(
                np.full(n_pixels, v),
                dims=["pixel"],
                coords={"pixel": pixel},
            )

        result = _sgam(
            plant_type=plant_type_da,
            pft_params=pft_params_ds,
            temperature_weekly=_da(15.0),
            gpp_weekly=_da(5.0),
            soil_moisture_weekly=_da(100.0),
            vpd_weekly=_da(1000.0),
            lue_weekly=_da(2.0),
            iwue_weekly=_da(100.0),
            dates_weekly=time,
            disturbances_weekly=_da(0.0),
            leaf_pool_init=_sda(1.0),
            stem_pool_init=_sda(5.0),
            root_pool_init=_sda(2.0),
            latitude=_sda(51.5),
        )
        for pool in ["leaf_pool_weekly", "stem_pool_weekly", "root_pool_weekly"]:
            assert np.all(result[pool] >= 0), f"{pool} contains negative values"


class TestDisturbancesDaily:
    """Smoke test: disturbances_daily computes disturbance indicators."""

    def test_disturbances_output_shape(self):
        from satterc.dag.sgam import disturbances_daily

        n_days = 365
        n_pixels = 2
        time = pd.date_range("2020-01-01", periods=n_days, freq="D")
        pixel = np.arange(n_pixels)

        def _da(data):
            return xr.DataArray(
                data, dims=["time", "pixel"], coords={"time": time, "pixel": pixel}
            )

        def _static_da(values):
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": pixel})

        result = disturbances_daily(
            temperature_daily=_da(np.full((n_days, n_pixels), 15.0)),
            gpp_daily=_da(np.full((n_days, n_pixels), 5.0)),
            lai_daily=_da(np.full((n_days, n_pixels), 2.0)),
            plant_type=_static_da(np.zeros(n_pixels, dtype=float)),
            latitude=_static_da(np.array([51.5, 52.0])),
        )
        assert isinstance(result, xr.DataArray)
        assert result.sizes["time"] == n_days
        assert result.sizes["pixel"] == n_pixels


class TestSplashExecution:
    """Smoke test: splash() and _splash() run end-to-end with minimal synthetic inputs."""

    @pytest.fixture(scope="class")
    def splash_result(self):
        from satterc.dag.splash import _splash

        n_days = 366  # 2020 is a leap year; SPLASH needs a full year
        n_pixels = 2
        time = pd.date_range("2020-01-01", periods=n_days, freq="D")
        pixel = np.arange(n_pixels)
        rng = np.random.default_rng(0)

        def _da(data):
            return xr.DataArray(
                data, dims=["time", "pixel"], coords={"time": time, "pixel": pixel}
            )

        def _static_da(values):
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": pixel})

        return _splash(
            sunshine_fraction_daily=_da(
                np.clip(rng.normal(0.5, 0.2, (n_days, n_pixels)), 0, 1)
            ),
            temperature_daily=_da(rng.normal(10, 5, (n_days, n_pixels))),
            precipitation_daily=_da(np.abs(rng.normal(2, 1, (n_days, n_pixels)))),
            elevation=_static_da(np.array([50.0, 100.0])),
            latitude=_static_da(np.array([51.5, 52.0])),
            max_soil_moisture=_static_da(np.array([150.0, 150.0])),
            soil_moisture_init_max_iter=5,
            soil_moisture_init_max_diff=1.0,
            dates_daily=time,
        )

    def test_returns_dict(self, splash_result):
        assert isinstance(splash_result, dict)

    def test_output_keys(self, splash_result):
        assert "actual_evapotranspiration_daily" in splash_result
        assert "soil_moisture_daily" in splash_result
        assert "runoff_daily" in splash_result

    def test_aet_is_dataarray(self, splash_result):
        assert isinstance(
            splash_result["actual_evapotranspiration_daily"], xr.DataArray
        )

    def test_aet_non_negative(self, splash_result):
        aet = splash_result["actual_evapotranspiration_daily"]
        assert np.all(aet.values >= 0)

    def test_soil_moisture_bounded(self, splash_result):
        sm = splash_result["soil_moisture_daily"]
        assert np.all(sm.values >= 0)
        assert np.all(sm.values <= 150.0)

    def test_output_shape(self, splash_result):
        aet = splash_result["actual_evapotranspiration_daily"]
        assert aet.sizes["time"] == 366
        assert aet.sizes["pixel"] == 2

    def test_public_splash_wrapper_returns_dict(self):
        """Test the public splash() function (covers the 'return _splash(...)' line)."""
        from satterc.dag.splash import splash

        n_days = 366
        n_pixels = 1
        time = pd.date_range("2020-01-01", periods=n_days, freq="D")
        pixel = np.arange(n_pixels)
        rng = np.random.default_rng(1)

        def _da(data):
            return xr.DataArray(
                data, dims=["time", "pixel"], coords={"time": time, "pixel": pixel}
            )

        def _static_da(values):
            return xr.DataArray(values, dims=["pixel"], coords={"pixel": pixel})

        result = splash(
            dates_daily=time,
            sunshine_fraction_daily=_da(
                np.clip(rng.normal(0.5, 0.2, (n_days, n_pixels)), 0, 1)
            ),
            temperature_daily=_da(rng.normal(10, 5, (n_days, n_pixels))),
            precipitation_daily=_da(np.abs(rng.normal(2, 1, (n_days, n_pixels)))),
            elevation=_static_da(np.array([50.0])),
            latitude=_static_da(np.array([51.5])),
            max_soil_moisture=_static_da(np.array([150.0])),
        )
        assert isinstance(result, dict)
        assert "actual_evapotranspiration_daily" in result
