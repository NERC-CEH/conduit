---
title: Contracts before compute
icon: lucide/shield-check
---

# Contracts before compute

conduit's flagship feature is lifting per-function contract validation to a **whole-DAG,
before-compute guarantee**. This page explains what that means, why it is possible, and
how far it reaches. For a hands-on walkthrough, see
[Add unit contracts](../get-started/units-and-contracts.md); for the task-level
mechanics, [Validate before running](../guides/validate-before-running.md).

## What is a contract?

A *contract* is a machine-checkable claim a node makes about the data on one of its
edges — declared in ordinary type annotations:

```python
def aridity_index_daily(
    precipitation_daily: Annotated[xr.DataArray, "mm/day"],
    evapotranspiration_daily: Annotated[xr.DataArray, "mm/day"],
) -> Annotated[xr.DataArray, "1"]:
    ...
```

conduit understands four **facets** of a contract, all through the same machinery:

- **units** (via `pint` / `cf-xarray`) — `"mm/day"`, `"Pa"`, `"1"` (dimensionless),
- **dims** — the dimension names,
- **coords** — required coordinate variables,
- **dtype** — the array's element type.

The `[[node]]` config form declares the same facets with `units`/`dims`/`coords`/`dtype`
keys (see [Configuration › nodes](../reference/configuration.md#nodes)).

## The leap: per-function → whole-graph

Libraries like `xarray-annotated` already validate a single function's contract when it
runs. conduit's contribution is to check the **whole graph, before any node executes**.

At build time it walks every internal edge. Where the producer declares an output
contract *and* the consumer declares an input contract, it proves the two are
consistent — for units, that they are convertible (and, under `exact`, identical); for
dims/coords/dtype, that they match. If they don't, the build fails with a message naming
both nodes and the offending facet. No data has moved yet.

This is only possible because **both the annotations and the graph are present at the
same time**. The annotations supply the per-edge claims; the graph supplies the edges to
check. Take away either — annotations without a graph, or a graph without annotations —
and a before-compute proof is not available. That composition is conduit's reason to
exist (see [Why conduit?](why-conduit.md)).

## What each check covers

- **Internal edges** (`check_dag_contracts`) — every edge where both ends declare a
  contract is proven at build time.
- **Input edges** (`check_input_contracts`) — an input from a file has no producer
  *function* to declare a contract, so its actual metadata is validated against its
  consumers instead. This needs the real files, but still no compute — it is what
  [`--dry-run`](../guides/validate-before-running.md) does.
- **Wiring** (`check_wiring`) — a separate check that the *plumbing* is complete
  (every required input is bound; unused inputs warn), independent of the facets.

## Passthrough nodes propagate contracts

Some nodes neither produce nor consume a *fixed* contract — they transform data while
preserving its facets. Resampling is the canonical case: `temperature_weekly` should
inherit whatever contract `temperature_daily` declared. Such nodes are tagged
**passthrough**, and the checker propagates the upstream contract across them
generically — so an edge fed through a resample is still covered end to end. The
`[[resample]]` preset produces passthrough nodes; you can mark your own inline
`[[node]]` passthrough too.

## Conversion, not just rejection

Contracts do more than reject. For units, a *compatible-but-different* input is
**converted** to what the consumer declares — feed `hPa` where `Pa` is wanted and
conduit scales it, rather than failing. You choose the strictness with the
[`[annotations]` policy](../reference/configuration.md#annotations): `warn` (default) vs
`strict`, and `exact` to forbid value-changing conversions.

## Why this matters

The mistakes contracts catch — a unit slip, a transposed axis, a renamed input — are
exactly the ones that otherwise survive until deep into a long run, or worse, produce a
plausible-looking wrong answer. Proving them away up front (and in CI, via `--dry-run`)
turns a class of silent, expensive errors into a fast failure at build time.

## See also

- [Add unit contracts](../get-started/units-and-contracts.md) — a runnable tutorial.
- [Validate before running](../guides/validate-before-running.md) — the `--dry-run`
  workflow.
- [`[annotations]` reference](../reference/configuration.md#annotations) — every policy
  key.
