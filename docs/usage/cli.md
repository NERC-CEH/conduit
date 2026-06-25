---
title: CLI Guide
icon: lucide/terminal
---

# Using the Command-Line Interface

SatTerC provides a `satterc` command for running pipelines from the terminal.
This guide walks through a typical workflow from setup to execution.

For a complete reference of all commands, arguments, and options, see the [CLI Reference](../api/satterc.cli/index.md).

## The Workflow

A typical SatTerC CLI workflow has four steps:

```
setup → data-gen → graph → run
```

1. **Generate a config** with `satterc setup`
2. **Create test data** with `satterc data-gen generate`
3. **Visualise the pipeline** with `satterc graph`
4. **Execute the pipeline** with `satterc run`

Let's walk through each step.

## Step 1: Generate a Configuration

The `setup` command creates a TOML configuration file. You can run it interactively or with defaults.

### Interactive mode

```sh
satterc setup
```

This walks you through:

1. Selecting built-in models (type numbers or names, toggle with re-entry)
2. Optionally adding custom module paths
3. Confirming input/output paths (or entering custom ones)
4. Optionally generating synthetic data right away

### Non-interactive mode

```sh
satterc setup --models splash pmodel --defaults
```

This generates a config with the specified models and placeholder paths, no prompts.

### Custom output path

```sh
satterc setup --models splash --output my_pipeline.toml
```

The generated config includes all input variables required by the selected models, placeholder output sections, and any resampling steps needed to bridge temporal frequencies.

## Step 2: Generate Synthetic Data

Before running on real data, test your pipeline with synthetic inputs:

```sh
satterc data-gen generate config.toml
```

This creates NetCDF files at the paths specified in your config. By default it generates data for a single site over 2 years.

### Custom grid and duration

```sh
satterc data-gen generate config.toml --grid 4,4 --duration 6m --seed 42
```

This produces a 4×4 grid of synthetic data covering 6 months.

The duration format is a number followed by a unit: `2y` (years), `6m` (months), `30d` (days).

## Step 3: Visualise the Pipeline

Before running, inspect the DAG to verify the structure looks correct:

```sh
satterc graph config.toml --pdf
```

This produces `pipeline.pdf` showing all nodes and their dependencies. Each node
displays its declared **unit** (read from the `Annotated[DataArray, "<unit>"]`
type) in place of the generic `DataArray` type, the requested output nodes are
highlighted with a coloured border, edges are coloured by temporal frequency,
and nodes are grouped into dashed `daily`/`weekly`/`monthly` clusters. Nodes are
filled by category:

| Colour | Category |
|--------|----------|
| Teal | Static inputs |
| Orange | Daily |
| Blue | Weekly |
| Green | Monthly |
| Pink border | Requested outputs |

You can also output as PNG:

```sh
satterc graph config.toml --png
```

### Customising the styling

Pass a separate styling file with `--style` (or `-s`) to override any of the
defaults — colours, layout, the legend, or even a custom style function. Keeping
it in its own file means one style can be reused across many pipelines:

```sh
satterc graph config.toml --style examples/graphviz.toml --pdf
```

See the commented [`examples/graphviz.toml`](https://github.com/SatTerC/satterc/blob/main/examples/graphviz.toml)
template for the full set of keys (`palette`, `graph_attr`/`node_attr`/`edge_attr`,
`show_legend`, `cluster_by_frequency`, and `style_function`).

/// admonition | Note
    type: note

Requires [graphviz](https://graphviz.org/) to be installed.
///

## Step 4: Run the Pipeline

Execute the pipeline:

```sh
satterc run config.toml
```

This reads the config, builds the DAG, executes all required nodes in dependency order, and writes output files as specified in the `[outputs.*]` sections.

### Validating without running (`--dry-run`)

Before committing to a long run, you can pre-flight a config with `--dry-run`:

```sh
satterc run config.toml --dry-run
```

This performs every check a real run depends on, but executes no model and writes no output. It validates, in order:

1. **Config** — the TOML parses into a valid pipeline.
2. **Inputs** — every input file exists and opens, and its time axis has the expected frequency. (Files are opened lazily, so this reads metadata only, not the full arrays.)
3. **DAG** — the driver builds, and the build-time unit check passes.
4. **Execution plan** — every variable in your `[outputs.*]` sections is reachable from the given inputs.
5. **Input units** — the `units` attribute of each loaded input is checked against the unit its consuming node declares. This is the part that needs the real data, and the only unit check a normal run defers to run time — so a dry run surfaces a file delivered in the wrong units (or missing a `units` attribute) without running the pipeline. See [Units](config.md#units).
6. **Output paths** — every output destination would accept a write (supported extension, writable parent directory, and — for subset runs — a pre-created Zarr store).

A clean pre-flight prints a per-stage summary and exits `0`:

```
Dry run for config.toml
  ✓ config parsed
  ✓ inputs loaded: 25 variable(s) from 4 source(s)
  ✓ DAG built (static unit check passed)
  ✓ execution plan valid: 3 output node(s) reachable
  ✓ input units validated (mode=warn)
  ✓ output paths writable: 3 destination(s)
Dry run passed.
```

The unit-checking stage honours the active `mode`: in `warn` mode a unit problem is reported as a warning and the dry run still passes, while in `strict` mode it fails with a non-zero exit. A genuine problem with the config, inputs, DAG plan, or output paths always fails the dry run regardless of `mode`.

### Caching

To reuse unchanged intermediate results between runs, enable caching — either via a
[`[cache]` section](config.md#caching) in the config, or with these flags:

| Flag | Description |
|------|-------------|
| `--cache` / `--no-cache` | Force caching on or off, overriding the config. |
| `--cache-dir` | Directory for the cache store (implies `--cache`). |

```sh
satterc run config.toml --cache --cache-dir runs/cache
```

This is especially useful for calibration loops that re-run the pipeline while
changing only a few parameters; see [Caching](config.md#caching) for details.

## Inspecting Results

The output files are NetCDF (or whatever format you specified). Load them in Python:

```python
import xarray as xr

ds = xr.open_dataset("outputs/daily.nc")
print(ds)
ds["soil_moisture"].plot()
```

## Getting Help

Every command supports `-h` / `--help`:

```sh
satterc -h
satterc setup -h
satterc data-gen generate -h
```

For detailed documentation on each CLI module's functions and parameters, see the [CLI Reference](../api/satterc.cli/index.md).
