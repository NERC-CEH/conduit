---
title: Bring your own module
icon: lucide/puzzle
---

# Bring your own module

Inline `[[node]]` expressions are handy for glue, but real work lives in your own
Python. Any importable module can become part of a conduit pipeline. This guide covers
the conventions your module must follow and how to wire it in from config.

## The conventions

conduit builds the DAG with [Hamilton](https://github.com/dagworks-inc/hamilton), so a
module is just plain functions that follow a few naming rules:

- **Function name = node name.** A public function `soil_moisture_daily` produces a DAG
  node called `soil_moisture_daily`.
- **Parameter names = upstream node names.** A parameter `temperature_daily` is wired to
  whatever produces the `temperature_daily` node (an input, another function, or an
  inline node).
- **Return value = the node's output** — an `xarray.DataArray` (single output), or use
  `@extract_fields` for multiple outputs (see below).
- **Keyword-only parameters (after `*`) = config parameters**, supplied from the
  module's own config section.

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

- `precipitation_daily` and `evapotranspiration_daily` are **inputs** — they must be
  produced somewhere else in the pipeline (e.g. an `[inputs.daily]` section).
- `floor` is a **config parameter** because it is keyword-only (it comes after `*`).
  Its default is used unless the config overrides it.

## 2. Declare contracts (optional, recommended)

Annotate parameters and the return with `Annotated[DataArray, "<unit>"]` and decorate
with `@declare_units` to have conduit validate/convert units and stamp the output.
`@declare_schema` does the same for dims, coords and dtype. Declaring contracts lets
the [whole-DAG contract check](../concepts/contracts.md) prove this node's edges before
compute.

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

## 3. Multiple outputs

To split one function into several named nodes, return a `TypedDict` and decorate with
`@extract_fields` (from `hamilton.function_modifiers`):

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

Each key becomes its own DAG node (`runoff_daily`, `soil_moisture_daily`).

## 4. Reference it in your config

Add a section whose body carries `_import_path`. The section header is a free-form
label; only `_import_path` is meaningful. Remaining keys become config parameters:

```toml
[aridity]
_import_path = "mypackage.indices"
floor = 1e-4          # overrides the function's default
```

Everything is wired by name — `aridity_index_daily`'s `precipitation_daily` parameter
binds to the `precipitation_daily` node automatically.

## Parameter namespacing

All config parameters are merged into a single flat dictionary and injected into
functions by name. If two modules declare a parameter with the same name, conduit
raises a conflict error at parse time. Disambiguate by prefixing:

```toml
[aridity]
_import_path = "mypackage.indices"
aridity_floor = 1e-4     # prefixed to avoid clashing with another module's `floor`
```

(then name the keyword-only parameter `aridity_floor` in the function signature).

## Dependencies

conduit does not manage your module's dependencies — make sure any packages it imports
are installed in the same environment.

## See also

- [Inline nodes & fan-out](inline-nodes-and-fan-out.md) — the `[[node]]` alternative for
  glue and templated node generation.
- [Add unit contracts](../get-started/units-and-contracts.md) — a hands-on units
  walkthrough.
- [Configuration reference](../reference/configuration.md) — every config section.
