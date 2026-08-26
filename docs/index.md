---
title: Home
icon: lucide/house
---

# Conduit

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev), serves as a highly flexible and robust substrate for environmental data science applications.

The process for building on top of Conduit is simple:

1. You write ordinary Python functions that receive and return `xarray.DataArray`s, and optionally add [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) that declare the expected properties of these arrays (coordinates, physical units etc).
2. Users can then use these functions to define data pipelines, by simply writing/editing TOML configuration files.
3. Conduit builds the graph (via Hamilton), checks the annotation contracts _before_ execution (via [`xarray-annotated`](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/)), and finally runs the pipeline with one of several swappable backend execution models (serial, multiprocessing, dask, jax.vmap...).

!!! warning "Alpha status"

    `conduit` is an early-stage project under active development. Things will change without warning.


## A small pipeline

=== "Python"

    ```python
    --8<-- "recipes/pipeline_101/nodes.py"
    ```

=== "TOML"

    ```toml
    --8<-- "recipes/pipeline_101/config.toml"
    ```

=== "Graph"

    ```mermaid
    graph LR
        I["temperature_climate<br/><small>degC</small>"] --> A["temperature_anomaly_climate<br/><small>degC</small>"]
        A --> R["anomaly_range_climate<br/><small>degC</small>"]
        R --> O[("results/anomaly.nc")]
        A --> O
    ```

That is [Pipeline 101](recipes/pipeline-101.md), which runs end to end.

## Getting started

- [How it works](how-it-works.md) — the design, and what the checks can and cannot catch.
- [Install](guides/install.md) — get it running.
- [Pipeline 101](recipes/pipeline-101.md) — the whole workflow in miniature.
- [Bring your own module](guides/authoring/bring-your-own-module.md) — the conventions your science code must follow. Start here if you are adding your own nodes.
- [Configuration reference](reference/configuration.md) — every TOML section and key.

## See also

Conduit offloads most of the hard work to several excellent libraries:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — the DAG engine
- [xarray](https://docs.xarray.dev/) — labelled N-D arrays
- [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) — per-function unit, dim, dtype, coord and frequency contracts using `typing.Annotated`
- [pint](https://pint.readthedocs.io) and [cf-xarray](https://cf-xarray.readthedocs.io) — units validation machinery
- [dask](https://www.dask.org/) — parallel and out-of-core computation
- [Typer](https://typer.tiangolo.com/) — the CLI

The following projects are using Conduit:

- [SatTerC](https://satterc.github.io/satterc/) — terrestrial carbon modelling

## Acknowledgements

This work has been supported by:

- NC-International
