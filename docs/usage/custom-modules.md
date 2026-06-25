---
title: Custom Modules
icon: lucide/puzzle
---

# Custom Modules

Extend SatTerC pipelines with your own Python modules.

## Overview

Any importable Python module can be added to a pipeline.
SatTerC uses the [Hamilton](https://github.com/dagworks-inc/hamilton) DAG framework, which means:

- Each **function** in your module becomes a **node** in the DAG.
- The **function name** is the node name.
- The **function parameters** are the node's dependencies (inputs).
- The **return value** is the node's output.

## Adding a Custom Module

### 1. Write the module

Create a Python module that follows Hamilton conventions:

```python
# mypackage/my_model.py

def my_output(temperature_daily, precipitation_daily, my_parameter):
    """Compute something interesting from daily inputs."""
    return temperature_daily * my_parameter + precipitation_daily
```

Key rules:

- Parameter names must match node names produced elsewhere in the pipeline (e.g., `temperature_daily` from `[inputs.daily]`).
- Return an `xarray.DataArray` (or a dict of DataArrays for multiple outputs).
- Define a `_Parameters()` function to declare configurable parameters (optional but recommended).

### 2. Declare parameters (optional)

Define a `_Parameters()` function to specify defaults and types:

```python
from dataclasses import dataclass

@dataclass
class _Parameters:
    my_parameter: float = 1.5
    another_param: str = "default"
```

This enables the `satterc setup` command to discover your module's parameters.

### 3. Reference it in your config

Use a TOML section with `_import_path`:

```toml
[my_custom_model]
_import_path = "mypackage.my_model"
my_parameter = 2.0
```

The section header (`my_custom_model`) is a human-readable label.
Only `_import_path` carries semantic meaning.
All other keys are passed as configuration parameters.

## Parameter Namespacing

All parameters are merged into a single flat dictionary.
If your parameter name clashes with a built-in model, prefix it:

```toml
[my_custom_model]
_import_path = "mypackage.my_model"
my_model_temperature_daily = true  # prefixed to avoid conflict
```

## Example: A Simple Custom Model

Here's a complete example that computes a custom drought index:

```python
# mypackage/drought_index.py

from dataclasses import dataclass
import xarray as xr


@dataclass
class _Parameters:
    threshold_mm: float = 50.0


def drought_index(
    precipitation_daily: xr.DataArray,
    threshold_mm: float,
) -> xr.DataArray:
    """Compute a simple drought index: 1 when precipitation < threshold, 0 otherwise."""
    return (precipitation_daily < threshold_mm).astype(float)
```

Config:

```toml
[models.splash]

[my_drought]
_import_path = "mypackage.drought_index"
threshold_mm = 30.0

[inputs.daily]
path = "data/daily.nc"
vars = ["precipitation", "temperature"]

[inputs.static]
path = "data/static.nc"
vars = ["elevation"]

[outputs.daily]
path = "results/daily.nc"
vars = ["drought_index", "soil_moisture"]
```

## Using Custom Modules with `satterc setup`

During interactive setup, you can add custom module paths.
The setup tool will attempt to import the module and read its `_Parameters` to include them in the generated config.

## Dependencies

Ensure any packages your custom module requires are installed in your environment.
SatTerC does not manage dependencies for custom modules.
