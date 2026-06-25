---
title: Quickstart
icon: lucide/rocket
---

# Quickstart: Your First Pipeline

Get a SatTerC pipeline running in 5 minutes.
This guide walks through creating a minimal pipeline that computes soil moisture and evapotranspiration from synthetic data.

## Prerequisites

Follow the [Installation guide](installation.md) to install SatTerC and optional dependencies.

## Step 1: Generate a Config

Use the interactive setup command to create a configuration file:

```sh
satterc setup
```

This will prompt you to select models. Choose `splash` for this tutorial.
Accept the default paths when prompted.

Or skip the prompts and use defaults:

```sh
satterc setup --models splash --defaults
```

This creates a `config.toml` file that looks like:

```toml
[models.splash]

[inputs.daily]
path = "inputs/daily.nc"
vars = [
  "precipitation",
  "sunshine_fraction",
  "temperature",
]

[inputs.static]
path = "inputs/static.nc"
vars = [
  "elevation",
  "max_soil_moisture",
  "plant_type",
]

[outputs.daily]
path = "outputs/daily.nc"
vars = [
  "actual_evapotranspiration",
  "soil_moisture",
  "runoff",
]
```

## Step 2: Generate Synthetic Data

Create test data from the config:

```sh
mkdir -p inputs
satterc data-gen generate config.toml --grid 1,1 --duration 1y --seed 42
```

This creates NetCDF files at the paths specified in your config.

## Step 3: Visualise the Pipeline

See what the DAG looks like:

```sh
satterc graph config.toml --pdf
```

This produces `pipeline.pdf` showing all nodes and their dependencies.

## Step 4: Run the Pipeline

```sh
mkdir -p outputs
satterc run config.toml
```

This reads the input data, executes the DAG, and writes the output files to `outputs/daily.nc`.

## Step 5: Inspect the Results

Load the output in Python:

```python
import xarray as xr

ds = xr.open_dataset("outputs/daily.nc")
print(ds)
ds["soil_moisture"].plot()
```

## Next Steps

- Read about [how DAGs work](concepts.md) to understand the internals
- See the [Configuration reference](../usage/config.md) for all available options
- Browse the Examples for interactive notebooks (run `just export-all` to generate)
- Learn about [built-in models](../models/index.md) and how to compose them
