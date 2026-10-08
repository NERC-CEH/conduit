---
title: Execution and scaling
icon: lucide/cpu
---

# Execution and scaling

A node operates on xarray objects, which may be backed by NumPy or dask arrays.
Nothing in the function knows which, how much data is in flight at once, or how many processes are involved.

In a hand-written script, loop bounds, chunk sizes and parallelism get tangled into the science, and scaling up means editing the code that computes the answer.
conduit keeps them apart, which makes scale a configuration concern.
Two properties make this work:

- The graph is a value, so conduit can slice the inputs, drive the whole graph over one partition, and recombine the results.
- A run is a pure function of its config and inputs, with no shared mutable state, so disjoint shards can safely run in separate processes.

## What a run does

1. **Parse.** Read the TOML into a validated `ParsedConfig`.
2. **Build.** Import the modules, connect input loaders, computed nodes and output savers into one graph, and run the contract check.
3. **Execute.** Run only the nodes the requested outputs depend on, in topological order.
4. **Save.** Write each `[outputs.*]` section, stamped with the config text and its SHA-256 so each file records the pipeline that produced it.

## The four models

| Model | Config | What it bounds | Use it when |
|---|---|---|---|
| in-memory serial | nothing | nothing | developing, testing, and every recipe here |
| out-of-core | dask-backed inputs, from Python | memory, lazily | the data is larger than RAM but one process is enough |
| blocked | `[blocking]` | peak memory, to roughly one block | you want a hard memory ceiling in one process |
| sharded | `[subset]`, plus `conduit gridded` | wall-clock time | you have many cores, or a cluster |

The first is the default, and the rest compose: a blocked, dask-backed run over a subset is ordinary.

- **Out-of-core** changes nothing about the graph. Hand a node dask-backed inputs and it streams lazily.
- **Blocking** partitions a dimension and drives the whole graph over one block at a time, concatenating the results. Peak memory is a small multiple of one block, however large the total. Every requested output must therefore vary over the partition dimension.
- **Sharding** partitions the same way, but many processes run the parts concurrently. Each runs an ordinary `conduit run` over its own slice, and a `merge` step reassembles the domain. For Zarr, the shards write into one store created up front.

**Caching** is independent of all four.
`[cache]` keys each node on a fingerprint of its code and inputs, so changing one parameter recomputes that node and its descendants and reads the rest from disk.

[Scale up a pipeline](../guides/run/scale-up.md) has the keys, commands and constraints for each.

## The invariant

None of these choices changes the result or the contracts: same graph, same checks, same outputs.
You can develop against a tiny in-memory run and deploy the same pipeline across a cluster without touching a node function.
