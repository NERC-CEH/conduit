---
title: CLI Guide
icon: lucide/terminal
---

# Using the command-line interface

conduit provides a `conduit` command for running pipelines from the terminal.
This guide walks through a typical workflow.

For a complete reference of all commands, arguments, and options, see the [CLI Reference](../api/conduit.cli/index.md).

## The workflow

A typical conduit CLI workflow is:

```
write a config.toml → graph → run
```

1. **Describe the pipeline** in a TOML config (see the [Quickstart](../getting_started/quickstart.md)
   and [Configuration reference](config.md)).
2. **Visualise the pipeline** with `conduit graph`.
3. **Execute the pipeline** with `conduit run`.

The other commands — `create-store` and `merge` — support parallel subset runs over Zarr;
see the [CLI Reference](../api/conduit.cli/index.md).

## Visualise the pipeline

Before running, inspect the DAG to verify the structure looks correct:

```sh
conduit graph config.toml --pdf
```

This produces `pipeline.pdf` showing all nodes and their dependencies. Each node
displays its declared **unit** (read from the `Annotated[DataArray, "<unit>"]`
type) in place of the generic `DataArray` type, and the requested output nodes are
highlighted with a coloured border. When sections represent temporal frequencies,
edges are coloured by frequency and nodes are grouped into dashed
`daily`/`weekly`/`monthly` clusters:

| Colour | Category |
|--------|----------|
| Teal | Static inputs |
| Orange | Daily |
| Blue | Weekly |
| Green | Monthly |
| Pink border | Requested outputs |

You can also output as PNG:

```sh
conduit graph config.toml --png
```

### Customising the styling

Pass a separate styling file with `--style` (or `-s`) to override any of the
defaults — colours, layout, the legend, or even a custom style function. Keeping
it in its own file means one style can be reused across many pipelines:

```sh
conduit graph config.toml --style examples/graphviz.toml --pdf
```

See the commented [`examples/graphviz.toml`](https://github.com/NERC-CEH/conduit/blob/main/examples/graphviz.toml)
template for the full set of keys (`palette`, `graph_attr`/`node_attr`/`edge_attr`,
`show_legend`, `cluster_by_frequency`, and `style_function`).

/// admonition | Note
    type: note

Requires [graphviz](https://graphviz.org/) to be installed.
///

## Run the pipeline

Execute the pipeline:

```sh
conduit run config.toml
```

This reads the config, builds the DAG, executes all required nodes in dependency order, and writes output files as specified in the `[outputs.*]` sections.

### Validating without running (`--dry-run`)

Before committing to a long run, you can pre-flight a config with `--dry-run`:

```sh
conduit run config.toml --dry-run
```

This performs every check a real run depends on, but executes no node and writes no output. It validates, in order:

1. **Config** — the TOML parses into a valid pipeline.
2. **Inputs** — every input file exists and opens. (Files are opened lazily, so this reads metadata only, not the full arrays.)
3. **DAG** — the driver builds, and the build-time unit check passes.
4. **Execution plan** — every variable in your `[outputs.*]` sections is reachable from the given inputs.
5. **Input units** — the `units` attribute of each loaded input is checked against the unit its consuming node declares. This is the part that needs the real data, and the only unit check a normal run defers to run time — so a dry run surfaces a file delivered in the wrong units (or missing a `units` attribute) without running the pipeline. See [Units](config.md#units).
6. **Output paths** — every output destination would accept a write (supported extension, writable parent directory, and — for subset runs — a pre-created Zarr store).

A clean pre-flight prints a per-stage summary and exits `0`. The unit-checking stage honours the active `mode`: in `warn` mode a unit problem is reported as a warning and the dry run still passes, while in `strict` mode it fails with a non-zero exit. A genuine problem with the config, inputs, DAG plan, or output paths always fails the dry run regardless of `mode`.

### Caching

To reuse unchanged intermediate results between runs, enable caching — either via a
[`[cache]` section](config.md#caching) in the config, or with these flags:

| Flag | Description |
|------|-------------|
| `--cache` / `--no-cache` | Force caching on or off, overriding the config. |
| `--cache-dir` | Directory for the cache store (implies `--cache`). |

```sh
conduit run config.toml --cache --cache-dir runs/cache
```

This is especially useful for calibration loops that re-run the pipeline while
changing only a few parameters; see [Caching](config.md#caching) for details.

## Inspecting results

The output files are NetCDF (or whatever format you specified). Load them in Python:

```python
import xarray as xr

ds = xr.open_dataset("results/anomaly.nc")
print(ds)
```

## Getting help

Every command supports `-h` / `--help`:

```sh
conduit -h
conduit run -h
conduit graph -h
```

For detailed documentation on each CLI module's functions and parameters, see the [CLI Reference](../api/conduit.cli/index.md).
