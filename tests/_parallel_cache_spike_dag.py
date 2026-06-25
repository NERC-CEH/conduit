"""Throwaway Hamilton DAG for the parallelism §7.5 caching spike.

Shape (``notes/parallelism.md`` §7.5):

    pixel_block  (Parallelizable -> N eager per-pixel blocks)
        -> expensive_block_output   (the "expensive" upstream node: sleep + marker)
            -> collected            (Collect)
                -> total            (cheap tail, parameterised by `scale`)

The spike question: under dynamic execution (``Parallelizable``/``Collect``) with a
real task executor, does ``Builder.with_cache`` fingerprint and store the *per-branch*
``expensive_block_output`` and **hit** it on re-run — so the expensive node does not
re-execute, and a change to the downstream-of-``Collect`` ``scale`` param still leaves
the upstream cache hit?

This module must be importable (not defined inside the test) so the
``MultiProcessingExecutor`` can run its nodes under either fork or spawn.

Instrumentation is kept *out* of the cache key on purpose: ``expensive_block_output``
depends only on its ``pixel_block`` (exactly as a real cached upstream node would), and
records each *real* execution as a side effect via a uniquely-named marker file under
``$SPIKE_MARKER_DIR``. A cache **hit** returns the stored output without calling the
function, so it writes no marker — counting marker files counts real executions.
"""

import os
import time
import uuid

import numpy as np
import xarray as xr
from hamilton.htypes import Collect, Parallelizable

# Registering satterc's DataArray fingerprint is what makes a DataArray block
# content-hashable (and therefore cacheable across runs/processes); without it
# Hamilton assigns a random per-result version and the cache never hits. Importing
# here ensures the registration happens in every process that imports this module.
import satterc.dag.caching  # noqa: F401

N_BLOCKS = 3
MARKER_ENV = "SPIKE_MARKER_DIR"


def pixel_block() -> Parallelizable[xr.DataArray]:
    """Emit ``N_BLOCKS`` eager per-pixel blocks via a deterministic partition.

    The partition is fixed (worker-count-independent), so a block's content — and
    hence its cache key — is identical on a 1-worker or an N-worker run.
    """
    for i in range(N_BLOCKS):
        yield xr.DataArray(
            np.arange(4, dtype=float) + i,
            dims=["time"],
            coords={"pixel": i},
            name="pixel_block",
        )


def expensive_block_output(pixel_block: xr.DataArray) -> xr.DataArray:
    """The 'expensive' upstream node: depends only on its block, sleeps, and marks.

    Each *real* (non-cached) execution drops a uniquely-named marker file under
    ``$SPIKE_MARKER_DIR``; a cache hit skips the body and writes nothing.
    """
    marker_dir = os.environ[MARKER_ENV]
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, f"{uuid.uuid4().hex}.run")
    with open(marker, "w") as fh:
        fh.write(str(int(pixel_block.coords["pixel"])))
    time.sleep(0.05)
    return pixel_block * 2.0


def collected(expensive_block_output: Collect[xr.DataArray]) -> list[xr.DataArray]:
    """Collect the per-branch outputs back into a single list."""
    return list(expensive_block_output)


def total(collected: list[xr.DataArray], scale: float) -> float:
    """Cheap tail downstream of ``Collect``, parameterised by ``scale``."""
    return float(sum(da.sum().item() for da in collected) * scale)
