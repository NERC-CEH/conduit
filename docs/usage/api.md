---
title: Python API
icon: lucide/code-2
---

# Python API

conduit can be driven from any Python script or notebook using the Python API.
This gives you fine-grained control: you can inspect individual nodes, plot
intermediate results, or skip writing outputs to disk entirely. The CLI
(`conduit run`) is a thin wrapper over the same API, useful when you just want
to run a config file end-to-end.

This page walks through the key steps — building a config, parsing it, loading
inputs, building the driver, and executing the pipeline.

/// admonition | Import convention
    type: info

All examples on this page assume the following imports:

```python
from conduit import build_driver, get_final_vars, get_outputs, load_inputs
from conduit.config import Config
```
///

---

## Step 1: Build a config

A pipeline is described by a configuration — a Python dictionary with the same
structure as a conduit [TOML configuration](config.md) file. You can pass this
dict directly to `Config` instead of writing a TOML file to disk.

```python
config_data = {
    "inputs": {
        "climate": {"path": "data/climate.nc", "vars": ["temperature"]},
    },
    "node": [
        {
            "name": "temperature_anomaly_climate",
            "inputs": ["temperature_climate"],
            "expression": "temperature_climate - temperature_climate.mean('time')",
            "units": "degC",
        },
    ],
    "outputs": {
        "climate": {"path": "results/anomaly.nc", "vars": ["temperature_anomaly"]},
    },
}
```

/// admonition | Loading from a file
    type: note

If you already have a config file, use `Config.load("config.toml")` instead.
Paths are resolved relative to the file's location.
`Config.loads(toml_string)` parses a TOML string directly — useful when the
config is embedded in a notebook or loaded from a database.
///

---

## Step 2: Parse it

Call `.parse()` to validate the config and extract a `ParsedConfig` — a
lightweight dataclass with everything the pipeline needs.

```python
parsed = Config(config_data).parse()
```

`ParsedConfig` has four fields:

| Field | Type | Description |
|-------|------|-------------|
| `modules` | `list[str]` | Module identifiers (e.g. `["node"]`, or a dotted `_import_path`) |
| `driver_config` | `dict` | Parameters passed through to the Hamilton driver and modules |
| `input_specs` | `dict[str, IOSpec]` | Per-section input specifications (paths and variable lists) |
| `output_specs` | `dict[str, IOSpec]` | Per-section output specifications |

---

## Step 3: Build the driver

Pass the modules and driver config to `build_driver()` to construct a Hamilton
`Driver`:

```python
dr = build_driver(
    modules=parsed.modules,
    config=parsed.driver_config,
)
```

The driver is the DAG runtime — it resolves dependencies, checks that all
required nodes are present, and executes computations in the correct order.

At this point you can inspect the DAG with helper methods like
`dr.visualize_execution()` or `dr.display_all_functions()` to understand what
will be computed.

---

## Step 4: Load inputs

`load_inputs()` reads the data files declared in `input_specs` and returns a
flat dictionary of named `xarray.DataArray` objects, keyed by Hamilton node
name:

```python
inputs = load_inputs(parsed.input_specs)
```

Temporal variables are keyed as `{var}_{freq}` (e.g. `temperature_daily`).
Static variables have no suffix (e.g. `elevation`). Grid coordinates
(`latitude`, `longitude`) are computed automatically when the inputs carry a CRS.

---

## Step 5: Run the pipeline

Call `driver.execute()` with the list of output nodes you want. Use
`get_final_vars()` to convert `output_specs` into the flat list of Hamilton
node names:

```python
results = dr.execute(
    get_final_vars(parsed.output_specs),
    inputs=inputs,
)
```

`get_final_vars()` handles the `{var}_{freq}` naming convention — including the
special case for `static` variables, which do not receive a frequency suffix.

You can also request outputs for a single frequency by passing a subset:

```python
daily_results = dr.execute(
    get_final_vars({"daily": parsed.output_specs["daily"]}),
    inputs=inputs,
)
```

Or request any node directly by name, without using `get_final_vars()` at all:

```python
sm = dr.execute(["soil_moisture_daily"], inputs=inputs)
```

You can also override any node value at runtime without rebuilding the DAG — useful for repeatedly running the pipeline with different parameter values:

```python
outputs = dr.execute(
    final_vars=["soil_moisture_daily"],
    overrides={"max_soil_moisture": custom_max_sm_array},
)
```

---

## Step 6: Inspect and save outputs

The raw results from `dr.execute()` are a flat dictionary of `xarray.DataArray`
objects. Call `get_outputs()` to merge them into per-frequency `xarray.Dataset`
objects — this is the format most plotting and analysis code expects:

```python
datasets = get_outputs(results, parsed.output_specs)
# datasets["daily"]  → xr.Dataset with variables named without the suffix
```

To write the outputs to disk, call `save_outputs()`:

```python
from conduit import save_outputs

save_outputs(datasets, parsed.output_specs)
```

/// admonition | Skipping disk writes
    type: tip

If you are in a notebook and just want to plot or explore, you can skip
`save_outputs()` entirely — the Datasets from `get_outputs()` are ready to
use with `xarray`'s plotting methods, `matplotlib`, or any other library.
///

---

## Putting it all together

Here is a complete script that ties all the steps together:

```python
from conduit import build_driver, get_final_vars, get_outputs, load_inputs, save_outputs
from conduit.config import Config

# 1. Build config
config_data = {
    "inputs": {"climate": {"path": "data/climate.nc", "vars": ["temperature"]}},
    "node": [
        {
            "name": "temperature_anomaly_climate",
            "inputs": ["temperature_climate"],
            "expression": "temperature_climate - temperature_climate.mean('time')",
            "units": "degC",
        },
    ],
    "outputs": {
        "climate": {"path": "results/anomaly.nc", "vars": ["temperature_anomaly"]},
    },
}

# 2. Parse
parsed = Config(config_data).parse()

# 3. Build driver
dr = build_driver(modules=parsed.modules, config=parsed.driver_config)

# 4. Load inputs
inputs = load_inputs(parsed.input_specs)

# 5. Execute
results = dr.execute(get_final_vars(parsed.output_specs), inputs=inputs)

# 6. Inspect and save
datasets = get_outputs(results, parsed.output_specs)
save_outputs(datasets, parsed.output_specs)
```

**From here**, explore the [Configuration reference](config.md) and the
[CLI](cli.md) to build your own pipelines.
