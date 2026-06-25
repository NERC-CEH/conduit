"""RothC soil carbon model interface for the SatTerC pipeline."""

from typing import Annotated, TypedDict, cast

import numpy as np
import pandas as pd
import xarray as xr
from hamilton.function_modifiers import extract_fields
from numpy.typing import NDArray
from pandas import DatetimeIndex
from rothc_py import RothC, RothCParams, percent_modern_c
from rothc_py.containers import InputData
from xarray import DataArray

from ._utils import declare_units


class RothCOut(TypedDict):
    """Outputs of the `rothc` node, at monthly resolution.

    All quantities are carbon mass per unit ground area (tonnes of carbon per
    hectare): the first four are the active soil-carbon pools, the fifth is their
    total, and the last is the month's respiration flux.
    """

    decomposable_plant_material_monthly: Annotated[DataArray, "t ha-1"]
    """Decomposable plant material (DPM) pool (tonnes of carbon per hectare)."""
    resistant_plant_material_monthly: Annotated[DataArray, "t ha-1"]
    """Resistant plant material (RPM) pool (tonnes of carbon per hectare)."""
    microbial_biomass_monthly: Annotated[DataArray, "t ha-1"]
    """Microbial biomass (BIO) pool (tonnes of carbon per hectare)."""
    humified_organic_matter_monthly: Annotated[DataArray, "t ha-1"]
    """Humified organic matter (HUM) pool (tonnes of carbon per hectare)."""
    soil_organic_carbon_monthly: Annotated[DataArray, "t ha-1"]
    """Total soil organic carbon: the sum of the DPM, RPM, BIO, HUM and inert
    organic matter pools (tonnes of carbon per hectare)."""
    heterotrophic_respiration_monthly: Annotated[DataArray, "t ha-1"]
    """Carbon released as CO2 by microbial decomposition during the month
    (tonnes of carbon per hectare)."""


# RothC output keys, in the order they are returned by `_rothc_1px` and mapped
# onto the DAG node names below.
_ROTHC_OUTPUT_KEYS: tuple[str, ...] = (
    "DPM_t_C_ha",
    "RPM_t_C_ha",
    "BIO_t_C_ha",
    "HUM_t_C_ha",
    "SOC_t_C_ha",
    "CO2_t_C_ha",
)
_ROTHC_OUTPUT_NAMES: tuple[str, ...] = (
    "decomposable_plant_material_monthly",
    "resistant_plant_material_monthly",
    "microbial_biomass_monthly",
    "humified_organic_matter_monthly",
    "soil_organic_carbon_monthly",
    "heterotrophic_respiration_monthly",
)


def _rothc_1px(
    temperature: NDArray[np.float64],
    precipitation: NDArray[np.float64],
    evaporation: NDArray[np.float64],
    plant_cover: NDArray[np.bool_],
    dpm_rpm_ratio: NDArray[np.float64],
    soil_carbon_input: NDArray[np.float64],
    farmyard_manure_input: NDArray[np.float64],
    clay: float,
    depth: float,
    iom: float,
    *,
    t_mod: list[float],
    n_spinup_months: int,
    dpm_rate: float,
    rpm_rate: float,
    bio_rate: float,
    hum_rate: float,
    evap_factor: float,
    equilibrium_threshold: float,
    zero_threshold: float,
) -> tuple[NDArray[np.float64], ...]:
    """Run RothC for a single pixel.

    The climate/driver arguments are 1D ``(time,)`` arrays for one pixel; ``clay``,
    ``depth`` and ``iom`` are per-pixel scalars. ``t_mod`` (the percent-modern-carbon
    series) depends only on the date range, so it is computed once in `_rothc`
    and passed through unchanged. Returns one ``(time,)`` array per output pool/flux,
    ordered as `_ROTHC_OUTPUT_KEYS`. This is the per-pixel kernel mapped over the
    ``pixel`` dimension by `_rothc` via `xarray.apply_ufunc`.
    """
    params = RothCParams(
        clay=float(clay),
        depth=float(depth),
        iom=float(iom),
        dpm_rate=dpm_rate,
        rpm_rate=rpm_rate,
        bio_rate=bio_rate,
        hum_rate=hum_rate,
        evap_factor=evap_factor,
        equilibrium_threshold=equilibrium_threshold,
        zero_threshold=zero_threshold,
    )
    model = RothC(params)
    data: InputData = {
        "t_tmp": temperature.tolist(),
        "t_rain": precipitation.tolist(),
        "t_evap": evaporation.tolist(),
        "t_PC": plant_cover.astype(int).tolist(),
        "t_DPM_RPM": dpm_rpm_ratio.tolist(),
        "t_C_Inp": soil_carbon_input.tolist(),
        "t_FYM_Inp": farmyard_manure_input.tolist(),
        "t_mod": t_mod,
    }
    spinup_data: InputData = {
        "t_tmp": data["t_tmp"][:n_spinup_months],
        "t_rain": data["t_rain"][:n_spinup_months],
        "t_evap": data["t_evap"][:n_spinup_months],
        "t_PC": data["t_PC"][:n_spinup_months],
        "t_DPM_RPM": data["t_DPM_RPM"][:n_spinup_months],
        "t_C_Inp": data["t_C_Inp"][:n_spinup_months],
        "t_FYM_Inp": data["t_FYM_Inp"][:n_spinup_months],
        "t_mod": data["t_mod"][:n_spinup_months],
    }

    _, outputs = model(data, spinup_data)
    return tuple(np.asarray(outputs[key], dtype=float) for key in _ROTHC_OUTPUT_KEYS)


