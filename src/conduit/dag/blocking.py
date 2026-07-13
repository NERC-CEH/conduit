"""Blocked driver execution for memory management (Mechanism B).

Partitions a chosen dimension (``dim``, default ``pixel``) into fixed-size blocks
and calls ``dr.execute`` per block sequentially, then concatenates results along
that dimension. Peak memory is bounded to a small multiple of one block's
footprint.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import xarray as xr

if TYPE_CHECKING:
    from hamilton import driver

    from conduit.config import BlockingSpec


def _block_input_names(inputs: dict[str, Any], dim: str = "pixel") -> list[str]:
    """Return the names of inputs that have the ``dim`` dimension."""
    return [
        name
        for name, val in inputs.items()
        if isinstance(val, xr.DataArray) and dim in val.dims
    ]


def _block_dim_size(inputs: dict[str, Any], block_names: list[str], dim: str) -> int:
    """Return the size of ``dim``, shared by every blocked input.

    Taking the first input's length on trust would silently clamp a longer input to
    a shorter one's slices, surfacing (if at all) as a confusing broadcast error
    inside a node. A disagreement is a config error, so say so.
    """
    sizes = {name: inputs[name].sizes[dim] for name in block_names}
    distinct = set(sizes.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={size}" for name, size in sorted(sizes.items()))
        raise ValueError(
            f"Inputs disagree on the size of the blocking dimension {dim!r}: "
            f"{detail}. Every input carrying {dim!r} must span the same domain."
        )
    return distinct.pop()


def _make_blocks(
    inputs: dict[str, Any],
    block_names: list[str],
    block_size: int,
    dim: str = "pixel",
) -> Generator[dict[str, Any]]:
    """Yield sliced input dicts, one per block along ``dim``.

    Partition is deterministic and fixed-size (independent of worker count)
    so cache keys are stable across machines and restarts.
    """
    if not block_names:
        yield inputs
        return

    n = _block_dim_size(inputs, block_names, dim)
    for start in range(0, n, block_size):
        sl = slice(start, start + block_size)
        yield {
            name: val.isel({dim: sl}) if name in block_names else val
            for name, val in inputs.items()
        }


def _concat_results(
    block_results: list[dict[str, Any]],
    final_vars: list[str],
    dim: str = "pixel",
) -> dict[str, Any]:
    """Concatenate per-block results along the ``dim`` dimension."""
    out: dict[str, Any] = {}
    for var in final_vars:
        first = block_results[0][var]
        if not (isinstance(first, xr.DataArray) and dim in first.dims):
            raise ValueError(
                f"Blocking cannot recombine '{var}' "
                f"(dims: {getattr(first, 'dims', '(scalar)')}) — it has no "
                f"{dim!r} dimension. Remove it from [outputs] when using "
                f"[blocking], or disable [blocking] to request "
                f"{dim}-aggregated outputs."
            )
        out[var] = xr.concat([r[var] for r in block_results], dim=dim)
    return out


def execute_blocked(
    dr: driver.Driver,
    inputs: dict[str, Any],
    final_vars: list[str],
    spec: BlockingSpec,
) -> dict[str, Any]:
    """Execute the driver in blocks along ``spec.dim`` and concatenate results.

    Parameters
    ----------
    dr
        A built Hamilton driver.
    inputs
        Full-grid input dict as returned by ``load_inputs``.
    final_vars
        Node names to compute, as returned by ``get_final_vars``.
    spec
        Blocking configuration (``block_size`` and ``dim``).
    """
    block_names = _block_input_names(inputs, spec.dim)
    blocks = list(_make_blocks(inputs, block_names, spec.block_size, spec.dim))
    return _concat_results(
        [dr.execute(final_vars, inputs=bi) for bi in blocks],  # type: ignore[reportArgumentType]
        final_vars,
        spec.dim,
    )
