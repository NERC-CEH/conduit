---
title: Flux processing with conduit
icon: lucide/workflow
---

# Flux processing with conduit

This recipe turns the eddy-covariance flux workflow from the
[xarray-annotated worked example](https://github.com/jmarshrossney/xarray-annotated/blob/main/examples/notebook.py)
into a conduit pipeline. It demonstrates the separation between:

- `nodes.py`: ordinary, annotated Hamilton node functions;
- `config.toml`: the pipeline wiring, inputs, and outputs;
- `demo.py`: an executable marimo walkthrough that generates data, visualises the
  DAG, runs it, and inspects the products.

The example files live in
[`examples/flux_pipeline`](https://github.com/NERC-CEH/conduit/tree/main/examples/flux_pipeline).
Run the notebook from the repository root with:

```sh
uv run marimo run examples/flux_pipeline/demo.py
```

The notebook also works as a batch documentation example. It generates the Graphviz
image using `conduit graph`, validates the pipeline with `conduit run --dry-run`, and
then executes it with `conduit run`.

!!! note "Requirements"

    Install the documentation dependencies with `uv sync --group docs`. Graph generation
    also requires the Graphviz system executable; see the
    [installation guide](../get-started/install.md).

## Pipeline configuration

The TOML imports the Python module as a user module. Input and output paths are
resolved relative to this file, as with every conduit configuration.

```toml
--8<-- "examples/flux_pipeline/config.toml"
```

The complete file is available at
[`config.toml`](https://github.com/NERC-CEH/conduit/blob/main/examples/flux_pipeline/config.toml).

## Python module

`examples.flux_pipeline.nodes` is an ordinary importable Python module. The
`[flux_nodes]` section in the TOML imports it with `_import_path`, and Hamilton
discovers the public functions below as pipeline nodes. Their annotations provide the
contracts used by the whole-DAG check.

The complete module is included below so that the implementation and its annotations
can be read together:

```python
--8<-- "examples/flux_pipeline/nodes.py"
```

## What the notebook demonstrates

The executable notebook follows this sequence:

1. Generate deterministic half-hourly flux and satellite NetCDF inputs.
2. Display the TOML configuration.
3. Generate the DAG with `conduit graph` and display its Graphviz output.
4. Run `conduit run --dry-run` to check wiring, contracts, and output paths.
5. Run the pipeline and display annual totals, weekly GPP, bias, and RMSE.

The functions remain independent of marimo and can be reused from another config or
driven directly through conduit's Python API.

The [exported notebook](flux-pipeline-demo.md) contains the same walkthrough with its
rendered Graphviz graph and pipeline results.
