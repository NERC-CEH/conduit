# /// script
# requires-python = ">=3.12"
# dependencies = ["conduit[all]", "marimo"]
# ///

"""Interactive, executable walkthrough of the Conduit flux pipeline."""

import marimo

app = marimo.App(app_title="conduit: a flux-processing pipeline")


@app.cell
def _():
    import marimo as mo
    import xarray as xr
    from xarray_annotated.units import use_cf_units

    use_cf_units()
    return mo, xr


@app.cell
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
def _(mo):
    from pathlib import Path

    example_dir = Path(__file__).parent
    project_dir = example_dir.parents[1]
    config_path = example_dir / "config.toml"
    data_dir = example_dir / "data"
    results_dir = example_dir / "results"
    data_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)
    mo.md(f"Using configuration: `{config_path}`")
    return config_path, data_dir, example_dir, project_dir, results_dir


@app.cell
def _(data_dir, example_dir):
    import sys

    # make_data.py sits next to this notebook, which is not necessarily importable.
    sys.path.insert(0, str(example_dir))
    from make_data import write_inputs

    flux_path, satellite_path = write_inputs(data_dir)
    return flux_path, satellite_path


@app.cell
def _(config_path, mo):
    mo.md("""
    ## The TOML configuration

    The `[flux_nodes]` section imports the Hamilton node module. Inputs and outputs
    are ordinary conduit file sections; the function parameter names provide the
    wiring between them.
    """)
    mo.md(f"```toml\n{config_path.read_text()}\n```")
    return


@app.cell
def _(config_path, example_dir, mo, project_dir):
    import os as graph_os
    import subprocess as graph_subprocess

    graph_base = example_dir / "pipeline"
    graph_environment = {**graph_os.environ, "PYTHONPATH": str(project_dir)}
    graph_subprocess.run(
        ["conduit", "graph", str(config_path), "--output", str(graph_base), "--png"],
        check=True,
        cwd=project_dir,
        env=graph_environment,
    )
    graph_path = graph_base.with_suffix(".png")
    mo.md("## The generated DAG")
    mo.image(
        graph_path, alt="Graphviz graph of the flux-processing pipeline", width="100%"
    )
    return graph_path


@app.cell
def _(config_path, mo, project_dir):
    import os as run_os
    import subprocess as run_subprocess

    run_environment = {**run_os.environ, "PYTHONPATH": str(project_dir)}
    run_subprocess.run(
        ["conduit", "run", str(config_path), "--dry-run"],
        check=True,
        cwd=project_dir,
        env=run_environment,
    )
    run_subprocess.run(
        ["conduit", "run", str(config_path)],
        check=True,
        cwd=project_dir,
        env=run_environment,
    )
    mo.md(
        "## Run the pipeline\n\nThe dry run passed, then conduit executed the DAG and wrote the products."
    )
    return


@app.cell
def _(mo, results_dir, xr):
    products = xr.open_dataset(results_dir / "flux_products.nc")
    annual = products[["annual_nee", "annual_gpp", "annual_reco"]]
    weekly = products["gpp_weekly"]
    comparison = products[["bias", "rmse"]]
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
    return products


if __name__ == "__main__":
    app.run()
