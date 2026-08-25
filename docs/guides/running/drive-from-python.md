---
title: Drive conduit from Python
icon: lucide/code-2
---

# Drive conduit from Python

The library is the product and `conduit run` is a wrapper over `conduit.run`, so everything the CLI does is available from Python with nothing extra installed.

Taking the steps yourself buys you control: inspect individual nodes, plot intermediate results, override values between runs, or skip writing to disk entirely.
This guide walks the same steps `run` takes, and [the whole thing in one call](#the-whole-thing-in-one-call) is at the end.

/// admonition | Import convention
    type: info

All examples below assume:

```python
from conduit import build_driver, get_final_vars, get_outputs, load_inputs, save_outputs
from conduit.config import Config
```
///

## 1. Build a config

A pipeline is described by a config — a Python dict with the same structure as a
[TOML config](../../reference/configuration.md) file. Pass it straight to `Config`:

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

Already have a file? Use `Config.load("config.toml")` (paths resolve relative to the
file) or `Config.loads(toml_string)`. The convenience function
`conduit.load_config("config.toml")` does load-and-parse in one call, returning the
`ParsedConfig` from the next step.
///

## 2. Parse it

`.parse()` validates the config and returns a `ParsedConfig` dataclass with everything
the pipeline needs:

```python
parsed = Config(config_data).parse()
```

Key fields: `modules` (module identifiers), `driver_config` (parameters for the driver
and modules), `node_specs` (the `[[node]]` / `[[resample]]` specs), `input_specs` /
`output_specs` (per-section `IOSpec`s), plus the parsed `cache_spec`, `blocking_spec`,
`subset_spec` and `annotations` (an `AnnotationPolicySpec`).

## 3. Apply the contract policy

The `[annotations]` section is *not* applied by parsing — it sets `xarray-annotated`'s
process-global policy, which the build-time contract check then consults. Apply it
before building, exactly as the CLI does:

```python
parsed.annotations.apply()
```

Skip this and your DAG is checked under the default policy rather than the one your
config asked for.

## 4. Build the driver

`build_driver()` constructs a Hamilton `Driver` and runs the build-time contract check:

```python
dr = build_driver(
    modules=parsed.modules,
    config=parsed.driver_config,
    node_specs=parsed.node_specs,
)
```

`node_specs` is required whenever the config defines `[[node]]` or `[[resample]]`
entries — it is what the built-in `node` module is generated from.

The driver is the DAG runtime — it resolves dependencies and executes nodes in order.
You can inspect it now with `dr.display_all_functions()` or
`dr.visualize_path_between(...)`.

## 5. Load inputs

`load_inputs()` reads the files in `input_specs` and returns a flat dict of named
`DataArray`s, keyed by node name:

```python
inputs = load_inputs(parsed.input_specs)
```

Node names follow the config's naming: `{var}{suffix}` for list-form `vars`, or the
explicit `{node_name: file_var}` alias for mapping-form. Grid coordinates
(`latitude`, `longitude`) are computed automatically when inputs carry a CRS.

## 6. Execute

Call `dr.execute()` with the node names you want. `get_final_vars()` turns
`output_specs` into that flat list:

```python
results = dr.execute(get_final_vars(parsed.output_specs), inputs=inputs)
```

You can also request any node by name — handy for inspecting intermediates:

```python
anomaly = dr.execute(["temperature_anomaly_climate"], inputs=inputs)
```

Or override a node's value at runtime without rebuilding the DAG — useful when
re-running with different parameters:

```python
results = dr.execute(
    final_vars=["temperature_anomaly_climate"],
    inputs=inputs,
    overrides={"temperature_climate": my_custom_array},
)
```

## 7. Inspect and save

`dr.execute()` returns a flat dict of `DataArray`s. `get_outputs()` merges them into
per-section `Dataset`s (the form most plotting/analysis expects):

```python
datasets = get_outputs(results, parsed.output_specs)
# datasets["climate"] -> xr.Dataset
```

Write them with `save_outputs()`:

```python
save_outputs(datasets, parsed.output_specs)
```

/// admonition | Skipping disk writes
    type: tip

In a notebook you can skip `save_outputs()` — the Datasets from `get_outputs()` are
ready for xarray's plotting methods, matplotlib, or any other library.
///

## Putting it together

```python
from conduit import build_driver, get_final_vars, get_outputs, load_inputs, save_outputs
from conduit.config import Config

parsed = Config(config_data).parse()          # 1–2. build + parse
parsed.annotations.apply()                     # 3. contract policy
dr = build_driver(                             # 4.
    modules=parsed.modules,
    config=parsed.driver_config,
    node_specs=parsed.node_specs,
)
inputs = load_inputs(parsed.input_specs)       # 5.
results = dr.execute(get_final_vars(parsed.output_specs), inputs=inputs)  # 6.
datasets = get_outputs(results, parsed.output_specs)  # 7.
save_outputs(datasets, parsed.output_specs)
```

## The whole thing in one call

Every step above is what `conduit.run` does, so when you want the outputs and nothing
else, call it directly. It takes a path to a TOML config, or a `ParsedConfig` you have
already adjusted in Python:

```python
import conduit

datasets = conduit.run("config.toml")   # writes each [outputs.*] section, returns them

parsed = conduit.load_config("config.toml")
parsed.driver_config["scaling_factor"] = 2.0
datasets = conduit.run(parsed)          # same run, with the spec tweaked first
```

`conduit.dry_run` validates the same pipeline without executing it and returns a
[`DryRunReport`](../../reference/modules/conduit.pipeline.md) — the stage list `conduit run --dry-run`
prints. `conduit.build_graph` returns the styled `graphviz.Digraph` that
`conduit graph` writes to disk, which renders inline in a notebook.

/// admonition | Provenance
    type: info

A run from a config *path* stamps the config text and its SHA-256 onto every output, so
a store says how it was made. A run from a `ParsedConfig` has no text to stamp, so it
stamps nothing.
///

## Where next

- [Python API reference](../../reference/python-api.md) — signatures for every function used here.
- [Run and visualise](run-and-visualise.md) — the CLI equivalent.
- [Test your pipeline](../authoring/test-your-pipeline.md) — these same calls, from a test.
- [Configuration reference](../../reference/configuration.md) — the config schema.
