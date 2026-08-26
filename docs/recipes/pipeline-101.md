---
title: Pipeline 101
icon: lucide/rocket
---

# Pipeline 101

The smallest pipeline that still has every moving part.
One input file, one node function imported from a Python module, one node declared inline in the config, one output file.

It derives a temperature anomaly from 90 days of daily temperature at three sites, then reduces that anomaly to a per-site range.
Plain arrays throughout, so the wiring is all there is to look at.

The files live in [`recipes/pipeline_101`](https://github.com/NERC-CEH/conduit/tree/main/recipes/pipeline_101).

!!! note "Requirements"

    Install the documentation dependencies with `uv sync --group docs`.
    Rendering the graph also needs the Graphviz system executable — see the [installation guide](../guides/install.md).

## The node module

A conduit node is an ordinary xarray function.
The function name is the node name, each parameter name is the node it consumes, and the annotations declare the units.

```python
--8<-- "recipes/pipeline_101/nodes.py"
```

`@declare_units` turns the annotations from documentation into a contract.
It validates each input against its declared unit, converts where the units are compatible, and rejects them where they are not.

## The config

```toml
--8<-- "recipes/pipeline_101/config.toml"
```

Four sections, and between them they describe the whole graph:

`[inputs.climate]`
:   Loads `temperature` from `data/climate.nc` and exposes it as a node.
    The node name is the file variable plus the section's suffix, `{var}{suffix}`, so `temperature` here becomes `temperature_climate`.
    See [Configuration › Inputs](../reference/configuration.md#inputs) for the other two forms `vars` takes.

`[climate_nodes]`
:   Imports the node module. conduit recognises a fixed set of section names and treats anything else as one of your own modules, which is why an unrecognised section must carry `_import_path`, and why a typo is an error rather than a silently ignored section.

`[[node]]`
:   Declares a node inline. `expression` is ordinary Python evaluated with the named `inputs` in scope, and `units` declares the unit of its result.
    Use this for glue that does not deserve a module of its own.

`[outputs.climate]`
:   Chooses what to write. The mapping form aliases node name to file variable, so `temperature_anomaly_climate` lands in the file as `temperature_anomaly`.

## Run it

Generate the input first.
`make_data.py` writes a deterministic file, so everything below is reproducible.

```bash exec="true" source="block" result="text"
python recipes/pipeline_101/make_data.py
```

Render the graph before running anything.
Node labels carry the declared units, so a wiring mistake is often visible at this point.

```bash exec="true" source="block" result="text"
conduit graph recipes/pipeline_101/config.toml --png \
  --output recipes/pipeline_101/pipeline
```

The rendered graph is on the [notebook walkthrough](pipeline-101-demo.md) of this same pipeline.

Then validate.
`--dry-run` parses the config, opens the input headers, builds the DAG and checks every contract, without executing a node or writing a file.

```bash exec="true" source="block" result="text"
conduit run --dry-run recipes/pipeline_101/config.toml
```

Only now is it worth spending compute.

```bash exec="true" source="block" result="text"
conduit run recipes/pipeline_101/config.toml
```

## What was written

```bash exec="true" source="block" result="text"
python -c "
import xarray as xr

ds = xr.open_dataset('recipes/pipeline_101/results/anomaly.nc')
print(ds)
print()
print('units:', {k: v.attrs.get('units') for k, v in ds.data_vars.items()})
print('config recorded:', 'conduit_config_sha256' in ds.attrs)
"
```

The output carries the units declared on the nodes.
Its attributes also hold the config text that produced it and a SHA-256 of that text, so the file records how it was made.

## Next

- [Bring your own module](../guides/nodes/bring-your-own-module.md) — the conventions your Python must follow.
- [Declaring contracts](../guides/nodes/contracts.md) — units, dims, coords, dtype and frequency.
- [Inline nodes and fan-out](../guides/configs/inline-nodes-and-fan-out.md) — generating many nodes from one spec.
- [Configuration reference](../reference/configuration.md) — every section and key.
