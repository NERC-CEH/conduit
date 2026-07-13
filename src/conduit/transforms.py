"""Reusable DAG transforms referenced from ``[[node]]``/preset config.

A transform is a plain function applied to a node's inputs by a config-generated
node (see `conduit.dag.node`). Transforms that *preserve* their inputs'
declared contracts (units/dims/dtype) are wired in as **passthrough** nodes: the
generated node declares no fixed output contract and is tagged so the contract
check propagates the input's declaration across it
(`conduit.dag.contract_check`). This is what lets the built-in ``[[resample]]``
preset be an ordinary generated node rather than a special-cased DAG module.
"""

import xarray as xr

from .io import sole_time_dim

__all__ = ["resample"]


def resample(
    var_in: xr.DataArray,
    *,
    freq: str,
    aggfunc: str = "mean",
    dim: str | None = None,
) -> xr.DataArray:
    """Resample a DataArray along its time axis to a coarser ``freq``.

    ``aggfunc`` must be a valid xarray ``DataArrayResample`` method (e.g. ``'mean'``,
    ``'sum'``). ``freq`` must be a valid pandas offset alias (e.g. ``'7D'``, ``'1ME'``).

    ``dim`` names the time axis. When omitted it is detected from the array's
    coordinates (`conduit.io.sole_time_dim`), so an axis need not be called
    ``time``; pass ``dim`` explicitly to override.

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
    """
    dim = dim or sole_time_dim(var_in, f"resample input {var_in.name!r}")
    out = getattr(var_in.resample({dim: freq}), aggfunc)()
    # Preserve attrs (notably CF 'units') so contract validation downstream sees
    # the resampled variable's units.
    out.attrs = dict(var_in.attrs)
    return out
