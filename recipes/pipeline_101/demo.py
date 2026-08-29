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
def _(mo):
    mo.md("""
    # Pipeline 101

    The smallest pipeline that still has every moving part: an input file, a
    node function imported from a Python module, a node defined inline in the
    config, and an output file.

    It derives a temperature anomaly from 90 days of daily temperature at three
    sites, then reduces the anomaly to a per-site range.

    Everything below drives the library directly, so nothing here needs the
    `conduit` command installed.
    """)
    return


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
    from conduit.importing import import_user_module

    # make_data.py sits next to this notebook. This is the same loader conduit uses
    # for an `_import_path` naming a .py file, so nothing goes on sys.path.
    make_data = import_user_module(str(recipe_dir / "make_data.py"))

    rel(make_data.write_inputs(data_dir))
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


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The graph conduit builds

    `conduit.build_graph` returns a `graphviz.Digraph` without running anything, so
    it renders inline. Node labels carry the declared units, so a wiring mistake is
    often visible before a dry run reports it.
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
    ## Validate, then run

    `conduit.dry_run` parses the config, opens the input headers, builds the DAG and
    checks every contract, without executing a node. Only then is it worth spending
    compute. It returns a `DryRunReport`, one `Stage` per thing it checked.
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
    return


@app.cell
def _(conduit, config_path, mo, rel):
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
    result = run.outputs["climate"]
    return (result,)


@app.cell(hide_code=True)
def _(mo, rel, result, run):
    import xarray as xr

    written = run.written[0].path
    with xr.open_dataset(written) as saved:
        sha256 = saved.attrs["conduit_config_sha256"]

    mo.md(f"""
    ## The output

    `run.outputs` holds the datasets in memory, carrying the units declared on the
    nodes:

    - `temperature_anomaly` — {result["temperature_anomaly"].attrs.get("units")}
    - `anomaly_range` — {result["anomaly_range"].attrs.get("units")}

    Provenance is stamped as the file is written rather than onto the returned
    dataset, so it is read back from `{rel(written)}`: the config text, and
    `conduit_config_sha256 = {sha256[:16]}…`
    """)
    return


@app.cell
def _(result):
    result
    return


if __name__ == "__main__":
    app.run()
