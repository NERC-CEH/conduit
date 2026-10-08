---
title: Scale up a pipeline
icon: lucide/gauge
---

# Scale up a pipeline

Four settings, roughly in order of the scale they address: caching, out-of-core dask, memory-bounded blocking, and parallel subset runs.
They compose, and none of them changes the node code.
To choose between them, see [Execution and scaling](../../concepts/execution.md).

## Caching results

A `[cache]` section persists node results to disk, and later runs read unchanged nodes back instead of recomputing them.

```toml
[cache]
path = ".conduit_cache"   # default; resolved relative to the config file
```

This uses [Hamilton's caching](https://hamilton.apache.org/concepts/caching/): each node is keyed on its code and its inputs' fingerprints, so the cache invalidates itself when either changes.
conduit fingerprints an `xarray.DataArray` by its values *and* metadata.

The payoff is in calibration loops.
In an `a → b → c → d` chain, changing `c`'s parameters leaves `a` and `b` cached, so only `c` and `d` recompute.

| Key | Description |
|-----|-------------|
| `path` | Cache directory (default `.conduit_cache`, resolved against the config file). |
| `enabled` | Set `false` to keep the section but turn caching off. |
| `recompute` | `true` or a list of node names — force recompute (and re-cache) even on a hit. |
| `disable` | `true` or a list of node names — bypass the cache entirely for those nodes. |

`--cache`/`--no-cache` and `--cache-dir` override these from the command line.

## Out-of-core with dask

Nodes are plain xarray functions, so dask-backed inputs make them execute lazily and out-of-core with no code change.
When [driving conduit from Python](drive-from-python.md#step-by-step), `.chunk()` the arrays from `load_inputs` before executing.
Combine with blocking to cap peak memory.

## Memory-bounded execution with `[blocking]`

`[blocking]` runs the whole DAG over one fixed-size block of a dimension at a time and concatenates the results, so peak memory stays near one block's footprint.

```toml
[blocking]
block_size = 500     # rows of the partition dim processed at a time
dim = "pixel"        # default; set to any dim (e.g. "location") for non-gridded data
```

!!! warning "Outputs must vary over the partition dim"

    An output without the `dim` dimension, such as a grid-mean aggregate, cannot be concatenated, and conduit raises an error.
    Drop such variables from `[outputs]` when blocking.

## Parallel subset runs

For parallelism, run independent `conduit run` processes, each restricted by `[subset]` to a contiguous slice of one dimension:

```toml
[subset]
start = 0            # inclusive, zero-based
stop  = 500          # exclusive (Python slice convention)
dim   = "pixel"      # optional; the default. Any dimension works.
```

As with `[blocking]`, `dim` can be any dimension, such as `location` or `site` in a non-gridded pipeline.
Each process reads only its slice.
The processes share one output `path`, so conduit keeps their writes apart, and `conduit gridded merge` (in the `geo` extra) reassembles them afterwards.
In practice, generate one config per task, for example from a SLURM array job.

**NetCDF** — each process writes its own part (`weekly.nc` → `weekly_pixel0-500.nc`), with no setup needed:

```sh
parallel conduit run config_{}.toml ::: 0 1 2 3   # writes weekly_<dim><start>-<stop>.nc
conduit gridded merge config.toml                  # concatenate the parts back into weekly.nc
```

`merge` refuses to run unless the parts cover the dimension end to end, so a shard that died cannot leave a silent gap of NaNs.

**Zarr** — all processes write regions of one shared store, created once up front.
The store's layout is the stacked pixel grid, so this path works only with `dim = "pixel"`:

```sh
conduit gridded create-store config.toml           # build the empty shared store(s)
parallel conduit run config_{}.toml ::: 0 1 2 3    # each shard region-writes its pixels
conduit gridded merge config.toml                  # unstack into a sibling *_gridded.zarr
```

`merge` writes NetCDF to the config's declared path and Zarr to a sibling `*_gridded.zarr`; pass `--out <path>` (single-output configs only) to choose a destination.

!!! note "What `create-store` computes"

    `create-store` runs the pipeline over a single pixel and takes each output's other axes, dims and dtype from the result, so the layout matches what the shards will write, derived axes included.

    The store therefore belongs to the config that created it.
    If a config change moves an output's time axis, `run` refuses to write into the stale store; re-create it with `--overwrite`.

!!! note "Chunk alignment for Zarr"

    Concurrent region writes are safe only when each subset's boundaries fall on the store's pixel-chunk boundaries.
    `create-store` sets the chunk from `--pixel-chunk` (default: `[blocking].block_size`), and a misaligned `[subset]` is an error.
    Keep subset ranges to multiples of the chunk size.
