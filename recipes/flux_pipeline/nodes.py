"""Hamilton nodes for the eddy-covariance flux recipe.

Ordinary xarray functions, annotated with the units and time frequencies that
catena checks across the whole DAG before anything runs.
"""

from typing import Annotated, TypedDict

import xarray as xr
import xarray_annotated as xra
from hamilton.function_modifiers import extract_fields, parameterize_sources
from xarray_annotated import Freq, Unit
from xarray_annotated.units import use_cf_units

use_cf_units()
xr.set_options(keep_attrs=True)


MolarFlux = Annotated[xr.DataArray, Unit("umol m-2 s-1")]


class PartitionedFluxes(TypedDict):
    """Fluxes returned by :func:`partition_fluxes`."""

    gpp: MolarFlux
    reco: MolarFlux


@xra.enforce
def nee(nee_raw: MolarFlux, qc: xr.DataArray) -> MolarFlux:
    """Keep only records whose quality-control flag is zero."""
    return nee_raw.where(qc == 0)


@xra.enforce
def tair_celsius(
    tair: Annotated[xr.DataArray, Unit("K")],
) -> Annotated[xr.DataArray, Unit("degC")]:
    """Convert air temperature from kelvin to degrees Celsius."""
    return xra.units.convert(tair, "degC")


@extract_fields()
@xra.enforce
def partition_fluxes(
    nee: MolarFlux,
    tair_celsius: Annotated[xr.DataArray, Unit("degC")],
    ppfd: Annotated[xr.DataArray, Unit("umol m-2 s-1")],
) -> PartitionedFluxes:
    """Partition net ecosystem exchange into GPP and respiration."""
    q10 = 2.0 ** ((tair_celsius - 10.0) / 10.0)
    reco = (2.60 * q10).assign_attrs(units="umol m-2 s-1")
    gpp = (reco - nee).where(ppfd > 5.0, 0.0)
    return {"gpp": gpp, "reco": reco}


@parameterize_sources(
    to_mass_flux_nee={"flux": "nee"},
    to_mass_flux_gpp={"flux": "gpp"},
    to_mass_flux_reco={"flux": "reco"},
)
@xra.enforce
def to_mass_flux(
    flux: MolarFlux,
) -> Annotated[xr.DataArray, Unit("g m-2 d-1")]:
    """Convert {flux} to grams of carbon per square metre per day."""
    return (flux * (1e-6 * 12.011 * 86400.0)).assign_attrs(units="g m-2 d-1")


@xra.enforce
def nee_daily(
    to_mass_flux_nee: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly NEE to daily means."""
    return to_mass_flux_nee.resample(time="D").mean()


@xra.enforce
def gpp_daily(
    to_mass_flux_gpp: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly GPP to daily means."""
    return to_mass_flux_gpp.resample(time="D").mean()


@xra.enforce
def reco_daily(
    to_mass_flux_reco: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly respiration to daily means."""
    return to_mass_flux_reco.resample(time="D").mean()


@xra.enforce
def gpp_weekly(
    gpp_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Freq("W-SUN")]:
    """Aggregate daily GPP to week-ending-Sunday means."""
    return gpp_daily.resample(time="W-SUN").mean()


# Each daily mean is weighted by one day, so a year's sum is a total per year.
# `keep_attrs` would carry the daily unit through the sum, so each annual node
# sets the unit it declares.
@xra.enforce
def annual_nee(
    nee_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 yr-1")]:
    """Calculate the annual NEE total from daily mean fluxes."""
    return nee_daily.sum().assign_attrs(units="g m-2 yr-1")


@xra.enforce
def annual_gpp(
    gpp_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 yr-1")]:
    """Calculate the annual GPP total from daily mean fluxes."""
    return gpp_daily.sum().assign_attrs(units="g m-2 yr-1")


@xra.enforce
def annual_reco(
    reco_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 yr-1")]:
    """Calculate the annual respiration total from daily mean fluxes."""
    return reco_daily.sum().assign_attrs(units="g m-2 yr-1")


class Comparison(TypedDict):
    """Summary statistics comparing modelled and satellite GPP."""

    bias: Annotated[xr.DataArray, Unit("g m-2 d-1")]
    rmse: Annotated[xr.DataArray, Unit("g m-2 d-1")]


@extract_fields()
@xra.enforce
def compare_with_satellite(
    gpp_weekly: Annotated[xr.DataArray, Unit("g m-2 d-1"), Freq("W-SUN")],
    sat_gpp: Annotated[xr.DataArray, Unit("g m-2 d-1"), Freq("W-SUN")],
) -> Comparison:
    """Return the mean bias and RMSE of modelled weekly GPP."""
    difference = gpp_weekly - sat_gpp
    return {"bias": difference.mean(), "rmse": (difference**2).mean() ** 0.5}