def _rothc(
    temperature_monthly: DataArray,
    precipitation_monthly: DataArray,
    evaporation_monthly: DataArray,
    plant_cover_monthly: DataArray,
    dpm_rpm_ratio_monthly: DataArray,
    soil_carbon_input_monthly: DataArray,
    farmyard_manure_input_monthly: DataArray,
    clay_content: DataArray,
    soil_depth: DataArray,
    inert_organic_matter: DataArray,
    dates_monthly: pd.Index,
    *,
    n_years_spinup: int,
    dpm_rate: float = 10.0,
    rpm_rate: float = 0.3,
    bio_rate: float = 0.66,
    hum_rate: float = 0.02,
    evap_factor: float = 0.75,
    equilibrium_threshold: float = 1e-6,
    zero_threshold: float = 1e-8,
) -> RothCOut:
    """Map `_rothc_1px` over the stacked ``pixel`` dimension.

    The per-pixel RothC kernel is applied via `xarray.apply_ufunc` with ``time``
    as the input/output core dimension and ``pixel`` as the broadcast (mapped) dim.
    The 2D ``(time, pixel)`` climate/driver inputs declare ``time`` as their core dim;
    the 1D ``(pixel,)`` soil inputs declare no core dim (so each call receives a
    per-pixel scalar). ``t_mod`` and the rate constants are pixel-invariant constants
    passed through ``kwargs``. ``dask="parallelized"`` is a no-op for eager numpy
    inputs but keeps the node compatible with a future dask-backed (chunked-``pixel``)
    execution strategy.
    """
    n_months = temperature_monthly.sizes["time"]

    # NOTE: need to pass a datetime.datetime object (not a numpy.datetime64)
    # DatetimeIndex.to_pydatetime() exists at runtime but is missing from
    # the pandas type stubs, hence the type: ignore.
    start_date = dates_monthly.to_pydatetime()[0]  # type: ignore[reportAttributeAccessIssue]

    # t_mod depends only on the date range, so compute it once and share across pixels.
    t_mod = percent_modern_c(start_date=start_date, n_months=n_months)

    outputs = xr.apply_ufunc(
        _rothc_1px,
        temperature_monthly,
        precipitation_monthly,
        evaporation_monthly,
        plant_cover_monthly,
        dpm_rpm_ratio_monthly,
        soil_carbon_input_monthly,
        farmyard_manure_input_monthly,
        clay_content,
        soil_depth,
        inert_organic_matter,
        input_core_dims=[["time"]] * 7 + [[]] * 3,
        output_core_dims=[["time"]] * 6,
        kwargs={
            "t_mod": t_mod,
            "n_spinup_months": n_years_spinup * 12,
            "dpm_rate": dpm_rate,
            "rpm_rate": rpm_rate,
            "bio_rate": bio_rate,
            "hum_rate": hum_rate,
            "evap_factor": evap_factor,
            "equilibrium_threshold": equilibrium_threshold,
            "zero_threshold": zero_threshold,
        },
        vectorize=True,
        dask="parallelized",
        output_dtypes=[float] * 6,
    )

    # apply_ufunc drops the `time` coordinate (a core dim) and orders outputs as
    # (pixel, time); reattach the coordinate and restore the canonical (time, pixel).
    time_coord = temperature_monthly.coords["time"]
    return cast(
        RothCOut,
        {
            name: da.assign_coords(time=time_coord).transpose("time", "pixel")
            for name, da in zip(_ROTHC_OUTPUT_NAMES, outputs, strict=True)
        },
    )


