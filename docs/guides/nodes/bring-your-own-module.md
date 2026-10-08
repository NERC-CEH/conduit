---
title: Bring your own module
icon: lucide/puzzle
---

# Bring your own module

Your science code goes in a Python module: a single `.py` file beside your config, or an installed package.
Inline `[[node]]` expressions are fine for glue, but anything worth testing belongs in a module.

## The conventions

A node is a plain function, and conduit reads its signature to wire it in:

| In your function | Becomes |
|---|---|
| the function name | the node name |
| a positional parameter name | the upstream node it consumes |
| the return value | the node's output |
| a keyword-only parameter, after `*` | a config parameter |

A function called `soil_moisture_daily` produces a node called `soil_moisture_daily`, and its parameter `temperature_daily` binds to whatever produces `temperature_daily`: an input variable, another function, or an inline node.
Node names must be unique across the pipeline.
Input nodes are named `{var}{suffix}`; see [Configuration › Inputs](../../reference/configuration.md#inputs).

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

`precipitation_daily` and `evapotranspiration_daily` must be produced elsewhere in the pipeline, typically by an `[inputs.daily]` section.
`floor` is keyword-only, so it is a config parameter rather than an edge, and its default holds unless the config overrides it.

## 2. Declare contracts

Annotate the parameters and return value, and add `@declare_units`:

```python
from typing import Annotated

import xarray as xr

from xarray_annotated.units import declare_units


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

At call time, the decorator validates and converts the inputs' units and stamps the output's.
Before anything runs, conduit reads the same annotations to check this node's edges against its neighbours.
A pipeline runs without contracts, but they are most of what conduit adds.
[Declaring contracts](contracts.md) covers the other facets and the decorator-ordering rule.

## 3. Multiple outputs

To split one function into several nodes, return a `TypedDict` and decorate with Hamilton's `@extract_fields`:

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
) -> _Water: ...
```

Each key becomes its own node, so `runoff_daily` and `soil_moisture_daily` can be consumed and requested independently.

## 4. Wire it in from config

Add a section with an `_import_path`.
The section name is a free-form label, and every other key sets a config parameter:

```toml
[aridity]
_import_path = "mypackage.indices"
floor = 1e-4          # overrides the function's default
```

Everything else is wired by name.

conduit treats any section it does not recognise as one of your modules, so a section without an `_import_path` is an error, unless an installed package has [registered a module](#modules-an-installed-package-provides) under that name.
A misspelt section name is therefore never silently skipped.

## Two ways to name a module

`_import_path` takes either form, told apart by the `.py` ending:

| Written as | Means | Use it when |
|---|---|---|
| `"nodes.py"`, `"lib/nodes.py"` | a file, relative to **the config file's directory** | you have a file of functions next to your config |
| `"/shared/models/nodes.py"` | a file, at an absolute path | several configs in different directories share one module |
| `"mypackage.indices"` | a dotted module name, imported from your environment | the code is an installed package |

A relative path resolves against the config, not your working directory, so a config and its module travel together:

```toml
# in ~/work/aridity/config.toml — finds ~/work/aridity/nodes.py
[aridity]
_import_path = "nodes.py"
```

```bash
cd /anywhere
conduit run ~/work/aridity/config.toml   # still works
```

A dotted name is an ordinary Python import, so the package must be installed in the environment you run in.
Either way, whatever your module imports must be installed there too; conduit does not manage your dependencies.

!!! warning "A single-file module cannot import a sibling file"

    A `.py` module is loaded from its path, and its directory is not added to Python's import path.
    It can import installed packages, but not a loose file beside it:

    ```python
    # nodes.py, next to config.toml
    import helpers  # ✗ ModuleNotFoundError under `conduit run`
    import xarray as xr  # ✓ installed
    ```

    This can appear to work in a notebook started from the same directory, because Python puts the working directory on the path.
    It will fail under `conduit run` and from anywhere else.

    Code spread across several files should be an installed package, named by a dotted `_import_path`.
    With [uv](https://docs.astral.sh/uv/), that means a `pyproject.toml` and `uv pip install -e .`; see the [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

## Modules an installed package provides

A package built on conduit can register its modules, and a config then names one by its section header alone:

```toml
# `science` is installed, and registers a module called `diagnostics`
[diagnostics]
threshold = 0.3
```

`--dry-run` reports which package supplied each such section, and an explicit `_import_path` always takes precedence.
[Register modules from a package](../../extending/register-modules.md) covers the package author's side.

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
In a pipeline you expect to grow, choose prefixed names from the start.
