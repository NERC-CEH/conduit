---
title: Configuration
icon: lucide/settings
---

# Configuration reference

A conduit pipeline is described by a [TOML](https://toml.io/en/) file. Each section
switches on one part of the pipeline; leave a section out and that part is not there.

Recognised top-level sections are listed below. **Any section not listed here is treated
as your own module** and must carry an `_import_path` key (see [Modules](#modules)), so a
mistyped section name is an error rather than a silently ignored one. Gridding comes from
the inputs' CRS, and graph styling from a `conduit graph --style` file.

!!! note "Paths are resolved relative to the config file"

    Every relative path in a config — `path` in `[inputs.*]`, `[outputs.*]` and
    `[cache]`, and a `.py` `_import_path` — is resolved against the directory
    containing the config file, never the current working directory. A config and the
    files beside it therefore travel together, and run the same from anywhere.

## Inputs

`[inputs.<label>]` declares where to load data from and which variables to expose. The
`<label>` is arbitrary (`climate`, `daily`, `static`, …).

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

- A **list** — `vars = ["temperature"]` — names each node `{var}{suffix}`. The suffix
  defaults to `_<label>` (so `temperature` under `[inputs.daily]` → node
  `temperature_daily`). Set `suffix = ""` for bare names on any section (e.g. a
  `static` section, as above), or `suffix = "_x"` for a custom one.
- A **mapping** — `vars = {temperature_daily = "t2m"}` — an explicit, suffix-free alias
  reading file variable `t2m` as node `temperature_daily`. Use this to decouple file
  naming from DAG naming.
- **Omitted** — every variable in the file is bound, through the suffix:

  ```toml
  [inputs.daily]
  path = "data/daily.nc"   # no `vars`: loads every variable as `{var}_daily`
  ```

  An empty list (`vars = []`) is a parse error. Output sections always require `vars`.

## Outputs

`[outputs.<label>]` declares which computed variables to write, and where. Both `path`
and at least one `vars` entry are required.

```toml
[outputs.daily]
path = "results/daily.nc"
vars = ["temperature_anomaly", "aridity_index"]
```

`vars` takes the same list/mapping forms as inputs — the mapping form
(`{gpp_daily = "gpp"}`) writes node `gpp_daily` to file variable `gpp`. Format is
inferred from the extension.

## Modules

Compose the pipeline from modules. There is one built-in addressable by short name —
`[[node]]` (with the `[[resample]]` preset) — and any other section is **your own
module**, loaded by its `_import_path`. A module's keyword-only parameters can be
supplied in its section body.

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

A module named by a `.py` path is loaded on its own: it can import installed packages,
but not another loose `.py` file beside it. Code that spans several files has to be an
installed package, named by a dotted path.

The section header (`aridity`) is a free-form label; only `_import_path` is semantic.
See [Bring your own module](../guides/nodes/bring-your-own-module.md) for the authoring
conventions.

!!! note "Parameter namespacing"

    Module parameters from **every** section are merged into a single flat dictionary, the
    Hamilton driver config. A parameter's config key and the function's argument name are
    therefore the same string.

    Parameter names must be unique across active sections. Two sections defining `threshold`
    is a parse-time error naming both:

    ```
    Parameter 'threshold' is defined by both [modela] and [modelb]. Module parameters
    share one flat namespace, so give the two parameters distinct names ...
    ```

    To fix it, rename the parameter in the config *and* the keyword argument in the module
    that reads it (e.g. `aridity_floor`). Sections that are not both active never collide.

## Nodes

`[[node]]` (a TOML [array of tables](https://toml.io/en/v1.0.0#array-of-tables)) defines
DAG nodes inline. Each entry uses **either** an `expression` **or**
(`_import_path` + `function`), never both.

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

Declaring any of `units`/`dims`/`dtype`/`coords`/`freq` makes the node a typed producer
the [contract check](../guides/nodes/contracts.md) can verify. See
[Inline nodes & fan-out](../guides/configs/inline-nodes-and-fan-out.md) for worked examples.

An anchored `freq` (`"W-SUN"`, `"ME"`) pins the *phase* as well as the spacing; an
unanchored one (`"7D"`, `"W"`) constrains the spacing only.

## Resample

`[[resample]]` is a preset that desugars to fan-out passthrough `[[node]]`s applying
`conduit.transforms.resample` — aggregating a temporal frequency to a coarser one while
preserving units and dims.

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

!!! note "`from` and `to` are node-name suffixes"

    `from = "daily"` reads `{var}_daily` and `to = "weekly"` writes `{var}_weekly`. They are
    free-form, so `from = "raw"`, `to = "smoothed"` works just as well. `freq` is what sets
    the time axis.

`freq` also becomes the generated node's **declared output frequency**, so every
resample carries a checkable frequency contract: a downstream consumer declaring
`Freq("W-SUN")` against a `freq = "W-WED"` resample fails at build time.

The time axis is detected from the data, so it need not be called `time`.

!!! warning "Choosing `aggfunc` is not something the checks can help with"

    Resampling preserves units, so `mean` and `sum` are equally valid *dimensionally*, and a
    wrong choice gives a meaningless number that no contract check will flag. Use `mean` for
    a rate and `sum` for an amount-per-period; see
    [Resampling & units](../guides/nodes/resampling-and-units.md).

## Cache

`[cache]` persists intermediate results to disk (Hamilton caching). See
[Scale up › caching](../guides/run/scale-up.md#caching-results).

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

`point_dim` is a top-level key naming the dimension your pipeline partitions over. It
does two things:

- it supplies the default `dim` for [`[blocking]`](#blocking) and [`[subset]`](#subset);
- it names the synthetic size-1 axis added to single-point CSV/Parquet/JSON/TOML inputs
  (see [Data formats › spatial handling](data-formats.md#spatial-handling)).

```toml
point_dim = "location"   # optional; defaults to "pixel"
```

The two must agree. If a table input were given a `pixel` axis while `[subset]`
partitioned over `location`, the subset would skip that input entirely and leave a
stray `pixel` axis in the outputs, which is why one key drives both.

Gridded pipelines should leave this at its default: the geospatial layer stacks `(y, x)`
into `pixel` by name.

## Blocking

`[blocking]` processes a partition dimension in fixed-size sequential chunks to bound
peak memory. See [Scale up › blocking](../guides/run/scale-up.md#memory-bounded-execution-with-blocking).

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

`[subset]` restricts the run to a contiguous slice of one dimension, so independent
processes can each handle a different shard of the same inputs. See
[Scale up › parallel subset runs](../guides/run/scale-up.md#parallel-subset-runs).

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

`dim` mirrors [`[blocking]`](#blocking): the two mechanisms partition the same way and
differ only in *who* runs the parts — one process sequentially (`[blocking]`) versus many
processes concurrently (`[subset]`). A non-gridded pipeline can subset over `location` or
`site` just as it can block over it, and each part is written to its own suffixed file
(`out_location0-500.nc`).

!!! warning "Zarr stores are pixel-only"

    The one place `pixel` is still special is the shared Zarr store built by
    `conduit gridded create-store`: the store's layout *is* the stacked pixel grid, which
    `merge` unstacks back to `(y, x)`. Configuring `dim` — or `point_dim` — as anything else
    alongside a Zarr output is an error. Use a NetCDF output instead — its subset parts are
    separate files and need no pre-created store.

## Validation

`[validation]` is where you declare properties you expect and want checked, as opposed to
the DAG's structure, which conduit works out on its own. Its `checks` array runs a set of
input-Dataset compatibility checks before compute, and as a stage of
[`--dry-run`](../guides/validate/validate-before-running.md).

```toml
[validation]
checks = [
  { check = "spatial_grid_equal", inputs = ["*"] },
  { check = "time_equal",         inputs = ["climate", "land"] },
  { check = "coords_equal",       inputs = ["*"], coords = ["level"] },
]
```

Each entry names a `check` and the `inputs` to pass it. `check` and `inputs` are reserved;
**every other key is forwarded verbatim as a keyword argument** to the check (e.g.
`coords`, `atol`).

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

The checks are an importable library ([`conduit.input_checks`](modules/conduit.input_checks.md)), so
the [notebook-driven path](../guides/run/drive-from-python.md) can call them directly.
They are **opt-in**: conduit cannot know which inputs are *meant* to align, so declare the
ones that must. Under [`[subset]`](#subset) they are skipped with a warning, since they
describe the whole domain rather than a single shard.

## Annotations

`[annotations]` controls how contract declarations (units, schema: dims/coords/dtype,
and temporal: freq) are validated. Omit it to keep the defaults.

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

Validation happens at two points:

- **Build time** — every internal edge where both ends declare a contract is checked
  when the driver is built, so a mismatch is caught before compute. Contracts propagate
  through passthrough nodes (e.g. resampling), so those edges are covered too.
- **Run time** — as each node executes, every `DataArray` input is validated against its
  declaration. Under `on_inexact = "convert"` a compatible input is converted; under
  `"error"` it must already match. Dimensionally-incompatible inputs always raise. A `units`
  attribute that is missing or unparseable follows `mode`.

Run the run-time input checks against your real data *without* executing the pipeline
with [`conduit run --dry-run`](../guides/validate/validate-before-running.md).

!!! warning "Affine units (temperature)"

    Converting between offset units such as `degC` and `K` applies the offset
    (`degC → K` adds 273.15), which is right for an *absolute* temperature and wrong for a
    *difference* or anomaly. Declare such quantities in the unit they are stored in, so no
    conversion happens, or set `on_inexact = "error"` to forbid implicit temperature
    conversions. `on_inexact = "warn"` is the middle course: the conversion still happens,
    but each one is reported by name, so an unintended one cannot pass unnoticed.

## See also

- [Write a config](../guides/configs/write-a-config.md) — the shape of a config, and the
  edits you are most likely to make.
- [Validate before running](../guides/validate/validate-before-running.md) — the `--dry-run`
  pre-flight, the wiring check, and the `[validation]` input checks.
- [Data formats](data-formats.md) — supported file types and spatial/temporal handling.
- [Inline nodes & fan-out](../guides/configs/inline-nodes-and-fan-out.md) — the `[[node]]` and
  `[[resample]]` guide.
- [Bring your own module](../guides/nodes/bring-your-own-module.md) — external module
  conventions.
