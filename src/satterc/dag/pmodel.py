"""
Satterc-compatable interface to PyRealm's 'P-model'.

This module provides the pmodel node, which wraps the pyrealm P-Model
to calculate gross primary productivity (GPP), light use efficiency (LUE),
and intrinsic water use efficiency (IWUE) from environmental inputs.
"""

from typing import Annotated, TypedDict, cast

import numpy as np
import pyrealm.pmodel
import xarray as xr
from hamilton.function_modifiers import extract_fields
from numpy.typing import NDArray
from xarray import DataArray

from ._utils import declare_units


class PModelOut(TypedDict):
    """Outputs of the `pmodel` node, at weekly resolution."""

    gpp_weekly: Annotated[DataArray, "g m-2 d-1"]
    """Gross primary productivity: the carbon fixed by photosynthesis, expressed
    as a rate (grams of carbon per square metre per day)."""
    lue_weekly: Annotated[DataArray, "g MJ-1"]
    """Light use efficiency: carbon fixed per unit absorbed PAR (grams of carbon
    per megajoule)."""
    iwue_weekly: Annotated[DataArray, "Pa"]
    """Intrinsic water use efficiency (pascals)."""


def _pmodel_block(
    temperature_weekly: NDArray,
    vpd_weekly: NDArray,
    co2_weekly: NDArray,
    pressure_weekly: NDArray,
    fapar_weekly: NDArray,
    ppfd_weekly: NDArray,
    mean_growth_temperature_weekly: NDArray,
    aridity_index_weekly: NDArray,
    soil_moisture_weekly: NDArray,
    *,
    method_optchi: str,
    method_jmaxlim: str,
    method_kphio: str,
    method_arrhenius: str,
) -> tuple[NDArray, NDArray, NDArray]:
    """Run the P-Model on a whole numpy block (element-wise over every cell).

    pyrealm's P-Model is vectorised over the spatial axis, so this kernel runs on the
    full array — or a single dask chunk — in one call; there is no per-pixel loop.
    Returns ``(gpp, lue, iwue)`` arrays matching the input shape, ordered as the fields
    of `PModelOut`. This is the unit mapped over the block by `_pmodel` via
    `xarray.apply_ufunc`.
    """
    # Environmental drivers computed upon instantiation of PModelEnvironment
    env = pyrealm.pmodel.PModelEnvironment(
        tc=temperature_weekly,
        vpd=vpd_weekly,
        co2=co2_weekly,
        patm=pressure_weekly,
        fapar=fapar_weekly,
        ppfd=ppfd_weekly,
        theta=soil_moisture_weekly / 300,  # TODO: figure out how to remove this factor!
        mean_growth_temperature=mean_growth_temperature_weekly,
        aridity_index=aridity_index_weekly,
    )
    # P-model fit performed upon instantiation of Pmodel
    model = pyrealm.pmodel.PModel(
        env=env,
        method_optchi=method_optchi,
        method_kphio=method_kphio,
        method_arrhenius=method_arrhenius,
        method_jmaxlim=method_jmaxlim,
    )

    # TODO: justify (a) the need for this and (b) why it's reasonable
    gpp = np.nan_to_num(model.gpp, nan=0.0)
    lue = np.nan_to_num(model.lue, nan=0.0)
    iwue = np.nan_to_num(model.iwue, nan=0.0)

    return gpp, lue, iwue


def _pmodel(
    temperature_weekly: DataArray,
    vpd_weekly: DataArray,
    co2_weekly: DataArray,
    pressure_weekly: DataArray,
    fapar_weekly: DataArray,
    ppfd_weekly: DataArray,
    mean_growth_temperature_weekly: DataArray,
    aridity_index_weekly: DataArray,
    soil_moisture_weekly: DataArray,
    method_optchi: str,
    method_jmaxlim: str,
    method_kphio: str,
    method_arrhenius: str,
) -> PModelOut:
    """Apply the P-Model to a ``(time, pixel)`` block via `xarray.apply_ufunc`.

    The P-Model is element-wise (every cell independent), so no core dimensions are
    declared and ``apply_ufunc`` broadcasts over both ``time`` and ``pixel``; pyrealm
    still vectorises within each call. ``dask="parallelized"`` is a no-op for eager
    numpy inputs but keeps the node compatible with a future dask-backed (chunked)
    execution strategy.
    """
    gpp, lue, iwue = xr.apply_ufunc(
        _pmodel_block,
        temperature_weekly,
        vpd_weekly,
        co2_weekly,
        pressure_weekly,
        fapar_weekly,
        ppfd_weekly,
        mean_growth_temperature_weekly,
        aridity_index_weekly,
        soil_moisture_weekly,
        kwargs={
            "method_optchi": method_optchi,
            "method_jmaxlim": method_jmaxlim,
            "method_kphio": method_kphio,
            "method_arrhenius": method_arrhenius,
        },
        output_core_dims=[[], [], []],
        dask="parallelized",
        output_dtypes=[float, float, float],
    )
    return cast(
        PModelOut,
        {"gpp_weekly": gpp, "lue_weekly": lue, "iwue_weekly": iwue},
    )


