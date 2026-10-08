---
title: Drive conduit from Python
icon: lucide/code-2
---

# Drive conduit from Python

Everything the CLI does is available from Python, with no extras installed.

## In one call

`conduit.run` takes a path to a TOML config, or a `ParsedConfig` you have adjusted in Python:

```python
import conduit

report = conduit.run("config.toml")  # writes each [outputs.*] section
report.outputs["climate"]  # the Dataset that went into that section
report.written  # where each one landed, and how big it is

parsed = conduit.load_config("config.toml")
parsed.driver_config["scaling_factor"] = 2.0
report = conduit.run(parsed)  # same run, with a parameter changed first
```

A [`RunReport`](../../reference/modules/conduit.pipeline.md#conduit.pipeline.RunReport) holds the datasets, one `WrittenOutput` per destination, and the elapsed time.
Take paths from `written` rather than from the config, because a `[subset]` run adds a suffix to them.
A run from a `ParsedConfig` has no config text, so its outputs carry no [provenance stamp](../../reference/data-formats.md#output-provenance).

`conduit.dry_run` runs the same checks without executing anything and returns a [`DryRunReport`](../../reference/modules/conduit.pipeline.md#conduit.pipeline.DryRunReport), and `conduit.build_graph` returns the graph as a `graphviz.Digraph`.

Progress is logged to the `conduit.pipeline` logger at `INFO`.
The library installs no handler, so to see it:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

## Step by step

Taking the steps yourself lets you inspect individual nodes, plot intermediate results, override values between runs, or skip writing to disk.
These are the steps `conduit.run` takes:

```python
from conduit import build_driver, get_final_vars, get_outputs, load_inputs, save_outputs
from conduit.config import Config

parsed = Config(config_data).parse()  # 1. parse
parsed.annotations.apply()  # 2. contract policy
dr = build_driver(  # 3. build, and check contracts
    modules=parsed.modules,
    config=parsed.driver_config,
    node_specs=parsed.node_specs,
)
inputs = load_inputs(parsed.input_specs)  # 4. load
results = dr.execute(get_final_vars(parsed.output_specs), inputs=inputs)  # 5. execute
datasets = get_outputs(results, parsed.output_specs)  # 6. collect
save_outputs(datasets, parsed.output_specs)  # 7. write
```

### 1. Parse a config

A config can be a Python dict with the same structure as a [TOML config](../../reference/configuration.md):

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
parsed = Config(config_data).parse()
```

For a file, use `Config.load("config.toml")`, which resolves paths relative to the file, or `conduit.load_config("config.toml")`, which also parses it.
The resulting `ParsedConfig` holds one spec per config section; see [its reference](../../reference/modules/conduit.specs.md#conduit.specs.ParsedConfig).

### 2. Apply the contract policy

`parsed.annotations.apply()` sets the `[annotations]` policy, which is process-global in `xarray-annotated`.
Skip it and the DAG is checked under the default policy rather than your config's.

### 3. Build the driver

`build_driver()` constructs a Hamilton `Driver` and runs the contract check.
Pass `node_specs` whenever the config has `[[node]]` or `[[resample]]` entries.
The driver can be inspected with Hamilton's own methods, such as `dr.display_all_functions()` or `dr.visualize_path_between(...)`.

### 4. Load inputs

`load_inputs()` opens the input files and returns a flat dict of `DataArray`s keyed by node name.
When inputs carry a CRS, `latitude` and `longitude` nodes are computed too.

### 5. Execute

`dr.execute()` takes the node names you want; `get_final_vars()` lists the ones the outputs need.
You can request any node, which is handy for inspecting intermediates, and override a node's value without rebuilding:

```python
results = dr.execute(
    final_vars=["temperature_anomaly_climate"],
    inputs=inputs,
    overrides={"temperature_climate": my_custom_array},
)
```

### 6–7. Collect and write

`get_outputs()` merges the flat results into one `Dataset` per output section, ready for plotting or analysis.
`save_outputs()` writes them and returns the path written for each section; skip it if you only need the datasets in memory.

The [Python API](../../reference/python-api.md) page links every name used here to its signature.
