"""§7.5 gating spike: Hamilton ``with_cache`` x ``Parallelizable``/``Collect``.

``notes/parallelism.md`` §7.5 names this "the highest-leverage unknown" and says to
spike it *before* building the outer (grid-level) parallelism layer. Everything in the
§7.7 net decision (eager per-block caching under a ``Parallelizable``/``Collect``
executor — Mechanism D) assumes Hamilton 1.90's ``with_cache`` correctly fingerprints
and stores **per-Parallelizable-branch** outputs and hits them on re-run. Dynamic
execution + caching is exactly the combination prone to version-specific rough edges.

This test runs the trivial DAG from ``tests/_parallel_cache_spike_dag.py`` twice under a
real task executor and asserts:

1. **Per-branch cache hit on re-run** — run 2 (warm cache) re-executes the expensive
   upstream node **zero** times (no new markers), i.e. the cache fingerprints/stores
   each Parallelizable branch and hits it.
2. **Downstream-param change keeps the upstream hit** — changing the
   downstream-of-``Collect`` ``scale`` param recomputes the cheap tail (``total``
   changes) while the expensive upstream node *still* hits cache (no new markers). This
   is the MCMC story: only the cheap tail recomputes per parameter iteration.

It is parameterised over the in-process ``SynchronousLocalTaskExecutor`` and the
cross-process ``MultiProcessingExecutor`` (the §7.6 target) to separate a
cache-vs-dynamic-graph-shape problem from a cross-process serialisation one.

Outcome wiring (per §7.5): if this passes, Mechanism D is viable; if only the
synchronous case passes, the issue is cross-process and the fallback is Mechanism B
(explicit block loop, per-``dr.execute(block)`` caching).
"""

import os

import _parallel_cache_spike_dag as spike_dag
import pytest
from _parallel_cache_spike_dag import N_BLOCKS
from hamilton import driver
from hamilton.execution.executors import (
    MultiProcessingExecutor,
    SynchronousLocalTaskExecutor,
)

EXECUTORS = {
    "synchronous": lambda: SynchronousLocalTaskExecutor(),
    "multiprocessing": lambda: MultiProcessingExecutor(max_tasks=N_BLOCKS),
}


def _count_markers(marker_dir: str) -> int:
    """Number of real (non-cached) executions of the expensive node so far."""
    if not os.path.isdir(marker_dir):
        return 0
    return len([f for f in os.listdir(marker_dir) if f.endswith(".run")])


def _build(cache_path: str, remote_executor):
    return (
        driver.Builder()
        .with_modules(spike_dag)
        .enable_dynamic_execution(allow_experimental_mode=True)
        .with_remote_executor(remote_executor)
        .with_cache(path=cache_path)
        .build()
    )


@pytest.mark.parametrize("executor_name", list(EXECUTORS))
def test_parallel_branch_cache(tmp_path, monkeypatch, executor_name):
    marker_dir = str(tmp_path / "markers")
    cache_path = str(tmp_path / "cache")
    monkeypatch.setenv(spike_dag.MARKER_ENV, marker_dir)

    def run(scale: float) -> float:
        # A fresh Driver per run mimics a re-invoked script / MCMC iteration: the
        # cache must persist on disk across Driver instances, not just in memory.
        dr = _build(cache_path, EXECUTORS[executor_name]())
        return dr.execute(["total"], inputs={"scale": scale})["total"]

    # Run 1 — cold cache: the expensive node runs once per block.
    total_1 = run(scale=1.0)
    assert _count_markers(marker_dir) == N_BLOCKS

    # Run 2 — warm cache, identical inputs: expected ZERO re-executions.
    total_2 = run(scale=1.0)
    assert total_2 == total_1
    assert _count_markers(marker_dir) == N_BLOCKS, (
        "expensive per-branch node re-executed on a warm cache — "
        "with_cache did not hit the Parallelizable branch outputs"
    )

    # Run 3 — change only the downstream-of-Collect `scale`: the cheap tail must
    # recompute (different result) while the expensive upstream node still hits cache.
    total_3 = run(scale=2.0)
    assert total_3 == pytest.approx(2.0 * total_1)
    assert _count_markers(marker_dir) == N_BLOCKS, (
        "changing a downstream-of-Collect param re-ran the upstream expensive node — "
        "the cache key is not isolated to the branch input"
    )
