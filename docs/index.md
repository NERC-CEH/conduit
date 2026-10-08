---
title: Home
icon: lucide/house
---

# Conduit

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev) for building configurable environmental data pipelines.

1. **Write the science code.** Ordinary Python functions that take and return `xarray.DataArray`s, with optional [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) declaring what each one requires and produces: units, dimensions, coordinates, dtype, temporal frequency.
2. **Write the config.** A TOML file names the input files, the nodes and the outputs. Assembling or adapting a pipeline from here needs no Python.
3. **Validate.** Conduit assembles the whole graph before computing anything and checks every declared edge against the claim at the other end, via [`xarray-annotated`](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/). A unit mismatch fails at the terminal in a second rather than forty minutes into a run.
4. **Run.** In memory, out-of-core with dask, memory-bounded in blocks, or sharded across processes. The choice lives in the config, and none of it changes the science code.

!!! warning "Alpha status"

    `conduit` is an early-stage project under active development. Things will change without warning.


## A very simple demo

[Pipeline 101](recipes/pipeline-101.md) derives a temperature anomaly from 90 days of daily temperature at three sites, then reduces it to a per-site range.
It has one input file, one node function in a Python module, one node declared inline in the config, and one output file.

<!-- The input file comes from `recipes/pipeline_101/make_data.py`. -->

```bash exec="true"
python recipes/pipeline_101/make_data.py > /dev/null
```

=== "Python module"

    The science code: ordinary functions of `xarray.DataArray`s, annotated with the units they expect and return.

    <!-- fmt:off -->
    ```python
    --8<-- "recipes/pipeline_101/nodes.py"
    ```
    <!-- fmt:on -->

=== "TOML config"

    The config names the input file, the module, an inline node and the output.
    From Python, the same structure can be passed as a dict.

    ```toml
    --8<-- "recipes/pipeline_101/config.toml"
    ```

=== "Graph visualisation"

    Node labels carry the declared units and requested outputs are highlighted, so a wiring mistake is often visible before anything runs.

    ```bash exec="true" source="block" result="text"
    conduit graph recipes/pipeline_101/config.toml --png \
      --output recipes/pipeline_101/pipeline
    ```

    ```bash exec="true"
    python - <<'EOF'
    import base64
    from pathlib import Path

    png = base64.b64encode(Path("recipes/pipeline_101/pipeline.png").read_bytes()).decode()
    print(f'<img src="data:image/png;base64,{png}" alt="The Pipeline 101 DAG" style="max-width:100%">')
    EOF
    ```

=== "Dry-run"

    `--dry-run` parses the config, opens the input headers, builds the DAG and checks every contract, without loading any data.

    ```bash exec="true" source="block" result="text"
    conduit run --dry-run recipes/pipeline_101/config.toml
    ```

=== "Run"

    ```bash exec="true" source="block" result="text"
    conduit run recipes/pipeline_101/config.toml
    ```

The [Pipeline 101 notebook](recipes/pipeline-101.md) runs the same pipeline through the Python API.

## Navigating these docs

<div class="grid cards" markdown>

- **[Concepts](concepts/overview.md)** — how conduit works, and why.
- **[Guides](guides/install.md)** — how to do things. After [installing](guides/install.md), start at [Write a config](guides/configs/write-a-config.md) to adapt a pipeline, or [Bring your own module](guides/nodes/bring-your-own-module.md) to add nodes.
- **[Recipes](recipes/index.md)** — complete pipelines as executable [marimo](https://marimo.io) notebooks.
- **[Extending](extending/index.md)** — building a package on top of conduit.
- **[Reference](reference/configuration.md)** — every config key, file format, CLI flag and Python name.

</div>

## See also

**Upstream**

Conduit offloads most of the hard work to several excellent libraries:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — the DAG engine.
- [xarray](https://docs.xarray.dev/) — labelled N-D arrays.
- [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) — per-function unit, dim, dtype, coord and frequency contracts using `typing.Annotated`.
- [pint](https://pint.readthedocs.io), [pint-xarray](https://pint-xarray.readthedocs.io/en/stable/), and [cf-xarray](https://cf-xarray.readthedocs.io) — units validation machinery.
- [dask](https://www.dask.org/) — parallel and out-of-core computation.
- [Typer](https://typer.tiangolo.com/) — the CLI.

**Downstream** 

The following projects are using Conduit:

- [SatTerC](https://satterc.github.io/satterc/) — terrestrial carbon modelling.

## Acknowledgements

This work has been supported by:

- NC-International
