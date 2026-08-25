---
title: Home
icon: lucide/house
---

# conduit

conduit is an opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton), [xarray](https://xarray.dev) and [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), driven by a plain [TOML](https://toml.io) file.
You write ordinary annotated xarray functions.
You describe how they wire together in config.
conduit builds the graph, proves it consistent before running it, and executes it at whatever scale the config asks for.

The premise is that the graph lives apart from the functions, and the functions carry their own contracts in their type annotations.
Everything below follows from that.

- **Validate the whole graph before any compute runs.** Units, dimensions, coordinates, dtypes, frequency and the wiring itself are all checked from the annotations. A hPa-for-Pa slip or a renamed input fails in seconds, not forty minutes into a run.
- **The config is the pipeline.** One file describes the inputs, the nodes, the fan-out and the outputs, and it is stamped into every result, so an output file records how it was made.
- **Scale by changing config, not code.** The same functions run in memory, cached, blocked, or across parallel processes writing to one Zarr store.
- **The wiring is declared, not implied.** Reading the config tells you what depends on what, without tracing a script.

## The same pipeline, three ways

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

This is [Pipeline 101](recipes/pipeline-101.md), run end to end.

## Where to go

- [How it works](how-it-works.md) — the design, and what the check can and cannot catch.
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
