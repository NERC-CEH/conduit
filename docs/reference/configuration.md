---
title: Configuration
icon: lucide/settings
---

# Configuration reference

A conduit pipeline is described by a [TOML](https://toml.io/en/) file. Each section
activates a pipeline component; absent sections are simply not included, so you build a
pipeline from only the parts you need.

Recognised top-level sections are listed below. **Any section not listed here is treated
as your own module** and must carry an `_import_path` key (see
[Modules](#modules)). Two sections are accepted but otherwise inert: `[grid]` (an
explicit marker for gridded inputs) and `[graphviz]` (styling belongs in a
`conduit graph --style` file, not the science config).

/// admonition | Paths are resolved relative to the config file
    type: note

Relative `path` values in `[inputs.*]`, `[outputs.*]` and `[cache]` are resolved
against the directory containing the config file, not the current working directory.
///

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
| `vars` | Which variables to expose, and under what node names (see below). |
| `suffix` | Overrides the node-name suffix for the list form of `vars`. |

**`vars` has two forms:**

- A **list** — `vars = ["temperature"]` — names each node `{var}{suffix}`. The suffix
  defaults to `_<label>` (so `temperature` under `[inputs.daily]` → node
  `temperature_daily`). Set `suffix = ""` for bare names on any section (e.g. a
  `static` section, as above), or `suffix = "_x"` for a custom one.
- A **mapping** — `vars = {temperature_daily = "t2m"}` — an explicit, suffix-free alias
  reading file variable `t2m` as node `temperature_daily`. Use this to decouple file
  naming from DAG naming.

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
module**, loaded by its dotted `_import_path`. A module's keyword-only parameters can be
supplied in its section body.

```toml
# Your own module, with a parameter
[aridity]
_import_path = "mypackage.indices"
floor = 1e-4
```

The section header (`aridity`) is a free-form label; only `_import_path` is semantic.
See [Bring your own module](../guides/bring-your-own-module.md) for the authoring
conventions.

/// admonition | Parameter namespacing
    type: note

All module parameters are merged into a single flat dictionary, so names must be unique
across active sections. A clash raises at parse time — prefix to disambiguate
(e.g. `aridity_floor`).
///

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
| `_import_path` + `function` | Alternative to `expression`: call `function` in that module. |
| `units` | Output unit contract (validated at parse time). |
| `dims` | Output dimension contract (list of names). |
| `dtype` | Output dtype contract (validated at parse time). |
| `coords` | Output coordinate contract (list of names). |
| `passthrough` | Declare no fixed output contract; propagate the input's contract across the node. |
| `for_each` | Fan-out: generate one node per value, substituting `{var}` in string fields. |

Declaring any of `units`/`dims`/`dtype`/`coords` makes the node a typed producer the
[contract check](../concepts/contracts.md) can verify. See
[Inline nodes & fan-out](../guides/inline-nodes-and-fan-out.md) for worked examples.

## Resample

`[[resample]]` is a preset that desugars to fan-out passthrough `[[node]]`s applying
`conduit.transforms.resample` — aggregating a temporal frequency to a coarser one while
preserving units and dims.

```toml
[[resample]]
from_freq = "daily"
to_freq = "weekly"
vars = ["temperature", "precipitation"]
aggfunc = "mean"
```

| Key | Description |
|-----|-------------|
| `vars` | **Required.** Variables to resample; each `{v}_{from_freq}` → `{v}_{to_freq}`. |
| `from_freq` | **Required.** Source frequency label. |
| `to_freq` | **Required.** Target frequency label. |
| `aggfunc` | Aggregation: `mean` (default), `sum`, `max`, `min`, `first`, `last`. |
| `freq` | Explicit pandas offset alias (e.g. `"1D"`). Required unless the direction is a built-in default. |

Built-in default directions (no `freq` needed): `daily`→`weekly`, `daily`→`monthly`,
`weekly`→`monthly`. Any other direction needs an explicit `freq`.

## Cache

`[cache]` persists intermediate results to disk (Hamilton caching). See
[Scale up › caching](../guides/scale-up.md#caching-results).

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

## Blocking

`[blocking]` processes a partition dimension in fixed-size sequential chunks to bound
peak memory. See [Scale up › blocking](../guides/scale-up.md#memory-bounded-execution-with-blocking).

```toml
[blocking]
block_size = 500
dim = "pixel"
```

| Key | Description |
|-----|-------------|
| `block_size` | **Required.** Positive integer — rows of `dim` per block. |
| `dim` | Partition dimension (default `pixel`). |

## Subset

`[subset]` restricts the run to a contiguous slice of the stacked `pixel` dimension, for
parallel per-shard runs. See [Scale up › parallel subset runs](../guides/scale-up.md#parallel-subset-runs-over-zarr).

```toml
[subset]
pixel_start = 0      # inclusive
pixel_end   = 500    # exclusive
```

| Key | Description |
|-----|-------------|
| `pixel_start` | **Required.** First pixel index (inclusive, zero-based). |
| `pixel_end` | **Required.** One past the last index (exclusive); must exceed `pixel_start`. |

## Validation

`[validation]` groups **declarations about properties you expect and want to check** — as
opposed to the DAG's structure, which conduit derives on its own. Its `checks` array runs
a suite of input-Dataset compatibility checks before compute (and as a stage of
[`--dry-run`](../guides/validate-before-running.md)).

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

The checks are a real importable library (`conduit.checks`), so the
[notebook-driven path](../guides/drive-from-python.md) calls them directly — the config
list is only sugar over the same functions. They are **opt-in**: with no `[validation]`
block conduit performs no cross-input validation (it does not guess which inputs are
*meant* to align — only you know that). Under [`[subset]`](#subset) they are skipped, with
a warning, since they describe the whole domain rather than a single shard.

## Annotations

`[annotations]` controls how contract declarations (units + schema: dims/coords/dtype)
are validated. The legacy name `[units]` is a working alias for the same section. Omit
it to keep the defaults.

```toml
[annotations]
mode = "strict"      # "strict" | "warn" (default) | "off"
exact = false        # reject value-changing unit conversions
on_mismatch = "error"  # "error" | "warn" | "ignore" — for dims/coords/dtype
```

| Key | Description |
|-----|-------------|
| `mode` | Units strictness. `strict` raises on a unit problem; `warn` reports and continues; `off` disables **all** contract checking (every facet). Default `warn`. |
| `exact` | When `true`, a dimensionally-compatible but value-changing unit (e.g. `hPa` where `Pa` is declared) is rejected rather than converted. Default `false`. |
| `on_mismatch` | Schema (dims/coords/dtype) policy: `error`, `warn`, or `ignore`. |

Validation happens at two points:

- **Build time** — every internal edge where both ends declare a contract is checked
  when the driver is built, so a mismatch is caught before compute. Contracts propagate
  through passthrough nodes (e.g. resampling), so those edges are covered too.
- **Run time** — as each node executes, every `DataArray` input is validated against its
  declaration. With `exact = false` a compatible input is converted; with `exact = true`
  it must already match. Dimensionally-incompatible inputs always raise. A `units`
  attribute that is missing or unparseable follows `mode`.

Run the run-time input checks against your real data *without* executing the pipeline
with [`conduit run --dry-run`](../guides/validate-before-running.md).

/// admonition | Affine units (temperature)
    type: warning

Converting between offset units such as `degC` and `K` applies the offset
(`degC → K` adds 273.15), which is correct for an *absolute* temperature but wrong for a
*difference* or anomaly. Declare such quantities in the unit they are stored in (no
conversion), or set `exact = true` to forbid implicit temperature conversions.
///

## See also

- [Validate before running](../guides/validate-before-running.md) — the `--dry-run`
  pre-flight, the wiring check, and the `[validation]` input checks.
- [Data formats](data-formats.md) — supported file types and spatial/temporal handling.
- [Inline nodes & fan-out](../guides/inline-nodes-and-fan-out.md) — the `[[node]]` and
  `[[resample]]` guide.
- [Bring your own module](../guides/bring-your-own-module.md) — external module
  conventions.
