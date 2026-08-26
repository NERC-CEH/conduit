---
title: Home
icon: lucide/house
---

# Conduit

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev) for building configurable environmental data pipelines.

Working with Conduit falls into four stages:

1. **Write the science code.** Ordinary Python functions that take and return `xarray.DataArray`s, with optional [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) declaring what each one requires and produces: units, dimensions, coordinates, dtype, temporal frequency.
2. **Write the config.** A TOML file names the input files, the nodes and the outputs. Assembling or adapting a pipeline from here needs no Python.
3. **Validate.** Conduit assembles the whole graph before computing anything and checks every declared edge against the claim at the other end, via [`xarray-annotated`](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/). A unit mismatch fails at the terminal in a second rather than forty minutes into a run.
4. **Run.** In memory, out-of-core with dask, memory-bounded in blocks, or sharded across processes. The choice lives in the config, and none of it changes the science code.

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

- [Install](guides/install.md) — get it running.
- [Pipeline 101](recipes/pipeline-101.md) — all four stages in miniature.
- [Overview](concepts/overview.md) — the design, and what the checks can and cannot catch.
- [Write a config](guides/configs/write-a-config.md) — start here if you are adapting a pipeline someone else wrote.
- [Bring your own module](guides/nodes/bring-your-own-module.md) — start here if you are adding your own nodes.
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
