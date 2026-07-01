---
title: Configuration
icon: lucide/settings
---

# Configuration

A conduit pipeline is described by a [TOML](https://toml.io/en/) configuration file.
Each section in the file activates a pipeline component — selecting which data to load,
which models to run, and which results to save.
Sections that are absent are simply not included in the pipeline, so you can build
a lightweight pipeline from only the components you need.

---

## Built-in modules

### Inputs

Input sections declare where to load data from and which variables to extract.
Include one section per temporal frequency for which you have data.

```toml
[inputs.daily]
path = "data/daily.nc"
vars = [
  "temperature",
  "precipitation",
  "sunshine_fraction",
]

[inputs.weekly]
path = "data/weekly.nc"
vars = [
  "co2",
  "fapar",
  "ppfd",
  "pressure",
  "vpd",
]

[inputs.monthly]
path = "data/monthly.nc"
vars = ["soil_organic_carbon"]

[inputs.static]
path = "data/static.nc"
vars = [
  "elevation",
  "clay_content",
  "soil_depth",
]
```

`path` may point to a NetCDF file (`.nc`, `.netcdf`), a Zarr store (`.zarr` or a bare
directory), or a flat file (`.csv`, `.parquet`). The format is inferred from the
extension — you do not need to specify it explicitly.

Only include the frequencies for which you have data.
A pipeline with only `[inputs.daily]` and `[inputs.static]` is perfectly valid.

---

### Grid

The geospatial layer (CRS-aware `(y, x)` → `pixel` stacking and computed
`latitude`/`longitude` nodes) activates **automatically** whenever an input carries CRS
metadata — it requires the optional `geo` extra, imported lazily only then. Non-gridded
inputs are loaded with their native dimensions and never touch those dependencies. The
`[grid]` section is accepted as an explicit marker but is otherwise optional:

```toml
[grid]
```

---

### Modules

Compose the pipeline from modules. There are two built-ins addressable by short name —
`[[node]]` (config-defined nodes) and `[[resample]]` (temporal resampling) — and any
other section is **your own module**, loaded by its dotted `_import_path`. A module's
keyword-only parameters can be supplied in its section body:

```toml
# An inline node (built-in)
[[node]]
name = "temperature_anomaly_climate"
inputs = ["temperature_climate"]
expression = "temperature_climate - temperature_climate.mean('time')"
units = "degC"

# Your own module, with parameters
[mymodel]
_import_path = "mypackage.mymodel"
threshold = 0.5
```

/// admonition | Parameter namespacing
    type: note

All module parameters are merged into a single flat configuration dictionary, so
parameter names must be unique across all active sections.
If two modules share a parameter name, prefix it to disambiguate
(e.g. `mymodel_threshold`).
///

---

### Resampling

Use `[[resample]]` (an [array of tables](https://toml.io/en/v1.0.0#array-of-tables))
to resample one or more variables from a finer temporal frequency to a coarser one.
Each entry specifies a direction, a list of variables, and an optional aggregation function.

```toml
[[resample]]
from_freq = "daily"
to_freq = "weekly"
vars = ["temperature", "precipitation"]
aggfunc = "mean"  # default; can also be "sum"

[[resample]]
from_freq = "daily"
to_freq = "monthly"
vars = ["precipitation"]
aggfunc = "sum"
```

Supported directions:

| `from_freq` | `to_freq`   |
|-------------|-------------|
| `"daily"`   | `"weekly"`  |
| `"daily"`   | `"monthly"` |
| `"weekly"`  | `"monthly"` |

Omit `[[resample]]` entirely if no resampling is needed.

---

### Outputs

Output sections declare which computed variables to save and where.
Include one section per temporal frequency you want to write to disk.

```toml
[outputs.daily]
path = "results/daily.nc"
vars = ["actual_evapotranspiration", "soil_moisture"]

[outputs.weekly]
path = "results/weekly.nc"
vars = ["gpp", "leaf_pool"]

[outputs.monthly]
path = "results/monthly.nc"
vars = ["soil_organic_carbon"]
```

As with inputs, the output format is inferred from the file extension.
Both `path` and at least one entry in `vars` are required; omit the section entirely
to produce no output at that frequency.

---

### Custom Nodes

Use `[[node]]` (an [array of tables](https://toml.io/en/v1.0.0#array-of-tables))
to create new computed variables from existing DAG nodes using inline Python
expressions or external functions. Each entry defines a single custom node.

#### Inline expressions

The simplest form uses an `expression` — a Python expression evaluated with
the listed `inputs` available as local variables. The `xr` (xarray) module is
automatically available in the expression namespace.

```toml
[[node]]
name = "aridity_index_daily"
inputs = ["precipitation_daily", "actual_evapotranspiration_daily"]
expression = "precipitation_daily / actual_evapotranspiration_daily"

[[node]]
name = "inert_organic_matter"
inputs = ["organic_carbon_stocks"]
expression = "0.049 * organic_carbon_stocks**1.139"
```

Input variable names must include their frequency suffix (e.g. `_daily`, `_weekly`,
`_monthly`) as they appear in the DAG. The `name` is the node name that
downstream models and outputs will reference.

#### Accessing dict-like parameters

Some DAG nodes (e.g. `pft_params`) return dictionaries. You can index into them
within the expression:

```toml
[[node]]
name = "leaf_area_index_weekly"
inputs = ["leaf_pool_weekly", "pft_params"]
expression = 'leaf_pool_weekly / pft_params["leaf_carbon_area"]'
```

#### Calling external functions

For more complex logic, you can delegate to a function in an importable module
by specifying `_import_path` and `function` instead of `expression`:

```toml
[[node]]
name = "custom_index_daily"
inputs = ["temperature_daily", "precipitation_daily"]
_import_path = "mypackage.indices"
function = "compute_custom_index"
```

The referenced function must accept keyword arguments matching the `inputs` list
and return an `xarray.DataArray`.

#### Declaring units

A custom node transforms its inputs, so its output unit cannot be inferred. Add an optional `units` key to make the node a typed producer: its output is stamped with that unit at run time, and the build-time unit check can verify any downstream consumer against it (see [Units](#units)).

```toml
[[node]]
name = "aridity_index_daily"
inputs = ["precipitation_daily", "actual_evapotranspiration_daily"]
expression = "precipitation_daily / actual_evapotranspiration_daily"
units = "1"   # dimensionless ratio
```

`units` is optional: omit it and the node is a unit-unknown pass-through (no static unit coverage). When present it must be a valid UDUNITS/pint unit string, validated when the config is parsed.

/// admonition | Naming and ordering
    type: note

Each `[[node]]` entry produces a DAG node named after its `name` field.
Custom nodes can be used as inputs to models, to other nodes,
or in output sections — as long as the DAG remains acyclic.

If multiple node entries depend on each other, they are executed in the
order they appear in the config file.
///

Omit `[[node]]` entirely if no custom nodes are needed.

---

### Caching

Add a `[cache]` section to cache intermediate results to disk.
On subsequent runs, nodes whose code and inputs are unchanged are read from the cache instead of being recomputed.

```toml
[cache]
path = ".conduit_cache"   # default; resolved relative to the config file
```

This builds on [Hamilton's caching](https://hamilton.apache.org/concepts/caching/): each node is keyed on a fingerprint of its code plus the fingerprints of its inputs, so the cache invalidates automatically when either changes.

#### Why this matters: calibration loops

The main motivation is iterative workflows that re-run the pipeline many times while changing only a few parameters — for example, calibrating one module in an `a → b → c → d` pipeline.
Because only that module's parameters change between iterations, the upstream outputs keep the same fingerprint and are served straight from the cache, so only the changed module (and downstream) is recomputed.
No manual selection of which nodes to cache is required.

#### Options

| Key | Description |
|-----|-------------|
| `path` | Directory for the cache store (default `.conduit_cache`). Relative paths are resolved against the config file's directory. |
| `enabled` | Set to `false` to keep the section but turn caching off. |
| `recompute` | `true`, or a list of node names, to force recomputation (and re-cache) of those nodes even on a hit. |
| `disable` | `true`, or a list of node names, to bypass the cache entirely for those nodes. |

```toml
[cache]
path = "runs/cache"
recompute = ["my_calibrated_node"]   # always re-run this node; reuse cached upstream
```

The `conduit run` command also exposes `--cache/--no-cache` and `--cache-dir` to override these settings without editing the config. Omit `[cache]` entirely to disable caching.

/// admonition | xarray fingerprinting
    type: note

conduit registers a content-based fingerprint for `xarray.DataArray` that hashes both the array's values *and* its metadata (`name`, dimensions, coordinates). 
A change to either the values or the metadata produces a different fingerprint and so misses the cache. 
In practice you are unlikely to alter metadata without also changing values.
///

---

### Memory-bounded execution

Add a `[blocking]` section to process the stacked `pixel` dimension in fixed-size sequential chunks.
Each block's inputs are sliced from the full-grid arrays, executed through the DAG, and the results concatenated along `pixel`.
Peak memory is bounded to a small multiple of one block's footprint regardless of total grid size.

```toml
[blocking]
block_size = 500   # number of pixels processed at a time
```

| Key | Description |
|-----|-------------|
| `block_size` | Number of pixels per block. Required. Smaller values reduce peak memory; the last block may be smaller if `n_pixels` is not divisible. |

For parallelism across pixels, see `[subset]` below — run independent `conduit` processes each covering a different spatial range, and merge the outputs afterwards.

/// admonition | Outputs must vary over pixels
    type: warning

`[blocking]` concatenates results along the `pixel` dimension. If any variable in `[outputs]` has no `pixel` dimension — for example, a spatial aggregate like a grid-mean — it cannot be recombined and conduit will raise a `ValueError`. Remove pixel-aggregated variables from `[outputs]` when using `[blocking]`, or omit `[blocking]` to request them.
///

---

### Spatial subsetting

Add a `[subset]` section to restrict the pipeline to a contiguous slice of the stacked `pixel` dimension.
`load_inputs` reads only that slice from the source file (lazy NetCDF/Zarr I/O means data outside the range is never loaded).

```toml
[subset]
pixel_start = 0    # inclusive
pixel_end   = 500  # exclusive (Python slice convention)
```

| Key | Description |
|-----|-------------|
| `pixel_start` | First pixel index to include (inclusive, zero-based). Required. |
| `pixel_end` | One past the last pixel index (exclusive). Required. Must be greater than `pixel_start`. |

The pixel ordering follows the row-major stacking of the spatial grid (x varies fastest).

#### HPC pattern: parallel shards

Run N independent `conduit run` processes, each with a different `[subset]`. Because the
processes share one config (and therefore one output `path`), conduit writes their outputs
in a **stacked `pixel` layout** so they don't collide, then a `merge` step reassembles the
grid. How that works depends on the output format:

- **NetCDF** — each process writes a uniquely-named file with its pixel range appended,
  e.g. `weekly.nc` → `weekly_p0-500.nc`. No setup is needed beforehand.
- **Zarr** — all processes write into their region of a single, shared store. The store
  must be created **once** up front so each process only fills its own slice.

For the Zarr workflow, create the store before launching the shards:

```bash
conduit create-store config.toml          # build the empty shared store(s)
parallel conduit run config_{}.toml ::: 0 1 2 3   # each shard region-writes its pixels
conduit merge config.toml                  # unstack into a gridded *_gridded.zarr
```

The NetCDF workflow skips `create-store`:

```bash
parallel conduit run config_{}.toml ::: 0 1 2 3   # writes weekly_p<start>-<end>.nc
conduit merge config.toml                  # concatenates parts into weekly.nc, gridded
```

`merge` writes NetCDF results to the config's declared path and Zarr results to a sibling
`*_gridded.zarr` store by default. Pass `--out <path>` (valid only when the config has a
single output section) to choose an explicit destination.

With a SLURM array job, vary `pixel_start`/`pixel_end` via environment variables or
per-task config files.

/// admonition | Chunk alignment for Zarr
    type: note

Concurrent Zarr region writes are only safe when each subset's boundaries fall on the
store's pixel-chunk boundaries (so no two processes touch the same chunk). `create-store`
sets the pixel chunk from `--pixel-chunk` (defaulting to `[blocking].block_size`); a `run`
whose `[subset]` is misaligned to that chunk raises a `ValueError`. Keep your subset ranges
as multiples of the chunk size.
///

---

### Units

Each model node declares the physical units of its inputs and outputs in its signature. The optional `[units]` section controls how those declarations are validated.

```toml
[units]
mode = "strict"   # "strict" | "warn" | "off"  (default: "warn")
exact = false     # require identical unit strings on each edge (default: false)
```

| Key | Description |
|-----|-------------|
| `mode` | Validation strictness. `strict` raises on a unit problem, `warn` emits a warning and continues, `off` disables unit checking. Defaults to `warn`. |
| `exact` | When `true`, a *dimensionally compatible but value-changing* unit (e.g. `hPa` where `Pa` is declared) is rejected rather than silently converted — both at build time (mismatched edges flagged) and at run time (such an input raises). When `false`, compatible units are auto-converted. Equivalent spellings (`pascal` for `Pa`, `dimensionless` for `1`) are always accepted. Defaults to `false`. |

Validation happens at two points:

- **Build time** — when the driver is built, every internal edge where both ends declare a unit is checked for consistency (subject to `mode` and `exact`), so a mismatch is caught before the pipeline runs. Units are propagated through resampling (which preserves units) so resampled edges are covered; a node is covered when its `[[node]]` entry declares `units` (see below). Edges fed by input files are checked at run time instead.
- **Run time** — as each node executes, every `DataArray` input is validated against its declared unit. With `exact = false` a compatible input is converted to the declared unit; with `exact = true` it must already be that unit. Dimensionally incompatible inputs always raise. A `units` attribute that is missing — or present but unparseable (e.g. a non-CF string like `"fraction"`) — cannot be validated, so it follows `mode` (raise / warn / ignore).

You can run these run-time input checks against your real data *without* executing the pipeline using [`conduit run --dry-run`](cli.md#validating-without-running-dry-run) — a fast pre-flight that catches a misconfigured input before a long run.

Both settings can also be overridden per-process via the `SATTERC_UNITS_MODE` and `SATTERC_UNITS_EXACT` environment variables. Omit `[units]` to keep the defaults (`warn`, no exact match).

/// admonition | Affine units (temperature)
    type: warning

Conversions between offset units such as `degC` and `K` apply the offset (`degC → K` adds 273.15), which is correct for an *absolute* temperature but wrong for a temperature *difference* or anomaly. Declare such quantities in the unit they are stored in (no conversion), or set `exact = true` to forbid implicit temperature conversions.
///

---

## Custom modules

You can extend the pipeline with any importable Python module by adding a section
with a `_import_path` key pointing to its dotted module path.
All other keys in the section are passed through to the pipeline as configuration
parameters, exactly as model parameters are.

```toml
[my_custom_model]
_import_path = "mypackage.mymodule"
learning_rate = 0.01
n_iterations = 500
```

The section header (`my_custom_model`) is a free-form human-readable label;
only `_import_path` carries semantic meaning.
The referenced module must follow the same Hamilton DAG conventions as the built-in modules.

/// admonition | Parameter conflicts
    type: warning

Module parameters are merged into a single flat configuration dictionary. Ensure your
parameter names do not clash with those of any other active section.
///
