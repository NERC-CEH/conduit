---
title: Scaling model
icon: lucide/gauge
---

# Scaling model

conduit's third promise is that the *same* functions run at every scale — laptop to
cluster — and you move between scales by changing config, not code. This page explains
why that is possible and what the knobs trade off. For the how-to, see
[Scale up a pipeline](../guides/scale-up.md).

## Why scale is (almost) free

The key structural fact is that **the graph is separate from the functions**. A node is
a plain xarray function; it says nothing about *how* it executes. That decision — where
the data lives, how much runs at once, how many processes participate — is made by the
runtime around the graph, so it can change without touching a single node.

Three consequences:

- Nodes operate on xarray objects, which are backed by NumPy **or** dask arrays
  interchangeably. Hand a node a dask-backed array and it executes lazily and
  out-of-core, with no change to the function.
- Because conduit knows the whole graph, it can slice inputs, run the graph on a chunk,
  and recombine — the graph is a value it can drive repeatedly over partitions.
- Because a run is a pure function of its config and inputs, running disjoint spatial
  shards in separate processes is safe: there is no shared mutable state.

Contrast this with a hand-written script, where the *how* (loops, chunk sizes,
parallelism) is tangled into the *what* (the science). Separating them is what makes
scale a configuration concern.

## The knobs

Four independent config knobs, from smallest to largest scale:

- **Caching** (`[cache]`) — persist node results keyed by a fingerprint of their code
  and inputs. Unchanged nodes are served from disk. The payoff is iterative workflows
  (calibration loops) that re-run the pipeline while changing only a few parameters —
  only the changed sub-graph recomputes.
- **Out-of-core (dask)** — back inputs with dask chunks so arrays larger than memory
  stream through the graph lazily. No config section of its own; it is a property of the
  arrays you feed in.
- **Memory-bounded blocking** (`[blocking]`) — split a partition dimension into
  fixed-size sequential blocks, run the graph per block, concatenate. Peak memory is
  bounded to one block regardless of total size — the tool when a node materialises data
  and you cannot rely on dask laziness alone.
- **Parallel subset runs** (`[subset]` + `conduit gridded`) — run independent processes,
  each over a disjoint slice of the stacked `pixel` dimension, region-writing into one
  shared Zarr store (or separate NetCDF parts), then merge. This is the cross-process,
  cross-machine (e.g. SLURM array) scale.

They compose: a blocked, dask-backed run over a subset, with caching on, is entirely
ordinary.

## What stays fixed

Crucially, none of these knobs changes the **result** or the **contracts**. The same
graph, the same before-compute checks, the same outputs — only the execution strategy
differs. That invariance is what lets you develop against a tiny in-memory run and
deploy the identical pipeline across a cluster with confidence.

## See also

- [Scale up a pipeline](../guides/scale-up.md) — the practical guide to each knob.
- [Why conduit?](why-conduit.md) — where scaling sits among conduit's three promises.
