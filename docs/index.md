---
title: Home
icon: lucide/house
---

# conduit

**Turn a working research script into a unit-safe, reproducible, scalable pipeline —
without a rewrite.**

You keep writing plain, typed [xarray](https://xarray.dev) functions. conduit adds
two things that are hard to get any other way:

- **Static dimensional checking across the whole pipeline.** Units are validated *before
  any compute runs*: the entire DAG is proven dimensionally consistent from your type
  annotations, so a hPa-vs-Pa mistake is caught at build time, not part-way through a run.
  Runtime unit conversion and validation come along for free.
- **Scale-up as a config knob, not a rewrite.** The *same* functions run in-memory,
  out-of-core ([dask](https://www.dask.org/)), or across parallel processes writing to a
  shared Zarr store — driven by config, not by rewriting your code.

Under the hood conduit composes [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton)
(the DAG engine), xarray (labelled N-D arrays), and [pint](https://pint.readthedocs.io) /
[cf-xarray](https://cf-xarray.readthedocs.io) (units). The value is not the parts but where
they *compose*: unit-checking is only possible over a whole graph, and scale is only free
when the graph is separate from the functions. The aim is to let you get that value
**without** having to learn Hamilton or pint — you write ordinary annotated functions and
describe how they wire together. When you *do* want the underlying machinery, conduit
exposes the Hamilton driver and xarray objects rather than hiding them.

It is domain-agnostic: forward models, land-cover classification, and analysis pipelines
are all expressed the same way — nothing carbon- or grid-specific is baked in.

## Installation

See the [Installation guide](getting_started/installation.md).

## Quick start

Get a pipeline running in a few minutes — see the [Quickstart](getting_started/quickstart.md).

## Key features

- **Whole-pipeline unit validation** — declare units on nodes with a simple
  `Annotated[DataArray, "<unit>"]` convention; conduit converts compatible inputs,
  rejects incompatible ones, and checks the *entire DAG* for dimensional consistency
  **before** any compute runs (powered by pint / cf-xarray). This is the flagship feature.
- **Scale without a rewrite** — the same functions run in-memory, out-of-core (dask), with
  content-addressed result caching, memory-bounded blocked execution, or parallel subset
  runs over a shared Zarr store — all driven by config, not code changes.
- **Dimension-agnostic I/O** — works with whatever dimensions your data has; optional
  temporal-resampling and geospatial (CRS) helpers when you want them.
- **Config-as-DAG** — describe how your functions wire together in a plain
  [TOML](https://toml.io) file: import your own modules (`_import_path`) or define small
  glue nodes inline (`[[node]]`), which makes swapping between not-quite-interchangeable
  implementations a config edit. The config doubles as a reproducible, parameterizable
  record of the run.
- **CLI and Python API** — run from the terminal (`conduit run`) or embed in a notebook.

## Learn more

- [Quickstart](getting_started/quickstart.md) — run your first pipeline
- [Concepts](getting_started/concepts.md) — how the DAG and config fit together
- [Configuration](usage/config.md) — TOML config reference
- [Custom modules](usage/custom-modules.md) — bring your own nodes
- [Examples](examples/getting_started.md) — annotated, runnable notebooks

## Acknowledgements

conduit builds on the following open-source projects:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — DAG-based dataflow framework
- [xarray](https://docs.xarray.dev/) — N-D labelled arrays and datasets
- [pint](https://pint.readthedocs.io) & [cf-xarray](https://cf-xarray.readthedocs.io) — units
- [dask](https://www.dask.org/) — parallel and out-of-core computation
- [Typer](https://typer.tiangolo.com/) — CLI framework
