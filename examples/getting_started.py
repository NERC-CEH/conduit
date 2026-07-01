# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "conduit==0.1.0",
#   "marimo",
#   "numpy==2.4.4",
#   "xarray==2026.4.0",
# ]
#
# [tool.uv.sources]
# conduit = { path = ".." }
# ///

import marimo

__generated_with = "0.23.5"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Getting started with conduit

    **conduit** turns a plain-text [TOML](https://toml.io) file into an executable
    [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) pipeline over
    [xarray](https://xarray.dev) data, with optional [pint](https://pint.readthedocs.io)
    unit validation.

    This notebook builds a tiny pipeline end to end: load an input, derive a new
    variable with a config-defined node, and write the result — no domain models, no
    geospatial machinery.
    """)
    return


@app.cell
def _():
    import tempfile
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import xarray as xr

    from conduit import (
        build_driver,
        get_final_vars,
        get_outputs,
        load_config,
        load_inputs,
    )

    return (
        Path,
        build_driver,
        get_final_vars,
        get_outputs,
        load_config,
        load_inputs,
        mo,
        np,
        tempfile,
        xr,
    )


@app.cell
def _(Path, tempfile):
    workdir = Path(tempfile.mkdtemp())
    return (workdir,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Some input data

    conduit works with the xarray objects you already use. Here we make a small
    `temperature` field over `time` and `site` — note there is **no** notion of a fixed
    frequency or a spatial grid; the dimensions are whatever your data has.
    """)
    return


@app.cell
def _(np, workdir, xr):
    times = xr.date_range("2020-01-01", periods=90, freq="D")
    temperature = xr.DataArray(
        10.0 + 8.0 * np.sin(np.linspace(0, 3.14, 90))[:, None] + np.arange(3)[None, :],
        dims=("time", "site"),
        coords={"time": times, "site": ["a", "b", "c"]},
        attrs={"units": "degC"},
    )
    input_path = workdir / "climate.nc"
    xr.Dataset({"temperature": temperature}).to_netcdf(input_path)
    temperature
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Describe the pipeline in TOML

    - `[inputs.climate]` loads `temperature` and exposes it to the DAG as
      `temperature_climate` (the node name is `{var}_{section}`).
    - `[[node]]` defines a derived node inline — here a temperature anomaly — and
      declares its output unit, which conduit validates and stamps.
    - `[outputs.climate]` selects what to write to disk.
    """)
    return


@app.cell
def _(workdir):
    config_toml = """
    [inputs.climate]
    path = "climate.nc"
    vars = ["temperature"]

    [[node]]
    name = "temperature_anomaly_climate"
    inputs = ["temperature_climate"]
    expression = "temperature_climate - temperature_climate.mean('time')"
    units = "degC"

    [outputs.climate]
    path = "anomaly.nc"
    vars = ["temperature_anomaly"]
    """
    config_path = workdir / "pipeline.toml"
    config_path.write_text(config_toml)
    return (config_path,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Run it

    The public API is deliberately thin — it hands you a real Hamilton `Driver` and
    plain xarray objects, so nothing is hidden behind a wrapper.
    """)
    return


@app.cell
def _(
    build_driver,
    config_path,
    get_final_vars,
    get_outputs,
    load_config,
    load_inputs,
):
    parsed = load_config(config_path)
    inputs = load_inputs(parsed.input_specs)
    driver = build_driver(parsed.modules, parsed.driver_config)
    final_vars = get_final_vars(parsed.output_specs)
    results = driver.execute(final_vars, inputs=inputs)
    output = get_outputs(results, parsed.output_specs)["climate"]
    output
    return (output,)


@app.cell(hide_code=True)
def _(mo, output):
    mo.md(
        f"""
        The result is an ordinary `xarray.Dataset` carrying the declared unit:

        - variable: `temperature_anomaly` with dims `{output["temperature_anomaly"].dims}`
        - units attribute: `{output["temperature_anomaly"].attrs.get("units")}`
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Where to go next

    - Swap the `[[node]]` for your own module via `_import_path` (see *Custom modules*).
    - Add unit checking across a whole DAG — see the **Unit-safe pipelines** example.
    - Point the inputs at your real NetCDF/Zarr/CSV files and run `conduit run`.
    """)
    return


if __name__ == "__main__":
    app.run()
