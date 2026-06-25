"""Temporal resampling module for the Hamilton DAG."""

import xarray as xr
from hamilton.function_modifiers import ResolveAt, parameterize, resolve, source, value

from ._hamilton_fixes import NoOpDecorator


@resolve(
    when=ResolveAt.CONFIG_AVAILABLE,
    decorate_with=lambda resample_specs=None: (
        parameterize(
            **{
                f"{var}_{spec.target_freq}": {
                    "var_in": source(f"{var}_{spec.source_freq}"),
                    "aggfunc": value(spec.aggfunc),
                    "freq": value(spec.freq),
                }
                for spec in resample_specs
                for var in spec.vars
            }
        )
        if resample_specs
        else NoOpDecorator()
    ),
)
def resample(var_in: xr.DataArray, aggfunc: str, freq: str) -> xr.DataArray:
    """Resample a DataArray to a coarser frequency using the given aggregation function.

    aggfunc must be a valid xarray DataArrayResample method (e.g. 'mean', 'sum').
    freq must be a valid pandas offset alias (e.g. '7D', '1ME').

    Units note: reducing along the time axis is dimensionally homogeneous, so both
    'mean' and 'sum' preserve units — hence we copy attrs (incl. CF 'units')
    unchanged. This matches native pint-xarray, which does *not* multiply by the
    timestep on a sum. The choice of aggfunc must therefore match the *kind* of
    quantity:

      - rate / intensive (e.g. 'g C m-2 day-1') -> use 'mean'; the result is the
        mean rate over the window, same units.
      - amount-per-period / extensive (e.g. 'g C m-2' fixed that day) -> use 'sum';
        the result is the window total, same units.

    The footgun is 'sum'-ming a rate to get a window total: the correct operation
    is an integral (Σ rateᵢ·Δt), which would cancel the time dimension, but
    xarray's .sum() omits the Δt factor. The result is dimensionally consistent
    (so unit validation cannot catch it) yet physically meaningless. Pick the
    aggfunc to match the quantity.

    # TODO: consider closed/label options for finer control over bin edges
    """
    out = getattr(var_in.resample(time=freq), aggfunc)()
    # Preserve attrs (notably CF 'units') across this internal edge so unit
    # validation downstream sees the resampled variable's units.
    out.attrs = dict(var_in.attrs)
    return out
