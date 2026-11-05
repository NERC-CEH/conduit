---
title: Declaring contracts
icon: lucide/shield-check
---

# Declaring contracts

A contract is a claim your node makes about the data on one of its edges, written as an ordinary type annotation:

```python
from typing import Annotated

import xarray as xr
import xarray_annotated as xra
from xarray_annotated import Unit


@xra.enforce
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, Unit("mm/day")],
    evapotranspiration_daily: Annotated[xr.DataArray, Unit("mm/day")],
) -> Annotated[xr.DataArray, Unit("1")]: ...
```

The decorator and markers come from [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), whose [API reference](https://jmarshrossney.github.io/xarray-annotated/api/package.html) documents them in full.
catena checks every such claim across the whole graph before any node runs; [Contracts and the whole-graph check](../../concepts/contracts.md) explains how.

## The five facets

| Facet | Declares | Example |
|---|---|---|
| units | the physical unit, via pint and cf-xarray | `Unit("mm/day")`, `Unit("Pa")`, `Unit("1")` for dimensionless |
| dims | the dimension names | `Dims("time", "site")` |
| coords | required coordinate variables | `Coords("time")` |
| dtype | the array's element type: a width is exact, and `float`, `int` and the like mean any width | `Dtype("float32")`, `Dtype("float")` |
| freq | how often the time axis ticks, and on what phase | `Freq("7D")`, `Freq("W-SUN")`, `Freq("month")`, `Freq("D", gaps_ok=True)` |

One `@xra.enforce` checks every facet declared on a signature:

```python
from typing import Annotated

import xarray as xr
import xarray_annotated as xra
from xarray_annotated import Freq, Unit


@xra.enforce
def weekly_mean(
    temperature_daily: Annotated[xr.DataArray, Unit("degC"), Freq("D")],
) -> Annotated[xr.DataArray, Unit("degC"), Freq("W-SUN")]: ...
```

!!! warning "A bare string is not a unit"

    `Annotated[xr.DataArray, "Pa"]` is only a description.
    It declares nothing, so nothing checks it and nothing raises.

An *unanchored* frequency compares spacing only, so `Freq("7D")` accepts any weekly axis.
An *anchored* one also pins the phase, so `Freq("W-SUN")` rejects an axis landing on Wednesdays, catching a resample offset by a day.
A *calendar step* (`"month"`, `"3month"`, `"year"`, `"2year"`) requires one value per step on any day, so `Freq("month")` accepts monthly means stamped at midpoints.
`Freq("D", gaps_ok=True)` declares daily values on an axis that may have holes: every step must be a whole number of days, and the smallest must be one day.

An inline `[[node]]` declares the same facets with `units`, `dims`, `coords`, `dtype` and `freq` keys — see [Configuration › Nodes](../../reference/configuration.md#nodes).
Its `freq` is a plain string, so `gaps_ok` can only be declared on a Python node.

## Producers and consumers

Declaring a unit on a node's **output** makes it a typed producer, whose unit catena knows without running it:

```toml
[[node]]
name = "temperature_anomaly_climate"
inputs = ["temperature_climate"]
expression = "temperature_climate - temperature_climate.mean('time')"
units = "degC"          # the output must already carry this
```

Annotating a function's **parameters** declares what it requires of its inputs.
`@xra.enforce` reads those hints, then checks each argument and the return value:

```python
@xra.enforce
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, Unit("Pa")],
) -> Annotated[xr.DataArray, Unit("Pa")]:
    """Deviation of pressure from its time mean."""
    return pressure_climate - pressure_climate.mean("time")
```

An edge is checked wherever both ends declare a contract.

## Different units are an error

Suppose your file stores pressure in hectopascals and the node above wants pascals.
Nothing converts it for you, because whether a conversion is correct depends on the quantity, so the node raises `ValueError`.
A unit that is only spelled differently, `"pascal"` for `"Pa"`, passes, and the values are not touched.

Declarations are held to the same rule.
Suppose the node producing `pressure_climate` declares pascals, and this one declares hectopascals:

```python
@xra.enforce
def pressure_anomaly_climate(
    pressure_climate: Annotated[xr.DataArray, Unit("hPa")],
) -> Annotated[xr.DataArray, Unit("hPa")]: ...
```

catena rejects the edge when the driver is built, naming both nodes and the facet that failed.
Nothing has been computed at that point, and `catena run config.toml --dry-run` shows the same failure.

## Converting units

Where a conversion is right for the quantity, make it a node of its own with `xra.units.convert`:

```python
@xra.enforce
def tair_celsius(
    tair: Annotated[xr.DataArray, Unit("K")],
) -> Annotated[xr.DataArray, Unit("degC")]:
    return xra.units.convert(tair, "degC")
```

`xra` is also in scope in an inline `[[node]]` expression:

```toml
[[node]]
name = "tair_celsius"
inputs = ["tair"]
expression = "xra.units.convert(tair, 'degC')"
units = "degC"
```

The flux recipe does this because its one conversion matters: `flux.nc` stores air temperature in kelvin, while `partition_fluxes` declares it in `degC` because its respiration term is a $Q_{10}$ relation written for Celsius.
Given kelvin, that term returns respiration around $10^8$ rather than $4$, and nothing downstream would look obviously wrong.
Without the declaration, a bare parameter would have used kelvin without complaint.

!!! warning "Affine units (temperature)"

    Converting between offset units such as `degC` and `K` applies the offset (`degC → K` adds 273.15), which is right for an *absolute* temperature and wrong for a *difference* or anomaly.

## Changing a unit in a calculation

A returned array must already carry its declared unit.
`attrs` take no part in arithmetic, so `p * 100.0` keeps its `hPa` label, and a ratio of two arrays labelled `mm/day` is still labelled `mm/day`.
A calculation that changes the unit states the new one:

```python
@xra.enforce
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, Unit("mm/day")],
    evapotranspiration_daily: Annotated[xr.DataArray, Unit("mm/day")],
) -> Annotated[xr.DataArray, Unit("1")]:
    ratio = precipitation_daily / evapotranspiration_daily
    return ratio.assign_attrs(units="1")
```

The values are not inspected, so that statement is taken on trust.
A missing label, or one that disagrees with the declaration, raises when the node runs.

## Turning the checks off

Every failed check raises, and there is nothing to configure.
To tolerate something, correct or remove the declaration.

To switch off all checking, including the whole-graph check, set `XARRAY_ANNOTATED_ENABLED=false`, or wrap the call in `with xarray_annotated.enabled(False):`.
The block beats the variable, and covers only the current thread or async task, so use the variable to switch off worker threads.

## Contracts across a passthrough node

Some nodes transform data while preserving most of its facets.
Resampling is the usual case: `temperature_weekly` should inherit whatever `temperature_daily` declared.
These nodes are **passthroughs**, and the checker carries the upstream contract across them, so an edge through a resample is still checked end to end.

This works per facet.
A resample preserves units but changes frequency, so a `[[resample]]` declares its own output frequency and is an ordinary typed producer for that facet.
Declare `Freq("W-SUN")` downstream and a mistyped `W-WED` offset fails when the driver is built.

Every `[[resample]]` is a passthrough, and an inline `[[node]]` can be marked as one with `passthrough = true`.

Contracts cannot catch anything that leaves units and shape unchanged, such as summing a rate you meant to average; see [Resampling and units](resampling-and-units.md).
