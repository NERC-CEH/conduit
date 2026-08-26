---
title: Contracts and the whole-graph check
icon: lucide/badge-check
---

# Contracts and the whole-graph check

A contract is a claim a node makes about the data on one of its edges, written as an ordinary type annotation:

```python
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, "mm/day"],
    evapotranspiration_daily: Annotated[xr.DataArray, "mm/day"],
) -> Annotated[xr.DataArray, "1"]: ...
```

[xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) already checks a claim like that against the arguments the function is actually handed, at the moment it is called.
That is a per-function guarantee, and it arrives too late to be much comfort: by the time the mismatched array reaches the function, everything upstream of it has already run.

Checking every edge *before* the graph runs needs the annotations and the graph together.
conduit has both, and lifting the per-function check to a DAG-wide one is the part it adds.

## What a contract can say

Five facets, each declared independently:

| Facet | Declares |
|---|---|
| units | the physical unit, via pint and cf-xarray |
| dims | the dimension names |
| coords | required coordinate variables |
| dtype | the array's element type |
| freq | how often the time axis ticks, and on what phase |

[Declaring contracts](../guides/nodes/contracts.md) is the vocabulary and the syntax.
This page is about what the checks do with it.

## Producers, consumers, and passthroughs

An annotation on a node's return value makes it a **typed producer**: conduit knows that node's output unit statically, without running it.
An annotation on a parameter declares what the node **requires** of its input.
An edge is checked wherever both ends declare a contract for the same facet.

Some nodes transform data while leaving most facets alone.
Resampling is the usual case: a weekly mean of a daily temperature is still degrees Celsius.
These nodes are tagged **passthrough**, and the checker carries the upstream contract across them, so an edge running through a resample is still covered end to end.

That happens per facet, because a passthrough preserves some and changes others.
A resample preserves units and dims.
It does not preserve frequency, since frequency is exactly what it changes, so it declares its own output frequency and becomes an ordinary typed producer for that one facet.
Declare `Freq("W-SUN")` downstream and a `W-WED` offset fails when the driver is built.

## The layers, and when each runs

The contract check is one of several.
They ask different questions and fire at different moments:

| Layer | Question | When |
|---|---|---|
| Config parse | Is the TOML a valid pipeline, with parseable units, dtypes and node names? | parse |
| Input compatibility | Do the input *files* relate as you said, on grid, time axis or coordinates? | after inputs open |
| Contract check | Does every internal edge with a contract at both ends agree? | when the driver is built |
| Execution plan | Is every requested output reachable from the inputs? | driver build |
| Wiring check | Is every required input bound, and is anything loaded going unused? | after inputs load |
| Input contracts | Does each file's metadata match what its consuming node requires? | node call |

Everything above the last row happens before a single array is computed.
Input contracts are the exception, because they compare against real file metadata rather than declarations, so a normal run defers them to the moment the consuming node is called.

`conduit run --dry-run` brings that forward: it performs every layer, including the input contracts, and executes nothing.
[Validate before running](../guides/validate/validate-before-running.md) is the guide.

Input compatibility is the only layer that is opt-in.
Different time axes across inputs are perfectly normal, so conduit does not guess which relationships must hold; you declare them in a `[validation]` block.

## Strictness is a policy, not a property

The `[annotations]` section sets one policy for the whole pipeline.
`mode` decides whether a contract problem raises, is reported, or is ignored.
`on_inexact` governs implicit conversion, and only a value-changing conversion consults it: hectopascals into a node wanting pascals can be scaled silently, reported, or refused.
Units that differ only in spelling are relabelled without touching the values, and dimensionally incompatible units are always an error regardless of policy.

## What contracts cannot catch

The check shows the pipeline is *consistent*.
It says nothing about whether it is *correct*.

A contract constrains the shape and units of data on an edge, so anything that leaves both unchanged passes.
Summing a rate where you meant to average it gives the same units and the same dimensions, and no check will save you.
[Resampling and units](../guides/nodes/resampling-and-units.md) is about that specific trap.
A sign error, a wrong coefficient, or the right calculation on the wrong variable are all invisible here too.

Contracts narrow the space of mistakes.
They do not empty it.
[Test your pipeline](../guides/validate/test-your-pipeline.md) covers the rest.

## Where next

- [Declaring contracts](../guides/nodes/contracts.md) — writing the annotations.
- [Validate before running](../guides/validate/validate-before-running.md) — the `--dry-run` pre-flight.
- [`[annotations]` reference](../reference/configuration.md#annotations) — every policy key.
