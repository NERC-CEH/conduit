---
title: Configuration
icon: lucide/settings
---

# Configuration reference

A conduit pipeline is described by a [TOML](https://toml.io/en/) file.
Each section switches on one part of the pipeline; leave a section out and that part is not there.

Recognised top-level sections are listed below.
**Any other section is treated as your own module**, named by an `_import_path` key or registered by an installed package (see [Modules](#modules)), so a misspelt section name is an error.

!!! note "Paths are resolved relative to the config file"

    Every relative path in a config — `path` in `[inputs.*]`, `[outputs.*]` and `[cache]`, and a `.py` `_import_path` — is resolved against the config file's directory, not the working directory.

## Inputs

`[inputs.<label>]` declares where to load data from and which variables to expose.
The `<label>` is arbitrary (`climate`, `daily`, `static`, …).

```toml
[inputs.daily]
path = "data/daily.nc"
vars = ["temperature", "precipitation"]

[inputs.static]
path = "data/static.nc"
suffix = ""
vars = ["elevation"]
```

| Key | Description |
|-----|-------------|
| `path` | **Required.** File to load. Format is inferred from the extension — see [Data formats](data-formats.md). |
| `vars` | Which variables to expose, and under what node names (see below). Omit to load them all. |
| `suffix` | Overrides the node-name suffix for the list form of `vars`. |

**`vars` has three forms:**

- A **list** — `vars = ["temperature"]` — names each node `{var}{suffix}`.
  The suffix defaults to `_<label>` (so `temperature` under `[inputs.daily]` → node `temperature_daily`).
  Set `suffix = ""` for bare names on any section (e.g. a `static` section, as above), or `suffix = "_x"` for a custom one.
- A **mapping** — `vars = {temperature_daily = "t2m"}` — an explicit, suffix-free alias reading file variable `t2m` as node `temperature_daily`.
  Use this to decouple file naming from DAG naming.
- **Omitted** — every variable in the file is bound, through the suffix:

  ```toml
  [inputs.daily]
  path = "data/daily.nc"   # no `vars`: loads every variable as `{var}_daily`
  ```

  An empty list (`vars = []`) is a parse error.
  Output sections always require `vars`.

## Outputs

`[outputs.<label>]` declares which computed variables to write, and where.
Both `path` and at least one `vars` entry are required.

```toml
[outputs.daily]
path = "results/daily.nc"
vars = ["temperature_anomaly", "aridity_index"]
```

`vars` takes the same list/mapping forms as inputs — the mapping form (`{gpp_daily = "gpp"}`) writes node `gpp_daily` to file variable `gpp`.
Format is inferred from the extension.

## Modules

Apart from the built-in `[[node]]` and `[[resample]]`, any section is **your own module**.
A module's keyword-only parameters are set in its section.

```toml
# A .py file beside the config
[climate_nodes]
_import_path = "nodes.py"

# An installed package, with a parameter
[aridity]
_import_path = "mypackage.indices"
floor = 1e-4
```

`_import_path` takes either form, told apart by the `.py` ending:

| Value | Resolved as |
| --- | --- |
| `"nodes.py"`, `"lib/nodes.py"` | a file, relative to the config file's directory |
| `"/shared/nodes.py"` | a file, at an absolute path |
| `"mypackage.indices"` | a dotted module name, imported from the environment |

A `.py` module can import installed packages but [not a sibling file](../guides/nodes/bring-your-own-module.md#two-ways-to-name-a-module); code spanning several files must be an installed package.

### How a section finds its module

A section header is a free-form label wherever `_import_path` is present.
Without one, it has to name a module that an installed package registers.

| The section | What conduit does |
| --- | --- |
| carries `_import_path` | imports that, whatever else the environment offers under the same name |
| carries no `_import_path`, and an installed package registers a module under the section name | imports the registered module, and reports which package supplied it |
| neither | fails at parse time, listing the registered names it does know |

An explicit `_import_path` always wins, so installing a package can never redirect a config that already says where its code lives.

Package authors: see [Register modules from a package](../extending/register-modules.md).

Parameters from every section share [one flat namespace](../guides/nodes/bring-your-own-module.md#parameter-names-share-one-namespace), so two sections defining `threshold` is a parse-time error:

```
Parameter 'threshold' is defined by both [modela] and [modelb]. Module parameters
share one flat namespace, so give the two parameters distinct names ...
```

Rename the parameter in the config *and* in the function that reads it (e.g. `aridity_floor`).

## Nodes

`[[node]]` (a TOML [array of tables](https://toml.io/en/v1.0.0#array-of-tables)) defines DAG nodes inline.
Each entry uses **either** an `expression` **or** (`_import_path` + `function`), never both.

```toml
[[node]]
name = "aridity_index_daily"
inputs = ["precipitation_daily", "evapotranspiration_daily"]
expression = "precipitation_daily / evapotranspiration_daily"
units = "1"
```

| Key | Description |
|-----|-------------|
| `name` | **Required.** The node this entry produces. |
| `inputs` | **Required.** Node names this entry consumes (available in `expression`). |
| `expression` | A Python/xarray expression over `inputs` (`xr` is in scope). |
| `_import_path` + `function` | Alternative to `expression`: call `function` in that module. Same two forms as a module section's. |
| `units` | Output unit contract (validated at parse time). |
| `dims` | Output dimension contract (list of names). |
| `dtype` | Output dtype contract (validated at parse time). |
| `coords` | Output coordinate contract (list of names). |
| `freq` | Output temporal-frequency contract: a pandas offset alias (`"7D"`, `"1ME"`, `"W-SUN"`), validated at parse time. |
| `passthrough` | Declare no fixed output contract; propagate the input's contract across the node. |
| `for_each` | Fan-out: generate one node per value, substituting `{var}` in string fields. |

Declaring any of `units`/`dims`/`dtype`/`coords`/`freq` makes the node a typed producer the [contract check](../guides/nodes/contracts.md) can verify.
See [Inline nodes & fan-out](../guides/configs/inline-nodes-and-fan-out.md) for worked examples.

An anchored `freq` (`"W-SUN"`, `"ME"`) pins the *phase* as well as the spacing; an unanchored one (`"7D"`, `"W"`) constrains the spacing only.

## Resample

`[[resample]]` aggregates to a coarser time frequency, preserving units and dims.
It expands to one passthrough `[[node]]` per variable, applying `conduit.transforms.resample`.

```toml
[[resample]]
vars = ["temperature", "precipitation"]
from = "daily"
to = "weekly"
freq = "7D"
aggfunc = "mean"
```

| Key | Description |
|-----|-------------|
| `vars` | **Required.** Variables to resample; each `{v}_{from}` → `{v}_{to}`. |
| `from` | **Required.** Node-name suffix to read from. |
| `to` | **Required.** Node-name suffix to write to. |
| `freq` | **Required.** Target frequency: a pandas offset alias (`"7D"`, `"1ME"`, `"W-SUN"`), validated at parse time. |
| `aggfunc` | Aggregation: `mean` (default), `sum`, `max`, `min`, `first`, `last`. |

`from` and `to` are free-form labels, so `from = "raw"`, `to = "smoothed"` works just as well; `freq` alone sets the time axis, and becomes the node's declared output frequency.
The time axis is detected from the data, so it need not be called `time`.

!!! warning "No check can catch a wrong `aggfunc`"

    `mean` and `sum` give the same units, so the wrong one passes every contract check.
    Use `mean` for a rate and `sum` for an amount per period; see [Resampling & units](../guides/nodes/resampling-and-units.md).

## Cache

`[cache]` persists intermediate results to disk (Hamilton caching).
See [Scale up › caching](../guides/run/scale-up.md#caching-results).

```toml
[cache]
path = ".conduit_cache"
recompute = ["my_calibrated_node"]
```

| Key | Description |
|-----|-------------|
| `path` | Cache directory (default `.conduit_cache`). |
| `enabled` | Set `false` to keep the section but disable caching. |
| `recompute` | `true` or a list of node names — force recompute even on a hit. |
| `disable` | `true` or a list of node names — bypass the cache for those nodes. |

## Point dimension

`point_dim` is a top-level key naming the dimension your pipeline partitions over.
It does two things:

- it supplies the default `dim` for [`[blocking]`](#blocking) and [`[subset]`](#subset);
- it names the synthetic size-1 axis added to single-point CSV/Parquet/JSON/TOML inputs (see [Data formats › spatial handling](data-formats.md#spatial-handling)).

```toml
point_dim = "location"   # optional; defaults to "pixel"
```

One key drives both so they cannot disagree; otherwise a `[subset]` over `location` would skip a table input given a `pixel` axis.
Gridded pipelines should keep the default, because the geospatial layer stacks `(y, x)` into `pixel`.

## Blocking

`[blocking]` processes a partition dimension in fixed-size sequential chunks to bound peak memory.
See [Scale up › blocking](../guides/run/scale-up.md#memory-bounded-execution-with-blocking).

```toml
[blocking]
block_size = 500
dim = "pixel"
```

| Key | Description |
|-----|-------------|
| `block_size` | **Required.** Positive integer — rows of `dim` per block. |
| `dim` | Partition dimension (defaults to [`point_dim`](#point-dimension), itself `pixel`). |

## Subset

`[subset]` restricts the run to a contiguous slice of one dimension, so independent processes can each handle a different shard of the same inputs.
See [Scale up › parallel subset runs](../guides/run/scale-up.md#parallel-subset-runs).

```toml
[subset]
start = 0            # inclusive
stop  = 500          # exclusive
dim   = "pixel"      # optional; the default
```

| Key | Description |
|-----|-------------|
| `start` | **Required.** First index along `dim` (inclusive, zero-based). |
| `stop` | **Required.** One past the last index (exclusive); must exceed `start`. |
| `dim` | Partition dimension (defaults to [`point_dim`](#point-dimension), itself `pixel`). |

Each NetCDF part is written to its own suffixed file (`out_location0-500.nc`).
A Zarr output requires `dim = "pixel"`, because the shared store's layout is the stacked pixel grid; use NetCDF to subset over any other dimension.

## Validation

`[validation]` declares relationships the input files must satisfy, checked before compute and as a stage of [`--dry-run`](../guides/validate/validate-before-running.md).

```toml
[validation]
checks = [
  { check = "spatial_grid_equal", inputs = ["*"] },
  { check = "time_equal",         inputs = ["climate", "land"] },
  { check = "coords_equal",       inputs = ["*"], coords = ["level"] },
]
```

Each entry names a `check` and the `inputs` to pass it.
`check` and `inputs` are reserved; **every other key is forwarded verbatim as a keyword argument** to the check (e.g. `coords`, `atol`).

| Key | Description |
|-----|-------------|
| `check` | **Required.** The check to run (see below). |
| `inputs` | **Required.** `[inputs.*]` labels to compare, in order. `["*"]` means *all* input sections (declaration order) and must be the sole element. |
| *others* | Forwarded as keyword arguments to the named check. |

Available checks:

| `check` | Inputs | Asserts |
|---------|--------|---------|
| `time_equal` | any | all inputs share an identical time index |
| `time_subset` | exactly 2 | the second input's timestamps are a subset of the first's |
| `spatial_grid_equal` | any | all inputs share a CRS, x/y dims, and coordinate values (`atol`) |
| `crs_equal` | any | all inputs share a CRS |
| `coords_equal` | any | the named `coords` match across all inputs (`atol` for float coords) |

The checks live in [`conduit.input_checks`](modules/conduit.input_checks.md) and can be called directly from Python.
Under [`[subset]`](#subset) they are skipped with a warning, since they describe the whole domain rather than one shard.

## Annotations

`[annotations]` controls how contract declarations (units, schema: dims/coords/dtype, and temporal: freq) are validated.
Omit it to keep the defaults.

```toml
[annotations]
mode = "strict"           # "strict" | "warn" (default) | "off"
on_inexact = "convert"    # "convert" (default) | "warn" | "error"
on_mismatch = "error"     # "error" | "warn" | "ignore" — dims/coords/dtype/freq
on_uninferable = "warn"   # "error" | "warn" (default) | "ignore" — freq only
```

| Key | Description |
|-----|-------------|
| `mode` | Units strictness. `strict` raises on a unit problem; `warn` reports and continues; `off` disables **all** contract checking (every facet). Default `warn`. |
| `on_inexact` | What to do with a dimensionally-compatible but value-changing unit (e.g. `hPa` where `Pa` is declared): `convert` it silently (default), `warn` and convert, or `error`. Two spellings of the same unit (`"pascal"` for `"Pa"`) are relabelled without consulting this. |
| `on_mismatch` | The array contradicts its declaration (dims/coords/dtype/freq): `error` (default), `warn`, or `ignore`. |
| `on_uninferable` | A time axis with too few points (fewer than three) or irregular spacing, so a declared `freq` could not be *tested*: `error`, `warn` (default), or `ignore`. |

Contracts are checked between nodes when the driver is built, and against each node's actual inputs when it runs; [`--dry-run`](../guides/validate/validate-before-running.md) brings the second forward without executing anything.
Incompatible units always raise, and a missing or unparseable `units` attribute follows `mode`.

!!! warning "Affine units (temperature)"

    Converting between offset units such as `degC` and `K` applies the offset (`degC → K` adds 273.15), which is right for an *absolute* temperature and wrong for a *difference* or anomaly.
    Declare such quantities in the unit they are stored in, so no conversion happens, or set `on_inexact = "error"` to forbid implicit temperature conversions.
    `on_inexact = "warn"` is the middle course: each conversion still happens, but is reported by name.
