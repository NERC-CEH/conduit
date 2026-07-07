---
title: Add unit contracts
icon: lucide/shield-check
---

# Add unit contracts

conduit's flagship feature is **whole-DAG contract checking**: it proves your whole
pipeline is consistent *before any compute runs*, straight from your type annotations.
This tutorial layers units onto the pipeline from
[Your first pipeline](first-pipeline.md) and shows conduit catch a mistake at build
time.

We use units here because they are the most familiar contract, but the same machinery
covers dimensions, coordinates and dtypes too — see
[Contracts before compute](../concepts/contracts.md).

## Step 1: A node stamps its declared unit

You already met one half of this in the first tutorial: the inline `[[node]]` declared
`units = "degC"`, and the output file carried that unit. Declaring a unit turns a node
into a *typed producer* — a node whose output unit conduit knows statically.

```toml
[[node]]
name = "temperature_anomaly_climate"
inputs = ["temperature_climate"]
expression = "temperature_climate - temperature_climate.mean('time')"
units = "degC"          # <- the output is stamped with this unit
```

## Step 2: A node *requires* a unit — and conduit converts

Declaring a unit on an inline `[[node]]` covers its *output*. To declare what a node
*requires* of its inputs, write a Python function and annotate its parameters. Create
a module `mypipeline/contracts.py`:

```python
# mypipeline/contracts.py
from typing import Annotated

import xarray as xr

from conduit import declare_units


@declare_units
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, "Pa"],
) -> Annotated[xr.DataArray, "Pa"]:
    """Deviation of pressure from its time mean."""
    return pressure_climate - pressure_climate.mean("time")
```

`@declare_units` reads the `Annotated[DataArray, "<unit>"]` hints: it validates that
`pressure_climate` arrives in pascals and stamps the return value as pascals.

Now suppose your input file stores pressure in **hectopascals**. Add it to the config
and wire the module in:

```toml
[inputs.climate]
path = "climate.nc"
vars = ["temperature", "pressure"]      # pressure stored in hPa

[contracts]
_import_path = "mypipeline.contracts"

[outputs.climate]
path = "anomaly.nc"
vars = ["temperature_anomaly", "pressure_anomaly"]
```

When you run this, conduit sees the input is `hPa` and the node wants `Pa`, so it
**converts** the data automatically before the function runs. Compatible units are
reconciled for you; you never hand-write `* 100`.

## Step 3: See a mismatch caught *before* compute

Now break it on purpose. Change the annotation to something dimensionally
incompatible with pressure — say metres:

```python
@declare_units
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, "m"],   # metres — wrong!
) -> Annotated[xr.DataArray, "m"]:
    ...
```

`m` (length) and `hPa` (pressure) are not interconvertible. Because the producer
(`pressure_climate`, from an input declared/stored in `hPa`) and the consumer both
declare a unit, conduit rejects the edge — and it does so at **build time**, before a
single node executes. You can surface this without running anything:

```sh
conduit run config.toml --dry-run
```

`--dry-run` parses the config, builds the DAG (running the whole-graph contract
check), checks the wiring, and validates your input files' declared units against
every consumer — then stops. A `hPa`-vs-`Pa` slip, a transposed axis, or a renamed
input is caught here, not part-way through a long run. See
[Validate before running](../guides/validate-before-running.md) for the full checklist.

## Step 4: Tune the strictness

By default a unit problem is a warning. Add an `[annotations]` section to make units a
hard error, or to turn checking off:

```toml
[annotations]
mode = "strict"   # "strict" | "warn" (default) | "off"
exact = false     # true = reject value-changing conversions (e.g. hPa where Pa is declared)
```

- `mode = "strict"` raises on any unit problem; `"warn"` reports and continues;
  `"off"` disables contract checking entirely.
- `exact = true` forbids *implicit conversion*: a dimensionally-compatible but
  value-changing unit (like `hPa` where `Pa` is declared) is rejected rather than
  silently converted.

## What you learned

- Declaring `units` on a `[[node]]` (output) or with `Annotated` parameters
  (requirements) turns nodes into typed producers and consumers.
- conduit **converts** compatible units and **rejects** incompatible ones.
- The check runs over the *whole graph, before compute* — and `--dry-run` lets you
  run it against your real files without executing the pipeline.

## Next steps

- [Contracts before compute](../concepts/contracts.md) — why this is possible, and how
  it generalises to dims, coords and dtypes.
- [Bring your own module](../guides/bring-your-own-module.md) — the full module
  authoring conventions.
- [Configuration reference › `[annotations]`](../reference/configuration.md#annotations)
  — every policy key.
