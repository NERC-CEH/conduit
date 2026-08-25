---
title: Bring your own module
icon: lucide/puzzle
---

# Bring your own module

This is where your science code goes.
Inline `[[node]]` expressions handle glue, but anything worth testing belongs in a Python module, and any importable module can become part of a pipeline.

A node is a plain function. conduit reads its signature to work out how it wires in.

## The conventions

conduit builds the DAG with [Hamilton](https://github.com/dagworks-inc/hamilton), which derives the graph from names:

| In your function | Becomes |
|---|---|
| the function name | the node name |
| a positional parameter name | the upstream node it consumes |
| the return value | the node's output |
| a keyword-only parameter, after `*` | a config parameter |

So a function called `soil_moisture_daily` produces a node called `soil_moisture_daily`, and its parameter `temperature_daily` binds to whatever produces `temperature_daily` — an input variable, another function, or an inline node.
Nothing else connects them.
That is what lets you add a computation without touching any existing code.

Node names must be unique across the whole pipeline, and input node names come from `{var}{suffix}` — see [Configuration › Inputs](../../reference/configuration.md#inputs) for how a file variable gets its node name.

## 1. Write the module

```python
# mypackage/indices.py
import xarray as xr


def aridity_index_daily(
    precipitation_daily: xr.DataArray,
    evapotranspiration_daily: xr.DataArray,
    *,
    floor: float = 1e-6,
) -> xr.DataArray:
    """Ratio of precipitation to evapotranspiration."""
    return precipitation_daily / (evapotranspiration_daily + floor)
```

`precipitation_daily` and `evapotranspiration_daily` must be produced somewhere else in the pipeline, typically by an `[inputs.daily]` section.
`floor` is keyword-only, which makes it a config parameter rather than an edge. Its default holds unless the config overrides it.

## 2. Declare contracts

Annotating the parameters and the return turns the function into a checkable node.
Add `@declare_units` and conduit validates and converts units at call time and stamps the output.
The annotations are readable statically, so it can also check this node's edges against its neighbours before anything runs.

```python
from typing import Annotated

import xarray as xr

from conduit import declare_units


@declare_units
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, "mm/day"],
    evapotranspiration_daily: Annotated[xr.DataArray, "mm/day"],
    *,
    floor: float = 1e-6,
) -> Annotated[xr.DataArray, "1"]:
    """Ratio of precipitation to evapotranspiration (dimensionless)."""
    return precipitation_daily / (evapotranspiration_daily + floor)
```

A pipeline runs perfectly well without any of this, but the contracts are most of what conduit adds, so they are worth writing.
[Declaring contracts](contracts.md) covers the other four facets and the decorator ordering rule.

## 3. Multiple outputs

To split one function into several named nodes, return a `TypedDict` and decorate with `@extract_fields` from `hamilton.function_modifiers`:

```python
from typing import TypedDict

import xarray as xr
from hamilton.function_modifiers import extract_fields


class _Water(TypedDict):
    runoff_daily: xr.DataArray
    soil_moisture_daily: xr.DataArray


@extract_fields(_Water)
def water_balance_daily(
    precipitation_daily: xr.DataArray,
    evapotranspiration_daily: xr.DataArray,
) -> _Water:
    ...
```

Each key becomes its own node, so `runoff_daily` and `soil_moisture_daily` can be consumed and requested independently.

## 4. Wire it in from config

Add a section carrying `_import_path`.
The section name is a free-form label; only `_import_path` is meaningful, and the remaining keys become config parameters:

```toml
[aridity]
_import_path = "mypackage.indices"
floor = 1e-4          # overrides the function's default
```

conduit recognises a fixed set of section names and treats every other section as one of your modules, which is why an unrecognised section without `_import_path` is an error rather than something quietly skipped.

Everything else is wired by name.
`aridity_index_daily`'s `precipitation_daily` parameter finds the `precipitation_daily` node on its own.

## Parameter names share one namespace

Keyword-only parameters from every config section are merged into one flat dictionary and injected by name.
Two modules declaring the same parameter name is a parse-time error naming both sections.

Prefix to disambiguate:

```toml
[aridity]
_import_path = "mypackage.indices"
aridity_floor = 1e-4
```

and name the parameter `aridity_floor` in the signature to match.
Worth choosing prefixed names from the start in a pipeline you expect to grow.

## Dependencies are yours

conduit does not manage what your module imports.
Whatever it needs has to be installed in the same environment.

## Where next

- [Declaring contracts](contracts.md) — units, dims, coords, dtype and frequency.
- [Test your pipeline](test-your-pipeline.md) — testing node functions and configs.
- [Inline nodes and fan-out](inline-nodes-and-fan-out.md) — the `[[node]]` form, for glue and for generating many nodes from one spec.
- [Configuration reference](../../reference/configuration.md) — every section and key.
