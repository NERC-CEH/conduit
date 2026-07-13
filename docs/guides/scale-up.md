---
title: Scale up a pipeline
icon: lucide/gauge
---

# Scale up a pipeline

The same functions that run on a laptop scale to a cluster — you change the config, not
the code. This guide covers the four scaling knobs: result **caching**, out-of-core
**dask**, memory-bounded **blocking**, and parallel **subset** runs over a shared Zarr
store. For the *why* behind this, see [Scaling model](../concepts/scaling.md).

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

The main payoff is **calibration loops** — re-running a pipeline many times while
changing only a few parameters. In an `a → b → c → d` chain, tweaking `c`'s parameters
leaves `a` and `b` with the same fingerprint, so they are served from cache and only
`c` (and downstream) recompute. No manual selection of which nodes to cache is needed.

| Key | Description |
|-----|-------------|
| `path` | Cache directory (default `.conduit_cache`, resolved against the config file). |
| `enabled` | Set `false` to keep the section but turn caching off. |
| `recompute` | `true` or a list of node names — force recompute (and re-cache) even on a hit. |
| `disable` | `true` or a list of node names — bypass the cache entirely for those nodes. |

CLI overrides (`--cache`/`--no-cache`, `--cache-dir`) let you toggle caching without
editing the config.

## Out-of-core with dask

Because nodes are plain xarray functions, passing dask-backed arrays makes them execute
lazily and out-of-core with no code change — open inputs with a `chunks` argument, or
rely on Zarr's native chunking. Combine with blocking (below) to cap peak memory.

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

## Parallel subset runs over Zarr

For parallelism across the grid, run *independent* `conduit run` processes, each
restricted to a contiguous slice of the stacked `pixel` dimension with `[subset]`:

```toml
[subset]
pixel_start = 0      # inclusive, zero-based
pixel_end   = 500    # exclusive (Python slice convention)
```

`load_inputs` reads only that slice (lazy NetCDF/Zarr I/O means the rest is never
loaded). Because the processes share one config — and one output `path` — conduit
writes their outputs so they don't collide, then a `merge` step reassembles the grid.
This is behind the optional `geo` extra and the `conduit gridded` command group.

**NetCDF** — each process writes a uniquely-named part (`weekly.nc` →
`weekly_p0-500.nc`); no setup needed beforehand:

```sh
parallel conduit run config_{}.toml ::: 0 1 2 3   # writes weekly_p<start>-<end>.nc
conduit gridded merge config.toml                  # concatenate parts into a gridded weekly.nc
```

**Zarr** — all processes region-write into one shared store, which must be created
**once** up front:

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

To lay out the empty store, `create-store` needs each output's non-`pixel` axes — its
time coordinate, above all. It gets them by **running the pipeline over a single pixel**
and reading the real coordinates, dims and dtype off the result. So the store matches
what the shards will write by construction, and a *derived* axis (a `[[resample]]`'s
weekly time axis, say) needs no input file to already have it.

The practical consequence: the store belongs to the config that created it. Change the
config in a way that moves an output's time axis and the next `run` will refuse to write
into the stale store rather than mislabel it — re-create it with `--overwrite`.
///

/// admonition | Chunk alignment for Zarr
    type: note

Concurrent Zarr region writes are only safe when each subset's boundaries fall on the
store's pixel-chunk boundaries. `conduit gridded create-store` sets that chunk from
`--pixel-chunk` (default: `[blocking].block_size`); a `run` whose `[subset]` is
misaligned raises a `ValueError`. Keep subset ranges as multiples of the chunk size.
///

With a SLURM array job, vary `pixel_start`/`pixel_end` via environment variables or
per-task config files.

## See also

- [Scaling model](../concepts/scaling.md) — why the same functions scale for free.
- [Configuration reference](../reference/configuration.md) — the `[cache]`,
  `[blocking]` and `[subset]` keys.
