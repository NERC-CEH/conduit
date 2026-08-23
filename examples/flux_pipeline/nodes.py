"""Hamilton nodes for the documented eddy-covariance flux pipeline.

The functions in this module are ordinary xarray functions.  Their annotations
describe the units and temporal frequency that conduit checks across the whole
DAG before any computation runs.
"""

from typing import Annotated, TypedDict

import xarray as xr
from hamilton.function_modifiers import extract_fields, parameterize_sources
from xarray_annotated.temporal import Freq, declare_freq
from xarray_annotated.units import Unit, declare_units, use_cf_units

use_cf_units()
xr.set_options(keep_attrs=True)


MolarFlux = Annotated[xr.DataArray, Unit("umol m-2 s-1")]


class PartitionedFluxes(TypedDict):
    """Fluxes returned by :func:`partition_fluxes`."""

    gpp: MolarFlux
    reco: MolarFlux


def nee(nee_raw: MolarFlux, qc: xr.DataArray) -> MolarFlux:
    """Keep only records whose quality-control flag is zero."""
    return nee_raw.where(qc == 0)


@extract_fields()
@declare_units
def partition_fluxes(
    nee: MolarFlux,
    tair: Annotated[xr.DataArray, Unit("degC")],
    ppfd: Annotated[xr.DataArray, Unit("umol m-2 s-1")],
) -> PartitionedFluxes:
    """Partition net ecosystem exchange into GPP and respiration."""
    reco = 2.60 * 2.0 ** ((tair - 10.0) / 10.0)
    gpp = (reco - nee).where(ppfd > 5.0, 0.0)
    return {"gpp": gpp, "reco": reco}


@parameterize_sources(
    to_mass_flux_nee={"flux": "nee"},
    to_mass_flux_gpp={"flux": "gpp"},
    to_mass_flux_reco={"flux": "reco"},
)
@declare_units
def to_mass_flux(
    flux: MolarFlux,
) -> Annotated[xr.DataArray, Unit("g m-2 d-1")]:
    """Convert {flux} to grams of carbon per square metre per day."""
    return flux * (1e-6 * 12.011 * 86400.0)


@declare_freq
def nee_daily(
    to_mass_flux_nee: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly NEE to daily means."""
    return to_mass_flux_nee.resample(time="D").mean()


@declare_freq
def gpp_daily(
    to_mass_flux_gpp: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly GPP to daily means."""
    return to_mass_flux_gpp.resample(time="D").mean()


@declare_freq
def reco_daily(
    to_mass_flux_reco: Annotated[xr.DataArray, Unit("g m-2 d-1")],
) -> Annotated[xr.DataArray, Freq("D")]:
    """Aggregate half-hourly respiration to daily means."""
    return to_mass_flux_reco.resample(time="D").mean()


@declare_freq
def gpp_weekly(
    gpp_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Freq("W-SUN")]:
    """Aggregate daily GPP to week-ending-Sunday means."""
    return gpp_daily.resample(time="W-SUN").mean()


def annual_nee(
    nee_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 d-1")]:
    """Calculate the annual NEE total from daily mean fluxes."""
    return nee_daily.sum()


def annual_gpp(
    gpp_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 d-1")]:
    """Calculate the annual GPP total from daily mean fluxes."""
    return gpp_daily.sum()


def annual_reco(
    reco_daily: Annotated[xr.DataArray, Freq("D")],
) -> Annotated[xr.DataArray, Unit("g m-2 d-1")]:
    """Calculate the annual respiration total from daily mean fluxes."""
    return reco_daily.sum()


class Comparison(TypedDict):
    """Summary statistics comparing modelled and satellite GPP."""

    bias: Annotated[xr.DataArray, Unit("g m-2 d-1")]
    rmse: Annotated[xr.DataArray, Unit("g m-2 d-1")]


@extract_fields()
@declare_units
def compare_with_satellite(
    gpp_weekly: Annotated[xr.DataArray, Unit("g m-2 d-1"), Freq("W-SUN")],
    sat_gpp: Annotated[xr.DataArray, Unit("g m-2 d-1"), Freq("W-SUN")],
) -> Comparison:
    """Return the mean bias and RMSE of modelled weekly GPP."""
    difference = gpp_weekly - sat_gpp
    return {"bias": difference.mean(), "rmse": (difference**2).mean() ** 0.5}