@extract_fields()
@declare_units
def rothc(
    temperature_monthly: Annotated[DataArray, "degC"],
    precipitation_monthly: Annotated[DataArray, "mm"],
    evaporation_monthly: Annotated[DataArray, "mm"],
    plant_cover_monthly: DataArray,
    dpm_rpm_ratio_monthly: DataArray,
    soil_carbon_input_monthly: Annotated[DataArray, "t ha-1"],
    farmyard_manure_input_monthly: Annotated[DataArray, "t ha-1"],
    clay_content: Annotated[DataArray, "percent"],
    inert_organic_matter: Annotated[DataArray, "t ha-1"],
    soil_depth: Annotated[DataArray, "cm"],
    dates_monthly: pd.Index,
    *,
    n_years_spinup: int = 1,
    dpm_rate: float = 10.0,
    rpm_rate: float = 0.3,
    bio_rate: float = 0.66,
    hum_rate: float = 0.02,
    evap_factor: float = 0.75,
    equilibrium_threshold: float = 1e-6,
    zero_threshold: float = 1e-8,
) -> RothCOut:
    """
    Rothamsted Carbon model.

    Monthly resolution input data.

    Parameters
    ----------
    temperature_monthly
        Monthly mean air temperature (degrees Celsius).
    precipitation_monthly
        Monthly total precipitation (millimetres).
    evaporation_monthly
        Monthly total open-pan evaporation (millimetres).
    plant_cover_monthly
        Monthly plant cover as boolean (True = soil covered by vegetation).
    dpm_rpm_ratio_monthly
        Ratio of decomposable to resistant plant material (dimensionless).
    soil_carbon_input_monthly
        Carbon input amount for the month (tonnes of carbon per hectare).
    farmyard_manure_input_monthly
        Farmyard manure carbon input amount for the month (tonnes of carbon per
        hectare).
    clay_content
        Soil clay content (percent).
    soil_depth
        Soil depth (centimetres).
    inert_organic_matter
        Inert organic matter (tonnes of carbon per hectare).
    n_years_spinup
        Number of years to use for model spin-up.
    dpm_rate
        Decomposition rate constant for Decomposable Plant Material (per year).
    rpm_rate
        Decomposition rate constant for Resistant Plant Material (per year).
    bio_rate
        Decomposition rate constant for Microbial Biomass (per year).
    hum_rate
        Decomposition rate constant for Humified Organic Matter (per year).
    evap_factor
        Factor to convert open-pan evaporation to evapotranspiration
        (dimensionless).
    equilibrium_threshold
        Spin-up convergence criterion: maximum annual change in total organic
        carbon (tonnes of carbon per hectare).
    zero_threshold
        Minimum pool size for numerical stability in radiocarbon age
        calculations (tonnes of carbon per hectare).

    Returns
    -------
    RothCOut
        Dictionary of monthly outputs (all in tonnes of carbon per hectare):

        - decomposable_plant_material_monthly: DPM pool
        - resistant_plant_material_monthly: RPM pool
        - microbial_biomass_monthly: microbial biomass (BIO) pool
        - humified_organic_matter_monthly: HUM pool
        - soil_organic_carbon_monthly: total soil organic carbon (sum of pools)
        - heterotrophic_respiration_monthly: CO2 from microbial decomposition

        See `RothCOut` for per-output detail.

    Notes
    -----
    All outputs are at monthly resolution and in tonnes of carbon per hectare.
    """
    return _rothc(
        temperature_monthly=temperature_monthly,
        precipitation_monthly=precipitation_monthly,
        evaporation_monthly=evaporation_monthly,
        plant_cover_monthly=plant_cover_monthly,
        dpm_rpm_ratio_monthly=dpm_rpm_ratio_monthly,
        soil_carbon_input_monthly=soil_carbon_input_monthly,
        farmyard_manure_input_monthly=farmyard_manure_input_monthly,
        clay_content=clay_content,
        soil_depth=soil_depth,
        inert_organic_matter=inert_organic_matter,
        dates_monthly=dates_monthly,
        n_years_spinup=n_years_spinup,
        dpm_rate=dpm_rate,
        rpm_rate=rpm_rate,
        bio_rate=bio_rate,
        hum_rate=hum_rate,
        evap_factor=evap_factor,
        equilibrium_threshold=equilibrium_threshold,
        zero_threshold=zero_threshold,
    )


# --- Bridge nodes, needed for RothC --- #
# Ideally refactored in future to be more flexible, configurable via config.toml etc.


