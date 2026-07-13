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

    .. warning::
       Units are preserved unchanged, so ``aggfunc`` must match the *kind* of
       quantity: ``mean`` for a rate, ``sum`` for an amount-per-period. Summing a
       rate is dimensionally consistent — so **no contract check can catch it** —
       and physically meaningless. See the "Resampling & units" guide.
    """
    dim = dim or sole_time_dim(var_in, f"resample input {var_in.name!r}")
    out = getattr(var_in.resample({dim: freq}), aggfunc)()
    # Preserve attrs (notably CF 'units') so contract validation downstream sees
    # the resampled variable's units.
    out.attrs = dict(var_in.attrs)
    return out
