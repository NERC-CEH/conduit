# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "conduit[all] @ git+https://github.com/NERC-CEH/conduit",
#     "marimo",
# ]
# ///

"""Executable walkthrough of the smallest complete conduit pipeline."""

import marimo

__generated_with = "0.23.14"
app = marimo.App(app_title="Pipeline 101")


@app.cell
def _():
    import subprocess

    import marimo as mo
    import xarray as xr
    from xarray_annotated.units import use_cf_units

    use_cf_units()
    return mo, subprocess, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Pipeline 101

    The smallest pipeline that still has every moving part: an input file, a
    node function imported from a Python module, a node defined inline in the
    config, and an output file.

    It derives a temperature anomaly from 90 days of daily temperature at three
    sites, then reduces the anomaly to a per-site range.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    recipe_dir = Path(__file__).parent
    project_dir = recipe_dir.parents[1]
    config_path = recipe_dir / "config.toml"
    nodes_path = recipe_dir / "nodes.py"
    data_dir = recipe_dir / "data"
    results_dir = recipe_dir / "results"
    data_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    def rel(path):
        """Path relative to the repository root, so output is machine-independent."""
        return Path(path).relative_to(project_dir)

    return (
        config_path,
        data_dir,
        nodes_path,
        project_dir,
        recipe_dir,
        rel,
        results_dir,
    )


@app.cell
def _(project_dir, subprocess):
    def conduit(*args):
        """Run the conduit CLI from the repository root, with absolute paths scrubbed.

        cwd is the repository root, which conduit appends to sys.path, so
        `_import_path = "recipes.pipeline_101.nodes"` resolves.
        """
        proc = subprocess.run(
            ["conduit", *args],
            check=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        for stream in (proc.stdout, proc.stderr):
            if stream:
                print(stream.replace(f"{project_dir}/", ""), end="")

    return (conduit,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The input

    `make_data.py` writes a deterministic NetCDF file next to this notebook. The
    `units` attribute on the variable is what lets conduit check the pipeline's
    unit contracts against the file before running anything.
    """)
    return


@app.cell
def _(data_dir, recipe_dir, rel):
    import sys

    # make_data.py sits next to this notebook, which is not necessarily importable.
    sys.path.insert(0, str(recipe_dir))
    from make_data import write_inputs

    rel(write_inputs(data_dir))
    return


@app.cell(hide_code=True)
def _(mo, nodes_path):
    mo.md(f"""
    ## The node module

    An ordinary xarray function is an ordinary DAG node. The function name is
    the node name, each parameter name is the node it consumes, and the
    annotations declare the units.

    ```python
    {nodes_path.read_text()}
    ```
    """)
    return


@app.cell(hide_code=True)
def _(config_path, mo):
    mo.md(f"""
    ## The config

    Three kinds of section, and between them they describe the whole graph.

    ```toml
    {config_path.read_text()}
    ```
    """)
    return


@app.cell
def _(conduit, config_path, recipe_dir, rel):
    graph_base = recipe_dir / "pipeline"
    conduit("graph", str(rel(config_path)), "--output", str(rel(graph_base)), "--png")
    graph_path = graph_base.with_suffix(".png")
    return (graph_path,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The graph conduit builds

    `conduit graph` renders the DAG without running it. Node labels carry the
    declared units, so a wiring mistake is often visible before a dry run
    reports it.
    """)
    return


@app.cell
def _(graph_path, mo):
    mo.image(graph_path, alt="Graphviz graph of the pipeline", width="100%")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Validate, then run

    `--dry-run` parses the config, opens the input headers, builds the DAG and
    checks every contract, without executing a node. Only then is it worth
    spending compute.
    """)
    return


@app.cell
def _(conduit, config_path, rel):
    conduit("run", str(rel(config_path)), "--dry-run")
    conduit("run", str(rel(config_path)))
    return


@app.cell
def _(results_dir, xr):
    result = xr.open_dataset(results_dir / "anomaly.nc")
    return (result,)


@app.cell(hide_code=True)
def _(mo, result):
    mo.md(f"""
    ## The output

    The written file carries the units declared on the nodes, and its attributes
    include the config that produced it, along with a SHA-256 of that text.

    - `temperature_anomaly` — {result["temperature_anomaly"].attrs.get("units")}
    - `anomaly_range` — {result["anomaly_range"].attrs.get("units")}
    """)
    return


@app.cell
def _(result):
    result
    return


if __name__ == "__main__":
    app.run()
