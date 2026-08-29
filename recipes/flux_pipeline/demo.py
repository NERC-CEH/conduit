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
app = marimo.App(app_title="Flux processing")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

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

    return config_path, data_dir, mo, nodes_path, recipe_dir, rel, results_dir


@app.cell(hide_code=True)
def _(config_path, mo, rel):
    mo.md(f"""
    # A flux-processing pipeline with conduit

    This example adapts the eddy-covariance flux workflow from the
    [xarray-annotated worked example](https://github.com/jmarshrossney/xarray-annotated/blob/main/examples/notebook.py).
    It keeps the scientific functions in a Python module and moves the pipeline
    wiring into TOML.

    The pipeline produces annual carbon totals, weekly GPP, and a comparison with
    a synthetic satellite product. Every stage is checked before it runs.

    Everything below drives the library directly, so nothing here needs the
    `conduit` command installed. Configuration: `{rel(config_path)}`.
    """)
    return


@app.cell
def _(data_dir, recipe_dir, rel):
    from conduit.importing import import_user_module

    # make_data.py sits next to this notebook. This is the same loader conduit uses
    # for an `_import_path` naming a .py file, so nothing goes on sys.path.
    make_data = import_user_module(str(recipe_dir / "make_data.py"))

    [rel(written) for written in make_data.write_inputs(data_dir)]
    return


@app.cell(hide_code=True)
def _(config_path, mo):
    mo.md(f"""
    ## The TOML configuration

    The `[flux_nodes]` section imports the Hamilton node module. Inputs and outputs
    are ordinary conduit file sections; the function parameter names provide the
    wiring between them.

    ```toml
    {config_path.read_text()}
    ```
    """)
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


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The generated DAG

    `conduit.build_graph` returns a `graphviz.Digraph` without running anything, so
    it renders inline. Node labels carry the declared units, which makes a wiring
    mistake visible before a dry run reports it.
    """)
    return


@app.cell
def _(config_path, mo):
    import conduit

    graph = conduit.build_graph(config_path)
    mo.Html(graph.pipe(format="svg").decode())
    return (conduit,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Validate before running

    `conduit.dry_run` parses the config, opens the input headers, builds the DAG and
    checks every contract, without executing a node. It returns a `DryRunReport`,
    one `Stage` per thing it checked.
    """)
    return


@app.cell
def _(conduit, config_path, mo):
    dry = conduit.dry_run(config_path)

    mo.md(
        "| Stage | Status | Detail |\n|---|---|---|\n"
        + "\n".join(
            f"| `{stage.name}` | {stage.status} | {stage.detail} |"
            for stage in dry.stages
        )
    )
    return (dry,)


@app.cell(hide_code=True)
def _(dry, mo):
    findings = [
        f"- **{stage.name}** — {finding}"
        for stage in dry.stages
        for finding in stage.findings
    ]
    mo.md(
        "conduit reports the unit conversion this pipeline relies on, because "
        '`on_inexact = "warn"` in the config asks it to:\n\n' + "\n".join(findings)
        if findings
        else "No findings."
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Run the pipeline

    `conduit.run` takes the same config and returns a `RunReport`: the datasets it
    produced, and one `WrittenOutput` per destination. The conversion reported above
    happens here, so it is silenced rather than repeated.
    """)
    return


@app.cell
def _(conduit, config_path, mo, rel):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run = conduit.run(config_path)

    mo.md(
        f"Completed in {run.elapsed:.2f}s.\n\n"
        "| Written | Variables | Size |\n|---|---|---:|\n"
        + "\n".join(
            f"| `{rel(out.path)}` | {len(out.variables)} | {out.size_bytes / 1000:.1f} kB |"
            for out in run.written
        )
    )
    return (run,)


@app.cell
def _(run):
    products = run.outputs["products"]
    annual = products[["annual_nee", "annual_gpp", "annual_reco"]]
    weekly = products["gpp_weekly"]
    comparison = products[["bias", "rmse"]]
    return annual, comparison, weekly


@app.cell(hide_code=True)
def _(annual, comparison, mo, weekly):
    mo.md(f"""
    ## Results

    These come straight from the `RunReport`, not from re-opening the file.

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
