---
title: Quickstart
icon: lucide/rocket
---

# Quickstart: your first pipeline

Get a conduit pipeline running in a few minutes. This guide builds a minimal pipeline
that derives a temperature anomaly from an input field — no domain models, no geospatial
setup.

## Prerequisites

Follow the [Installation guide](installation.md) to install conduit.

## Step 1: Create some input data

conduit reads the xarray-friendly formats you already use (NetCDF, Zarr, CSV, Parquet,
JSON). Here we make a small NetCDF input:

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

## Step 2: Write a config

Save this as `config.toml`:

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

- `[inputs.climate]` loads `temperature` and exposes it to the DAG as
  `temperature_climate` — the node name is `{var}_{section}`.
- `[[node]]` defines a derived node inline and declares its output unit.
- `[outputs.climate]` chooses what to write to disk.

## Step 3: Visualise the pipeline

```sh
conduit graph config.toml --pdf
```

This produces `pipeline.pdf` showing the nodes and their dependencies. (Requires the
`viz` extra and the Graphviz system binary.)

## Step 4: Run the pipeline

```sh
conduit run config.toml
```

This loads the input, executes the DAG, and writes `anomaly.nc`.

## Step 5: Inspect the results

```python
import xarray as xr

ds = xr.open_dataset("anomaly.nc")
print(ds)
print(ds["temperature_anomaly"].attrs["units"])  # "degC"
```

## Next steps

- Read about [how it works](concepts.md) to understand the DAG and config.
- See the [Configuration reference](../usage/config.md) for all available options.
- Learn how to plug in your own modules in [Custom modules](../usage/custom-modules.md).
- Browse the runnable [Examples](../examples/getting_started.md).
