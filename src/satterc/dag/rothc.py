"""RothC soil carbon model interface for the SatTerC pipeline."""

import numpy as np
import pandas as pd
import xarray as xr
from hamilton.function_modifiers import extract_fields
from numpy.typing import NDArray
from pandas import DatetimeIndex
from rothc_py import RothC, RothCParams, percent_modern_c
from rothc_py.containers import InputData
from xarray import DataArray

from ._utils import xarray_io


@xarray_io()
def _rothc(
    temperature_celcius_monthly: NDArray[np.float64],
    precipitation_mm_monthly: NDArray[np.float64],
    evaporation_monthly: NDArray[np.float64],
    plant_cover_monthly: NDArray[np.bool],
    dpm_rpm_ratio_monthly: NDArray[np.float64],
    soil_carbon_input_monthly: NDArray[np.float64],
    farmyard_manure_input_monthly: NDArray[np.float64],
    clay_content: NDArray[np.float64],
    soil_depth: NDArray[np.float64],
    inert_organic_matter: NDArray[np.float64],
    dates_monthly: DatetimeIndex,
    *,
    n_years_spinup: int,
    dpm_rate: float = 10.0,
    rpm_rate: float = 0.3,
    bio_rate: float = 0.66,
    hum_rate: float = 0.02,
    evap_factor: float = 0.75,
    equilibrium_threshold: float = 1e-6,
    zero_threshold: float = 1e-8,
) -> dict[str, NDArray]:
    n_months, n_pixels = temperature_celcius_monthly.shape
    n_spinup_months = n_years_spinup * 12

    # NOTE: need to pass a datetime.datetime object (not a numpy.datetime64)
    # DatetimeIndex.to_pydatetime() exists at runtime but is missing from
    # the pandas type stubs, hence the type: ignore.
    start_date = dates_monthly.to_pydatetime()[0]  # type: ignore[reportAttributeAccessIssue]

    t_mod = percent_modern_c(start_date=start_date, n_months=n_months)

    pixel_outputs = []
    for i in range(n_pixels):
        pixel_params = RothCParams(
            clay=clay_content[i],
            depth=soil_depth[i],
            iom=inert_organic_matter[i],
            dpm_rate=dpm_rate,
            rpm_rate=rpm_rate,
            bio_rate=bio_rate,
            hum_rate=hum_rate,
            evap_factor=evap_factor,
            equilibrium_threshold=equilibrium_threshold,
            zero_threshold=zero_threshold,
        )
        model = RothC(pixel_params)
        data: InputData = {
            "t_tmp": temperature_celcius_monthly[:, i].tolist(),
            "t_rain": precipitation_mm_monthly[:, i].tolist(),
            "t_evap": evaporation_monthly[:, i].tolist(),
            "t_PC": plant_cover_monthly[:, i].astype(int).tolist(),
            "t_DPM_RPM": dpm_rpm_ratio_monthly[:, i].tolist(),
            "t_C_Inp": soil_carbon_input_monthly[:, i].tolist(),
            "t_FYM_Inp": farmyard_manure_input_monthly[:, i].tolist(),
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
            "t_mod": t_mod[:n_spinup_months],
        }

        _, outputs = model(data, spinup_data)
        pixel_outputs.append(outputs)

    return dict(
        decomposable_plant_material_monthly=np.column_stack(
            [out["DPM_t_C_ha"] for out in pixel_outputs]
        ),
        resistant_plant_material_monthly=np.column_stack(
            [out["RPM_t_C_ha"] for out in pixel_outputs]
        ),
        microbial_biomass_monthly=np.column_stack(
            [out["BIO_t_C_ha"] for out in pixel_outputs]
        ),
        humified_organic_matter_monthly=np.column_stack(
            [out["HUM_t_C_ha"] for out in pixel_outputs]
        ),
        soil_organic_carbon_monthly=np.column_stack(
            [out["SOC_t_C_ha"] for out in pixel_outputs]
        ),
        heterotrophic_respiration_monthly=np.column_stack(
            [out["CO2_t_C_ha"] for out in pixel_outputs]
        ),
    )


@extract_fields(
    [
        "decomposable_plant_material_monthly",
        "resistant_plant_material_monthly",
        "microbial_biomass_monthly",
        "humified_organic_matter_monthly",
        "soil_organic_carbon_monthly",
        "heterotrophic_respiration_monthly",
    ]
)
def rothc(
    temperature_celcius_monthly: DataArray,
    precipitation_mm_monthly: DataArray,
    evaporation_monthly: DataArray,
    plant_cover_monthly: DataArray,
    dpm_rpm_ratio_monthly: DataArray,
    soil_carbon_input_monthly: DataArray,
    farmyard_manure_input_monthly: DataArray,
    clay_content: DataArray,
    inert_organic_matter: DataArray,
    soil_depth: DataArray,
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
) -> dict[str, DataArray]:
    """
    Rothamsted Carbon model.

    Monthly resolution input data.

    Parameters
    ----------
    temperature_celcius_monthly
        Monthly mean temperature in degrees Celsius.
    precipitation_mm_monthly
        Monthly precipitation in mm.
    evaporation_monthly
        Monthly evaporation in mm.
    plant_cover_monthly
        Monthly plant cover as boolean (True = covered).
    dpm_rpm_ratio_monthly
        Ratio of decomposable to resistant plant material.
    soil_carbon_input_monthly
        Carbon input in tC/ha/month.
    farmyard_manure_input_monthly
        Farmyard manure input in tC/ha/month.
    clay_content
        Clay content percentage.
    soil_depth
        Soil depth in cm.
    inert_organic_matter
        Inert organic matter in tC/ha.
    n_years_spinup
        Number of years to use for model spin-up.
    dpm_rate
        Decomposition rate constant for Decomposable Plant Material (yr⁻¹).
    rpm_rate
        Decomposition rate constant for Resistant Plant Material (yr⁻¹).
    bio_rate
        Decomposition rate constant for Microbial Biomass (yr⁻¹).
    hum_rate
        Decomposition rate constant for Humified Organic Matter (yr⁻¹).
    evap_factor
        Factor to convert open-pan evaporation to evapotranspiration.
    equilibrium_threshold
        Spin-up convergence criterion: maximum annual TOC change (t C/ha).
    zero_threshold
        Minimum pool size for numerical stability in radiocarbon age calculations.

    Returns
    -------
    dict
        Dictionary containing monthly model outputs:
        - decomposable_plant_material_monthly: DPM pool (tC/ha)
        - resistant_plant_material_monthly: RPM pool (tC/ha)
        - microbial_biomass_monthly: Microbial biomass pool (tC/ha)
        - humified_organic_matter_monthly: HUM pool (tC/ha)
        - soil_organic_carbon_monthly: Total SOC (tC/ha)
        - heterotrophic_respiration_monthly: CO₂ from microbial decomposition (tC/ha)

    Notes
    -----
    All outputs have units tC/ha (tonnes of Carbon per hectare).
    All outputs are at monthly resolution.
    """
    return _rothc(
        temperature_celcius_monthly=temperature_celcius_monthly,
        precipitation_mm_monthly=precipitation_mm_monthly,
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


def farmyard_manure_input_monthly(
    plant_type: DataArray,
    dates_monthly: DatetimeIndex,
) -> DataArray:
    """Return array of zeros for farmyard manure input.

    In a future version, this could be driven by a grazing/manure C flux
    estimated by SGAM for grass-dominated pixels. Such a flux would need
    to be exposed as a monthly SGAM output and wired here.
    """
    return xr.zeros_like(plant_type.expand_dims(time=dates_monthly))
