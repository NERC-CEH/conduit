# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "conduit[all] @ git+https://github.com/NERC-CEH/conduit",
#     "marimo",
# ]
# ///

"""Interactive, executable walkthrough of the Conduit flux pipeline."""

import marimo

__generated_with = "0.23.14"
app = marimo.App(app_title="conduit: a flux-processing pipeline")


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
    # A flux-processing pipeline with conduit

    This example adapts the eddy-covariance flux workflow from the
    [xarray-annotated worked example](https://github.com/jmarshrossney/xarray-annotated/blob/main/examples/notebook.py).
    It keeps the scientific functions in a Python module and moves the pipeline
    wiring into TOML.

    The pipeline produces annual carbon totals, weekly GPP, and a comparison with
    a synthetic satellite product. Every stage is checked before it runs.
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
        `_import_path = "recipes.flux_pipeline.nodes"` resolves.
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
def _(config_path, mo, rel):
    mo.md(f"Using configuration: `{rel(config_path)}`")
    return


@app.cell
def _(data_dir, recipe_dir, rel):
    import sys

    # make_data.py sits next to this notebook, which is not necessarily importable.
    sys.path.insert(0, str(recipe_dir))
    from make_data import write_inputs

    [rel(written) for written in write_inputs(data_dir)]
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The TOML configuration

    The `[flux_nodes]` section imports the Hamilton node module. Inputs and outputs
    are ordinary conduit file sections; the function parameter names provide the
    wiring between them.
    """)
    return


@app.cell(hide_code=True)
def _(config_path, mo):
    mo.md(f"```toml\n{config_path.read_text()}\n```")
    return


@app.cell(hide_code=True)
def _(mo, nodes_path):
    mo.md(f"""
    ## The Python module

    The pipeline nodes are ordinary annotated Python functions. Their annotations
    describe the units and frequencies that conduit checks across the DAG.

    ```python
    {nodes_path.read_text()}
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
    ## The generated DAG
    """)
    return


@app.cell
def _(graph_path, mo):
    mo.image(
        graph_path, alt="Graphviz graph of the flux-processing pipeline", width="100%"
    )
    return


@app.cell
def _(conduit, config_path, rel):
    conduit("run", str(rel(config_path)), "--dry-run")
    conduit("run", str(rel(config_path)))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Run the pipeline

    The dry run passed, then conduit executed the DAG and wrote the products.
    """)
    return


@app.cell
def _(results_dir, xr):
    products = xr.open_dataset(results_dir / "flux_products.nc")
    annual = products[["annual_nee", "annual_gpp", "annual_reco"]]
    weekly = products["gpp_weekly"]
    comparison = products[["bias", "rmse"]]
    return annual, comparison, weekly


@app.cell(hide_code=True)
def _(annual, comparison, mo, weekly):
    mo.md(f"""
    ## Results

    | Product | Value |
    |---|---:|
    | Annual NEE | **{float(annual.annual_nee):+.0f}** g C m^-2 yr^-1 |
    | Annual GPP | **{float(annual.annual_gpp):+.0f}** g C m^-2 yr^-1 |
    | Annual RECO | **{float(annual.annual_reco):+.0f}** g C m^-2 yr^-1 |
    | Weekly GPP | {weekly.sizes["time"]} weeks, mean **{float(weekly.mean()):.2f}** g C m^-2 d^-1 |
    | Satellite bias | **{float(comparison.bias):+.2f}** g C m^-2 d^-1 |
    | Satellite RMSE | **{float(comparison.rmse):.2f}** g C m^-2 d^-1 |
    """)
    return


if __name__ == "__main__":
    app.run()
