---
title: Your first pipeline
icon: lucide/rocket
---

# Your first pipeline

This tutorial builds a complete conduit pipeline from scratch. By the end you will
have written an input file, described a pipeline in TOML, visualised it, run it, and
inspected the result — the whole conduit workflow in miniature.

The pipeline is deliberately tiny: it derives a *temperature anomaly* from a single
input field. There are no domain models and no geospatial setup — just enough to see
every moving part.

## Prerequisites

Follow the [Installation guide](install.md) to install conduit. To render the DAG in
[Step 3](#step-3-visualise-the-pipeline) you also need the `viz` extra and the
Graphviz system binary; if you skip that step, the base install is enough.

## Step 1: Create some input data

conduit reads the xarray-friendly formats you already use (NetCDF, Zarr, CSV,
Parquet, JSON). Here we make a small NetCDF file with one variable, `temperature`,
over 90 days at three sites:

```python
import numpy as np
import xarray as xr

times = xr.date_range("2020-01-01", periods=90, freq="D")
temperature = xr.DataArray(
    10.0 + 8.0 * np.sin(np.linspace(0, 3.14, 90))[:, None] + np.arange(3),
    dims=("time", "site"),
    coords={"time": times, "site": ["a", "b", "c"]},
    attrs={"units": "degC"},
)
xr.Dataset({"temperature": temperature}).to_netcdf("climate.nc")
```

The `units` attribute is optional, but setting it lets conduit validate and convert
units for you later — see [the next tutorial](units-and-contracts.md).

## Step 2: Write a config

A conduit pipeline is a [TOML](https://toml.io) file. Save this as `config.toml`:

```toml
[inputs.climate]
path = "climate.nc"
vars = ["temperature"]

[[node]]
name = "temperature_anomaly_climate"
inputs = ["temperature_climate"]
expression = "temperature_climate - temperature_climate.mean('time')"
units = "degC"

[outputs.climate]
path = "anomaly.nc"
vars = ["temperature_anomaly"]
```

Three sections describe the whole pipeline:

- **`[inputs.climate]`** loads the `temperature` variable from `climate.nc` and
  exposes it to the pipeline as a node named `temperature_climate`. The node name is
  the file variable plus the section's suffix (`{var}_{section}`), so `temperature`
  under `[inputs.climate]` becomes `temperature_climate`.
- **`[[node]]`** defines a derived node *inline*. Its `inputs` list names the nodes it
  consumes, and `expression` is an ordinary Python/xarray expression evaluated with
  those inputs in scope. `units` declares the unit of its output.
- **`[outputs.climate]`** chooses what to write to disk. `vars` lists the variables to
  save — here the anomaly, written back without the section suffix.

That is the core idea: **the config *is* the pipeline.** conduit reads it, works out
the dependencies between nodes, and runs them in the right order.

## Step 3: Visualise the pipeline

Before running anything, render the graph to check the structure looks right:

```sh
conduit graph config.toml --pdf
```

This writes `pipeline.pdf` showing each node and the edges between them. (Requires the
`viz` extra and the Graphviz system binary — see [Installation](install.md).) You can
also pass `--png`. For more on styling the graph, see
[Run & visualise](../guides/run-and-visualise.md).

## Step 4: Run the pipeline

```sh
conduit run config.toml
```

conduit loads the input, executes the DAG, and writes `anomaly.nc`. Only the nodes
needed to produce your requested outputs are computed.

## Step 5: Inspect the results

```python
import xarray as xr

ds = xr.open_dataset("anomaly.nc")
print(ds)
print(ds["temperature_anomaly"].attrs["units"])  # "degC"
```

The output carries the `degC` unit you declared on the node, and its `attrs` also
include a copy of the config used to produce it — so the file is a self-describing,
reproducible record of the run.

## What you built

You wrote a pipeline as plain text, saw conduit turn it into a dependency graph, and
ran it end to end. Everything else conduit does builds on these same three section
types (`inputs`, nodes, `outputs`).

## Next steps

- [Add unit contracts](units-and-contracts.md) — let conduit prove your pipeline is
  consistent *before* it runs.
- [How conduit works](../concepts/dag-model.md) — the DAG model behind the config.
- [Configuration reference](../reference/configuration.md) — every config section.
- [Bring your own module](../guides/bring-your-own-module.md) — plug in your own
  Python functions instead of inline expressions.
