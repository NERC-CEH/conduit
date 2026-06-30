---
title: Home
icon: lucide/house
---

# breadboard

**An opinionated [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) +
[xarray](https://xarray.dev) + [pint](https://pint.readthedocs.io) foundation for
building configurable, unit-aware data pipelines and forward models in geoscience and
environmental science.**

breadboard lets you describe a computational pipeline — a Directed Acyclic Graph (DAG)
of operations over labelled N-D arrays — in a plain [TOML](https://toml.io) file. You
declare **what** you want computed; the DAG engine works out **how** and in what order.

It is domain-agnostic: forward models, land-cover classification, and analysis pipelines
are all expressed the same way. The value is in the *integration* of these tools, so
breadboard deliberately **exposes** Hamilton drivers and xarray objects rather than
hiding them behind wrappers.

## Installation

See the [Installation guide](getting_started/installation.md).

## Quick start

Get a pipeline running in a few minutes — see the [Quickstart](getting_started/quickstart.md).

## Key features

- **Config-as-DAG** — compose a pipeline from a TOML file, including nodes defined inline
  or imported from your own modules (`_import_path`).
- **Unit validation** — declare units on nodes; breadboard converts compatible inputs,
  rejects incompatible ones, and checks consistency across the DAG *before* running
  (powered by pint / cf-xarray).
- **Dimension-agnostic I/O** — works with whatever dimensions your data has; optional
  temporal-resampling and geospatial (CRS) helpers when you want them.
- **Scales out** — content-addressed result caching, memory-bounded blocked execution,
  and parallel subset runs over Zarr, via Hamilton and dask.
- **CLI and Python API** — run from the terminal (`breadboard run`) or embed in a notebook.

## Learn more

- [Quickstart](getting_started/quickstart.md) — run your first pipeline
- [Concepts](getting_started/concepts.md) — how the DAG and config fit together
- [Configuration](usage/config.md) — TOML config reference
- [Custom modules](usage/custom-modules.md) — bring your own nodes
- [Examples](examples/getting_started.md) — annotated, runnable notebooks

## Acknowledgements

breadboard builds on the following open-source projects:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — DAG-based dataflow framework
- [xarray](https://docs.xarray.dev/) — N-D labelled arrays and datasets
- [pint](https://pint.readthedocs.io) & [cf-xarray](https://cf-xarray.readthedocs.io) — units
- [dask](https://www.dask.org/) — parallel and out-of-core computation
- [Typer](https://typer.tiangolo.com/) — CLI framework
