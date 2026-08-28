---
title: Declaring contracts
icon: lucide/shield-check
---

# Declaring contracts

A contract is a claim your node makes about the data on one of its edges, written as an ordinary type annotation:

```python
from typing import Annotated

import xarray as xr

from conduit import declare_units


@declare_units
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, "mm/day"],
    evapotranspiration_daily: Annotated[xr.DataArray, "mm/day"],
) -> Annotated[xr.DataArray, "1"]:
    ...
```

conduit checks every such claim across the whole graph before any node runs.
This page is about writing them.
For the pre-flight that runs the checks against your real files, see [Validate before running](../validate/validate-before-running.md).
[Contracts and the whole-graph check](../../concepts/contracts.md) covers why a before-compute check is possible at all.

## The five facets

| Facet | Declares | Example |
|---|---|---|
| units | the physical unit, via pint and cf-xarray | `"mm/day"`, `"Pa"`, `"1"` for dimensionless |
| dims | the dimension names | `Dims("time", "site")` |
| coords | required coordinate variables | `Coords("time")` |
| dtype | the array's element type | `Dtype("float32")` |
| freq | how often the time axis ticks, and on what phase | `Freq("7D")`, `Freq("W-SUN")` |

A bare string in the annotation metadata is always a unit.
Every other facet uses a marker, so nothing needs disambiguating:

```python
from typing import Annotated

import xarray as xr
from conduit import Freq, declare_freq, declare_units


@declare_units
@declare_freq
def weekly_mean(
    temperature_daily: Annotated[xr.DataArray, "degC", Freq("D")],
) -> Annotated[xr.DataArray, "degC", Freq("W-SUN")]:
    ...
```

An *unanchored* frequency compares spacing only, so `Freq("7D")` accepts any weekly axis.
An *anchored* one also pins the phase, so `Freq("W-SUN")` rejects an axis landing on Wednesdays.
That is what catches a resample offset by a day.

!!! warning "Decorator order matters"

    `declare_units` must be the outermost decorator: `declare_units(declare_freq(declare_schema(fn)))`.
    It is the only one that may convert values rather than merely validate them, so it has to see the arguments first.

An inline `[[node]]` declares the same facets with `units`, `dims`, `coords`, `dtype` and `freq` keys — see [Configuration › Nodes](../../reference/configuration.md#nodes).

## Producers and consumers

Declaring a unit on a node's **output** makes it a typed producer, and conduit knows that unit statically:

```toml
[[node]]
name = "temperature_anomaly_climate"
inputs = ["temperature_climate"]
expression = "temperature_climate - temperature_climate.mean('time')"
units = "degC"          # the output is stamped with this
```

Annotating a function's **parameters** declares what it requires of its inputs.
`@declare_units` reads those hints, validates each argument, and stamps the return value:

```python
@declare_units
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, "Pa"],
) -> Annotated[xr.DataArray, "Pa"]:
    """Deviation of pressure from its time mean."""
    return pressure_climate - pressure_climate.mean("time")
```

An edge is checked wherever both ends declare a contract.

## Compatible units are converted for you

Suppose your file stores pressure in hectopascals and the node above wants pascals.
conduit converts the data before the function runs, so you never hand-write `* 100`.
A unit that is only spelled differently, `"pascal"` for `"Pa"`, is relabelled without touching the values.

Incompatible units are another matter.
Change that annotation to metres:

```python
@declare_units
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, "m"],   # length, not pressure
) -> Annotated[xr.DataArray, "m"]:
    ...
```

Length and pressure do not interconvert, so conduit rejects the edge when the driver is built, naming both nodes and the facet that failed.
Nothing has been computed at that point, and `conduit run config.toml --dry-run` will show you the same failure without executing anything.

## Choosing the strictness

The `[annotations]` section sets policy for the whole pipeline:

```toml
[annotations]
mode = "warn"           # "strict" | "warn" (default) | "off"
on_inexact = "convert"  # "convert" (default) | "warn" | "error"
```

`mode` decides whether a unit problem raises, reports, or is ignored entirely.

`on_inexact` governs implicit conversion, and only a *value-changing* conversion consults it.
`"convert"` scales silently, `"warn"` scales and tells you, `"error"` refuses.
Set it to `"warn"` when you want every conversion in the run to be visible.
The flux recipe does this, on the grounds that a kelvin-to-Celsius conversion is worth seeing.
Its `flux.nc` stores air temperature in kelvin, while `partition_fluxes` declares `tair` in `degC` because its respiration term is a $Q_{10}$ relation written for Celsius.
Handed kelvin, that term returns respiration around $10^8$ rather than $4$, and nothing downstream would look obviously wrong.
The declaration is what makes the conversion happen; a bare `tair` parameter would have quietly used kelvin.

Every policy key, `on_uninferable` included, is in the [`[annotations]` reference](../../reference/configuration.md#annotations).

## Contracts across a passthrough node

Some nodes transform data while preserving its facets.
Resampling is the usual case: `temperature_weekly` should inherit whatever `temperature_daily` declared.
These nodes are tagged **passthrough**, and the checker carries the upstream contract across them, so an edge running through a resample is still covered end to end.

That happens per facet, since a passthrough preserves some and changes others.
A resample preserves units.
It does not preserve frequency, since frequency is what it changes, so a `[[resample]]` declares its own output frequency and becomes an ordinary checkable producer for that facet.
Declare `Freq("W-SUN")` downstream and a mistyped `W-WED` offset fails when the driver is built.

`[[resample]]` produces passthrough nodes; you can mark your own inline `[[node]]` passthrough too.

## What contracts will not catch

Anything that leaves the shape and units of an edge unchanged.
[Contracts and the whole-graph check](../../concepts/contracts.md#what-contracts-cannot-catch) sets out where the line falls, and [Resampling and units](resampling-and-units.md) works through the trap you are most likely to hit.

## Where next

- [Bring your own module](bring-your-own-module.md) — the rest of the authoring conventions.
- [Validate before running](../validate/validate-before-running.md) — running the checks against real files.
- [Test your pipeline](../validate/test-your-pipeline.md) — for everything contracts cannot cover.