def plant_cover_monthly(
    plant_type: DataArray,
    latitude: DataArray,
    dates_monthly: DatetimeIndex,
) -> DataArray:
    """Return monthly plant cover as a boolean mask, accounting for crop seasonality.

    Tree (0), grass (1), and shrub (2) are always considered to cover the soil.
    Crops (3) have a bare season that depends on hemisphere:
      - Northern hemisphere (lat >= 0): bare Nov-Feb
      - Southern hemisphere (lat < 0): bare May-Aug

    Parameters
    ----------
    plant_type
        Plant functional type as integer (0=tree, 1=grass, 2=shrub, 3=crop).
        Dims: ["pixel"].
    latitude
        Latitude for each pixel. Dims: ["pixel"].
    dates_monthly
        Monthly datetime index.

    Returns
    -------
    DataArray
        Boolean plant cover with shape (time, pixel).
    """
    n_months = len(dates_monthly)
    n_pixels = len(plant_type)
    months = np.array([d.month for d in dates_monthly])

    is_crop = plant_type.values == 3
    nh = latitude.values >= 0

    bare_months_nh = np.isin(months, [11, 12, 1, 2])
    bare_months_sh = np.isin(months, [5, 6, 7, 8])

    cover = np.ones((n_months, n_pixels), dtype=bool)

    for i in range(n_pixels):
        if is_crop[i]:
            if nh[i]:
                cover[:, i] = ~bare_months_nh
            else:
                cover[:, i] = ~bare_months_sh

    return xr.DataArray(
        data=cover,
        dims=["time", "pixel"],
        coords={"time": dates_monthly, "pixel": plant_type.coords["pixel"]},
    )


def dpm_rpm_ratio_monthly(
    plant_type: DataArray,
    dates_monthly: DatetimeIndex,
    *,
    dpm_rpm_ratio_tree: float = 0.25,
    dpm_rpm_ratio_grass: float = 1.44,
    dpm_rpm_ratio_shrub: float = 0.67,
    dpm_rpm_ratio_crop: float = 1.44,
) -> DataArray:
    """Return the DPM/RPM ratio for RothC based on plant type.

    Default ratios follow the RothC documentation:
      - Tree (0) → 0.25 (woodland)
      - Grass (1) → 1.44 (improved grassland)
      - Shrub (2) → 0.67 (scrub)
      - Crop (3) → 1.44 (crop)

    Each ratio can be overridden via config, e.g.:
        [models.rothc]
        dpm_rpm_ratio_grass = 0.67

    Parameters
    ----------
    plant_type
        Plant functional type as integer (0=tree, 1=grass, 2=shrub, 3=crop).
        Dims: ["pixel"].
    dates_monthly
        Monthly datetime index.
    dpm_rpm_ratio_tree
        DPM/RPM ratio for tree/woodland.
    dpm_rpm_ratio_grass
        DPM/RPM ratio for grass.
    dpm_rpm_ratio_shrub
        DPM/RPM ratio for shrub/scrub.
    dpm_rpm_ratio_crop
        DPM/RPM ratio for crop.

    Returns
    -------
    DataArray
        DPM/RPM ratio with shape (time, pixel).
    """
    ratio_map = {
        0: dpm_rpm_ratio_tree,
        1: dpm_rpm_ratio_grass,
        2: dpm_rpm_ratio_shrub,
        3: dpm_rpm_ratio_crop,
    }
    values = np.array([ratio_map[int(t)] for t in plant_type.values])
    return xr.DataArray(
        data=np.tile(values, (len(dates_monthly), 1)),
        dims=["time", "pixel"],
        coords={"time": dates_monthly, "pixel": plant_type.coords["pixel"]},
    )


@declare_units
def farmyard_manure_input_monthly(
    plant_type: DataArray,
    dates_monthly: DatetimeIndex,
) -> Annotated[DataArray, "t ha-1"]:
    """Return a zero-filled monthly farmyard manure carbon input.

    In a future version, this could be driven by a grazing/manure C flux
    estimated by SGAM for grass-dominated pixels. Such a flux would need
    to be exposed as a monthly SGAM output and wired here.

    Parameters
    ----------
    plant_type
        Plant functional type as integer (0=tree, 1=grass, 2=shrub, 3=crop).
        Used only for its shape and coordinates. Dims: ["pixel"].
    dates_monthly
        Monthly datetime index.

    Returns
    -------
    DataArray
        Monthly farmyard manure carbon input, all zeros, with shape
        (time, pixel) (tonnes of carbon per hectare).
    """
    # Built from ``plant_type`` only for its shape/coords; drop its inherited
    # attrs so the zeros are stamped with this node's declared unit (``t ha-1``)
    # rather than ``plant_type``'s "dimensionless".
    zeros = xr.zeros_like(plant_type.expand_dims(time=dates_monthly), dtype=float)
    zeros.attrs.clear()
    return zeros
