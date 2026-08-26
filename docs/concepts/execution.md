---
title: Execution and scaling
icon: lucide/cpu
---

# Execution and scaling

A node operates on xarray objects, and those are backed by NumPy or dask arrays interchangeably.
Nothing in the function knows which, how much of the data is in flight at once, or how many processes are involved.

In a hand-written script the loop bounds, chunk sizes and parallelism end up tangled into the science, and scaling up means editing the code that computes the answer.
Pulling the two apart is what makes scale a configuration concern.

Two properties do the work.
The graph is a value, so conduit can slice the inputs, drive the whole graph over one partition, and recombine the results.
And a run is a pure function of its config and inputs, with no shared mutable state, so running disjoint shards in separate processes is safe by construction.

## What a run does

1. **Parse.** Read the TOML into a validated `ParsedConfig`.
2. **Build.** Import the modules, inspect their signatures, connect input loaders, computed nodes and output savers into one graph, and run the build-time contract check.
3. **Execute.** Trace back from the requested outputs and run only the nodes they depend on, in topological order.
4. **Save.** Write each `[outputs.*]` section, stamping the config text and its SHA-256 onto every file, so a result records the pipeline that produced it.

## The four models

| Model | Config | What it bounds | Reach for it when |
|---|---|---|---|
| in-memory serial | nothing | nothing | developing, testing, and every recipe here |
| out-of-core | `chunks` on inputs, or Zarr's native chunking | memory, lazily | the data is larger than RAM but one process is enough |
| blocked | `[blocking]` | peak memory, to roughly one block | you want a hard memory ceiling in one process |
| sharded | `[subset]`, plus `conduit gridded` | wall-clock time | you have many cores, or a cluster |

The first is what you get by default.
The rest compose, so a blocked, dask-backed run over a subset is entirely ordinary.

**Out-of-core** changes nothing about the graph.
Hand a node dask-backed inputs and it streams lazily, unchanged, because an xarray function does not care what is behind the array.

**Blocking** partitions a dimension and drives the whole graph over one block at a time, concatenating the results.
Peak memory is a small multiple of one block's footprint no matter how large the total is.
The cost is that every requested output must vary over the partition dimension, since that is what the results are concatenated along.

**Sharding** partitions the same way and differs only in who runs the parts: many processes concurrently rather than one process sequentially.
Each process runs an ordinary `conduit run` over its own slice, and a `merge` step reassembles the domain afterwards.
For Zarr the shards region-write into one store created up front, which is why that path has a setup step the NetCDF path does not.

Caching sits outside all four.
`[cache]` keys each node on a fingerprint of its code and its inputs, so re-running a pipeline after changing one parameter recomputes that node and its descendants and reads the rest from disk.
It is orthogonal to how the run is partitioned.

[Scale up a pipeline](../guides/run/scale-up.md) has the keys, the commands and the constraints for each.

## The invariant

None of these choices changes the result or the contracts.
Same graph, same before-compute checks, same outputs, different execution strategy.

That is what lets you develop against a tiny in-memory run, keep the fast feedback loop while the science is still moving, and then deploy the identical pipeline across a cluster without touching a node function.

## Where next

- [Scale up a pipeline](../guides/run/scale-up.md) — the practical knobs.
- [Run from the CLI](../guides/run/run-from-the-cli.md) — the everyday command.
- [Drive conduit from Python](../guides/run/drive-from-python.md) — the same steps, without the CLI.
