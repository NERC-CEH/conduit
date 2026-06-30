"""Blocked driver execution for pixel-dimension memory management (Mechanism B).

Partitions the stacked ``pixel`` dimension into fixed-size blocks and calls
``dr.execute`` per block sequentially, then concatenates results along ``pixel``.
Peak memory is bounded to a small multiple of one block's footprint.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import xarray as xr

if TYPE_CHECKING:
    from hamilton import driver

    from breadboard.config import BlockingSpec


def _pixel_input_names(inputs: dict[str, Any]) -> list[str]:
    """Return the names of inputs that have a ``pixel`` dimension."""
    return [
        name
        for name, val in inputs.items()
        if isinstance(val, xr.DataArray) and "pixel" in val.dims
    ]


def _make_blocks(
    inputs: dict[str, Any],
    pixel_names: list[str],
    block_size: int,
) -> Generator[dict[str, Any]]:
    """Yield sliced input dicts, one per pixel block.

    Partition is deterministic and fixed-size (independent of worker count)
    so cache keys are stable across machines and restarts.
    """
    if not pixel_names:
        yield inputs
        return

    n_pixels = inputs[pixel_names[0]].sizes["pixel"]
    for start in range(0, n_pixels, block_size):
        sl = slice(start, start + block_size)
        yield {
            name: val.isel(pixel=sl) if name in pixel_names else val
            for name, val in inputs.items()
        }


def _concat_results(
    block_results: list[dict[str, Any]],
    final_vars: list[str],
) -> dict[str, Any]:
    """Concatenate per-block results along the ``pixel`` dimension."""
    out: dict[str, Any] = {}
    for var in final_vars:
        first = block_results[0][var]
        if not (isinstance(first, xr.DataArray) and "pixel" in first.dims):
            raise ValueError(
                f"Blocking cannot recombine '{var}' "
                f"(dims: {getattr(first, 'dims', '(scalar)')}) — it has no "
                f"'pixel' dimension. Remove it from [outputs] when using "
                f"[blocking], or disable [blocking] to request "
                f"pixel-aggregated outputs."
            )
        out[var] = xr.concat([r[var] for r in block_results], dim="pixel")
    return out


def execute_blocked(
    dr: driver.Driver,
    inputs: dict[str, Any],
    final_vars: list[str],
    spec: BlockingSpec,
) -> dict[str, Any]:
    """Execute the driver in pixel blocks and concatenate results.

    Parameters
    ----------
    dr
        A built Hamilton driver.
    inputs
        Full-grid input dict as returned by ``load_inputs``.
    final_vars
        Node names to compute, as returned by ``get_final_vars``.
    spec
        Blocking configuration (``block_size``).
    """
    pixel_names = _pixel_input_names(inputs)
    blocks = list(_make_blocks(inputs, pixel_names, spec.block_size))
    return _concat_results(
        [dr.execute(final_vars, inputs=bi) for bi in blocks],  # type: ignore[reportArgumentType]
        final_vars,
    )
