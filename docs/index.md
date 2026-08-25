---
title: Home
icon: lucide/house
---

# conduit

conduit is an opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton), [xarray](https://xarray.dev) and [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), driven by a plain [TOML](https://toml.io) file.
You write ordinary annotated xarray functions and describe in config how they wire together.
conduit builds the graph, checks it for consistency, and runs it at whatever scale the config asks for.

The idea is to keep the graph separate from the functions, and let the functions carry their own contracts in their type annotations.
What that buys you:

- **The whole graph is checked before any compute runs.** Units, dimensions, coordinates, dtypes, frequency and the wiring all come from the annotations. A hPa-for-Pa slip or a renamed input fails in seconds, not forty minutes into a run.
- **The config is the pipeline.** One file describes the inputs, the nodes, the fan-out and the outputs, and it is stamped into every result, so an output file records how it was made.
- **Scaling up means editing config, not code.** The same functions run in memory, cached, blocked, or across parallel processes writing to one Zarr store.
- **The wiring is written down.** Reading the config tells you what depends on what, without tracing a script.

conduit is alpha, and a work in progress.
It does what is described here, but the config schema and the APIs still change without warning.

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

## Where to go

- [How it works](how-it-works.md) — the design, and what the checks can and cannot catch.
- [Install](guides/install.md) — get it running.
- [Pipeline 101](recipes/pipeline-101.md) — the whole workflow in miniature.
- [Bring your own module](guides/authoring/bring-your-own-module.md) — the conventions your science code must follow. Start here if you are adding your own nodes.
- [Configuration reference](reference/configuration.md) — every TOML section and key.

## Contributing

Development setup, conventions and how to add a recipe are in [`CONTRIBUTING.md`](https://github.com/NERC-CEH/conduit/blob/main/CONTRIBUTING.md).

## Acknowledgements

conduit builds on:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — the DAG engine
- [xarray](https://docs.xarray.dev/) — labelled N-D arrays
- [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) — per-function unit, dim, dtype, coord and frequency contracts
- [pint](https://pint.readthedocs.io) and [cf-xarray](https://cf-xarray.readthedocs.io) — units
- [dask](https://www.dask.org/) — parallel and out-of-core computation
- [Typer](https://typer.tiangolo.com/) — the CLI
