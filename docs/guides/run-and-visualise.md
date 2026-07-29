---
title: Run & visualise from the CLI
icon: lucide/terminal
---

# Run & visualise from the CLI

conduit provides a `conduit` command for running pipelines from the terminal. The
typical workflow is:

```
write a config.toml  →  conduit graph  →  conduit run
```

For a full reference of every command and flag, see the
[CLI reference](../api/conduit.cli/index.md).

## Visualise the pipeline

Before running, render the DAG to check the structure looks right:

```sh
conduit graph config.toml --pdf
```

This writes `pipeline.pdf` showing every node and its dependencies. Each node displays
its declared **unit** (read from the `Annotated[DataArray, "<unit>"]` type) in place of
the generic `DataArray` type, and requested output nodes are highlighted.

Nodes are coloured and clustered by their declared **frequency** — the `freq` contract on
a `[[node]]` or `[[resample]]` (`"7D"`, `"1ME"`). This is read from the DAG, not guessed
from node names: a pipeline whose resample targets are called `raw` and `smoothed` groups
exactly as well as one using `daily` and `weekly`. Nodes with no declared frequency
inherit one when all their neighbours agree, and are otherwise left ungrouped.

Pass `--png` for PNG instead, and `-o/--output` to change the base filename (default
`pipeline`). The `.dot` source is always written.

/// admonition | Requires Graphviz
    type: note

`conduit graph` needs the `viz` extra **and** the Graphviz system binary — see
[Installation](../get-started/install.md).
///

### Customising the styling

Pass a styling file with `-s`/`--style` to override colours, layout, the legend, or a
custom style function. Keeping style in its own file lets one look be reused across many
pipelines:

```sh
conduit graph config.toml --style examples/graphviz.toml --pdf
```

See the commented
[`examples/graphviz.toml`](https://github.com/NERC-CEH/conduit/blob/main/examples/graphviz.toml)
template for the full set of keys (`palette`, `graph_attr`/`node_attr`/`edge_attr`,
`show_legend`, `cluster_by_frequency`, `style_function`).

## Run the pipeline

```sh
conduit run config.toml
```

conduit reads the config, builds the DAG, executes the nodes needed for your
`[outputs.*]` sections in dependency order, and writes the output files. Each output is
stamped with the config used to produce it, so the file is self-describing.

### Pre-flight without running

Before committing to a long run, validate everything with `--dry-run` — it checks the
config, inputs, DAG, wiring and contracts without executing a node:

```sh
conduit run config.toml --dry-run
```

See [Validate before running](validate-before-running.md) for what each stage checks.

### Overriding config from the CLI

A few flags override the config per invocation, without editing the file:

| Flag | Effect |
|------|--------|
| `--cache` / `--no-cache` | Force result caching on or off (overrides `[cache]`). |
| `--cache-dir <path>` | Directory for the cache store (implies `--cache`). |
| `--allow-overrides` | Permit a later module to override an earlier one's node. |

Caching, memory-bounded execution and parallel runs are covered in
[Scale up a pipeline](scale-up.md).

## Inspecting results

Output files are NetCDF (or whatever the extension implies). Load them in Python:

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
conduit gridded -h   # parallel-Zarr commands (needs the geo extra)
```
