---
title: Scale up a pipeline
icon: lucide/gauge
---

# Scale up a pipeline

The same functions that run on a laptop run across a cluster.
You change the config, not the code.

There are four knobs, in rough order of the scale they address: result caching, out-of-core dask, memory-bounded blocking, and parallel subset runs over a shared Zarr store.
They compose, so a blocked, dask-backed run over a subset with caching on is entirely ordinary.

None of them changes the result or the contracts: same graph, same before-compute checks, same outputs, different execution strategy.
So you can develop against a tiny in-memory run and deploy the identical pipeline at scale.
[How it works](../../how-it-works.md) explains why that is possible.

## Caching results

Add a `[cache]` section to persist intermediate results to disk. On later runs, nodes
whose code and inputs are unchanged are read from the cache instead of recomputed.

```toml
[cache]
path = ".conduit_cache"   # default; resolved relative to the config file
```

This builds on [Hamilton's caching](https://hamilton.apache.org/concepts/caching/):
each node is keyed on a fingerprint of its code plus its inputs' fingerprints, so the
cache invalidates automatically when either changes. conduit registers a content-based
fingerprint for `xarray.DataArray` that hashes both values *and* metadata.

The main payoff is calibration loops, where you re-run a pipeline many times while
changing only a few parameters. In an `a → b → c → d` chain, tweaking `c`'s parameters
leaves `a` and `b` with the same fingerprint, so they come from the cache and only `c`
and downstream recompute. You do not have to choose which nodes to cache.

| Key | Description |
|-----|-------------|
| `path` | Cache directory (default `.conduit_cache`, resolved against the config file). |
| `enabled` | Set `false` to keep the section but turn caching off. |
| `recompute` | `true` or a list of node names — force recompute (and re-cache) even on a hit. |
| `disable` | `true` or a list of node names — bypass the cache entirely for those nodes. |

CLI overrides (`--cache`/`--no-cache`, `--cache-dir`) let you toggle caching without
editing the config.

## Out-of-core with dask

Nodes are plain xarray functions, so passing dask-backed arrays makes them execute
lazily and out-of-core with no code change. Open inputs with a `chunks` argument, or rely
on Zarr's native chunking. Combine with blocking (below) to cap peak memory.

## Memory-bounded execution with `[blocking]`

Add `[blocking]` to process a partition dimension in fixed-size sequential chunks. Each
block is sliced from the full arrays, run through the DAG, and the results concatenated
along the partition dim. Peak memory is bounded to a small multiple of one block's
footprint, regardless of total size.

```toml
[blocking]
block_size = 500     # rows of the partition dim processed at a time
dim = "pixel"        # default; set to any dim (e.g. "location") for non-gridded data
```

/// admonition | Outputs must vary over the partition dim
    type: warning

Blocking concatenates results along `dim`. If an `[outputs]` variable has no such
dimension — e.g. a grid-mean aggregate — it cannot be recombined and conduit raises a
`ValueError`. Drop such variables from `[outputs]` when blocking.
///

## Parallel subset runs

For parallelism across the domain, run *independent* `conduit run` processes, each
restricted to a contiguous slice of one dimension with `[subset]`:

```toml
[subset]
start = 0            # inclusive, zero-based
stop  = 500          # exclusive (Python slice convention)
dim   = "pixel"      # optional; the default. Any dimension works.
```

As with `[blocking]`, `dim` is free, so a non-gridded pipeline can shard over `location`
or `site`. The two mechanisms partition identically and differ only in who runs the
parts: one process sequentially, or many processes concurrently.

`load_inputs` reads only that slice (lazy NetCDF/Zarr I/O means the rest is never
loaded). Because the processes share one config — and one output `path` — conduit
writes their outputs so they don't collide, then a `merge` step reassembles the grid.
This is behind the optional `geo` extra and the `conduit gridded` command group.

**NetCDF** — each process writes a uniquely-named part (`weekly.nc` →
`weekly_pixel0-500.nc`); no setup needed beforehand:

```sh
parallel conduit run config_{}.toml ::: 0 1 2 3   # writes weekly_<dim><start>-<stop>.nc
conduit gridded merge config.toml                  # concatenate the parts back into weekly.nc
```

`merge` refuses to proceed unless the parts *cover* the dimension end to end: a shard
that died leaves a gap, and merging it anyway would silently produce unwritten (NaN)
regions in the output.

**Zarr** — all processes region-write into one shared store, which must be created
**once** up front. A Zarr store *is* the stacked pixel grid, so this path is `pixel`-only
(`create-store` rejects any other `dim`):

```sh
conduit gridded create-store config.toml           # build the empty shared store(s)
parallel conduit run config_{}.toml ::: 0 1 2 3    # each shard region-writes its pixels
conduit gridded merge config.toml                  # unstack into a sibling *_gridded.zarr
```

`merge` writes NetCDF to the config's declared path and Zarr to a sibling
`*_gridded.zarr`; pass `--out <path>` (single-output configs only) to choose a
destination.

/// admonition | What `create-store` computes
    type: note

`create-store` derives each output's non-`pixel` axes by running the pipeline over a
single pixel and reading the coordinates, dims and dtype off the result, so the layout
matches what the shards will write. A derived axis — a `[[resample]]`'s weekly time axis,
say — works without any input file already having it.

The store therefore belongs to the config that created it. Change the config in a way
that moves an output's time axis and the next `run` refuses to write into the stale
store. Re-create it with `--overwrite`.
///

/// admonition | Chunk alignment for Zarr
    type: note

Concurrent Zarr region writes are only safe when each subset's boundaries fall on the
store's pixel-chunk boundaries. `conduit gridded create-store` sets that chunk from
`--pixel-chunk` (default: `[blocking].block_size`); a `run` whose `[subset]` is
misaligned raises a `ValueError`. Keep subset ranges as multiples of the chunk size.
///

With a SLURM array job, vary `start`/`stop` via environment variables or per-task
config files.

## Where next

- [How it works](../../how-it-works.md) — why execution is a separate decision from the science.
- [Configuration reference](../../reference/configuration.md) — the `[cache]`, `[blocking]` and `[subset]` keys.
- [CLI reference](../../reference/cli.md) — every `conduit gridded` flag.