@extract_fields()
@declare_units
def pmodel(
    temperature_weekly: Annotated[DataArray, "degC"],
    vpd_weekly: Annotated[DataArray, "Pa"],
    co2_weekly: Annotated[DataArray, "ppm"],
    pressure_weekly: Annotated[DataArray, "Pa"],
    fapar_weekly: Annotated[DataArray, "1"],
    ppfd_weekly: Annotated[DataArray, "umol m-2 s-1"],
    mean_growth_temperature_weekly: Annotated[DataArray, "degC"],
    aridity_index_weekly: Annotated[DataArray, "1"],
    soil_moisture_weekly: Annotated[DataArray, "mm"],
    *,
    method_optchi: str = "prentice14",
    method_jmaxlim: str = "wang17",
    method_kphio: str = "temperature",
    method_arrhenius: str = "simple",
) -> PModelOut:
    """Run the P-Model to calculate GPP, LUE, and IWUE.

    Parameters
    ----------
    temperature_weekly
        Air temperature (degrees Celsius).
    vpd_weekly
        Vapour pressure deficit (pascals).
    co2_weekly
        Atmospheric CO2 concentration (parts per million).
    pressure_weekly
        Atmospheric pressure (pascals).
    fapar_weekly
        Fraction of absorbed photosynthetically active radiation
        (dimensionless, 0-1).
    ppfd_weekly
        Photosynthetic photon flux density (micromoles per square metre per
        second).
    mean_growth_temperature_weekly
        Mean growth temperature (degrees Celsius).
    aridity_index_weekly
        Aridity index (dimensionless, ratio of AET to precipitation).
    soil_moisture_weekly
        Soil moisture content (millimetres).
    method_optchi
        Method for calculating optimal chi (leaf-internal CO2 compensation
        point).
    method_jmaxlim
        Method for Jmax limitation.
    method_kphio
        Method for calculating the quantum yield efficiency (phi0).
    method_arrhenius
        Method for Arrhenius temperature scaling.

    Returns
    -------
    PModelOut
        Dictionary of weekly outputs:

        - gpp_weekly: gross primary productivity (grams of carbon per square
          metre per day)
        - lue_weekly: light use efficiency (grams of carbon per megajoule)
        - iwue_weekly: intrinsic water use efficiency (pascals)

        See `PModelOut` for per-output detail.
    """
    return _pmodel(
        temperature_weekly=temperature_weekly,
        vpd_weekly=vpd_weekly,
        co2_weekly=co2_weekly,
        pressure_weekly=pressure_weekly,
        fapar_weekly=fapar_weekly,
        ppfd_weekly=ppfd_weekly,
        mean_growth_temperature_weekly=mean_growth_temperature_weekly,
        aridity_index_weekly=aridity_index_weekly,
        soil_moisture_weekly=soil_moisture_weekly,
        method_optchi=method_optchi,
        method_jmaxlim=method_jmaxlim,
        method_kphio=method_kphio,
        method_arrhenius=method_arrhenius,
    )


def mean_growth_temperature_weekly(
    temperature_daily: xr.DataArray,
) -> xr.DataArray:
    """Calculate the mean temperature on growing degree days where temp > 0°C."""
    # NOTE: this may well be incorrect!! - see https://en.wikipedia.org/wiki/Growing_degree-day
    # Perhaps this depends on growing_season_limit?

    # True on growing degree days (temp > 0.)
    gdd_mask = temperature_daily > 0.0

    # Compute weekly mean, masking non-growing degree days
    # TODO: if the whole week is < 0, this will include NaN.
    # Need to check pmodel can deal with this!
    return temperature_daily.where(gdd_mask).resample(time="7D").mean()
