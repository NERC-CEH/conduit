---
title: Contracts and the whole-graph check
icon: lucide/badge-check
---

# Contracts and the whole-graph check

A contract is a claim a node makes about the data on one of its edges — its units, dims, coords, dtype or time frequency — written as an ordinary type annotation:

```python
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, "mm/day"],
    evapotranspiration_daily: Annotated[xr.DataArray, "mm/day"],
) -> Annotated[xr.DataArray, "1"]: ...
```

[xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) checks a claim like this against the arguments a function receives, when it is called.
That guarantee arrives late: by the time a mismatched array reaches the function, everything upstream of it has already run.

Checking every edge *before* the graph runs needs the annotations and the graph together.
conduit has both, and lifting the per-function check to a DAG-wide one is what it adds.
[Declaring contracts](../guides/nodes/contracts.md) covers the syntax; this page is about what the checks do with it.

## How edges are checked

An annotation on a node's return value makes it a **typed producer**, whose output contract conduit knows without running it.
An annotation on a parameter declares what the node **requires**.
An edge is checked wherever both ends declare the same facet.

Nodes that change some facets and keep others, such as a resample, are **passthroughs**: the checker carries the upstream contract across them facet by facet, so an edge through a resample is still covered end to end.

## The layers, and when each runs

The contract check is one of several checks, each asking a different question at a different moment:

| Layer | Question | When |
|---|---|---|
| Config parse | Is the TOML a valid pipeline, with parseable units, dtypes and node names? | parse |
| Input compatibility | Do the input *files* relate as you said, on grid, time axis or coordinates? | after inputs open |
| Contract check | Does every internal edge with a contract at both ends agree? | driver build |
| Execution plan | Is every requested output reachable from the inputs? | driver build |
| Wiring check | Is every required input bound, and is anything loaded going unused? | after inputs load |
| Input contracts | Does each file's metadata match what its consuming node requires? | node call |

All but the last happen before any array is computed.
Input contracts compare against real file metadata rather than declarations, so a normal run defers them until the consuming node is called.
`conduit run --dry-run` runs every layer, input contracts included, and executes nothing.

Input compatibility is the only opt-in layer.
Different time axes across inputs are normal, so conduit does not guess which relationships must hold; you declare them in a `[validation]` block.

## Strictness is a policy

The `[annotations]` section sets one policy for the whole pipeline.
`mode` decides whether a contract problem raises, is reported, or is ignored.
`on_inexact` decides what happens to a value-changing conversion, such as hectopascals into a node wanting pascals: scale silently, report, or refuse.
Units that differ only in spelling are relabelled without touching the values, and incompatible units are always an error.

## What contracts cannot catch

The check shows the pipeline is *consistent*, not that it is *correct*.

Anything that leaves units and shape unchanged passes.
Summing a rate where you meant to average it gives the same units and the same dims ([Resampling and units](../guides/nodes/resampling-and-units.md) covers this trap).
A sign error, a wrong coefficient, or the right calculation on the wrong variable are invisible too.
[Test your pipeline](../guides/validate/test-your-pipeline.md) covers the rest.
