# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "conduit==0.1.0",
#   "marimo",
#   "numpy==2.5.0",
#   "xarray==2026.4.0",
# ]
#
# [tool.uv.sources]
# conduit = { path = ".." }
# ///

import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium")


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
        load_inputs,
        save_outputs,
    )
    from conduit.config import Config

    return (
        Config,
        Path,
        build_driver,
        get_final_vars,
        get_outputs,
        load_inputs,
        mo,
        np,
        save_outputs,
        tempfile,
        xr,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Drive conduit from Python

    The `conduit run` CLI is a thin wrapper over conduit's Python API. Driving that API
    directly gives you fine-grained control: inspect individual nodes, plot
    intermediate results, override values between runs, or skip writing to disk. This
    notebook walks the exact steps `run` takes — end to end, on synthetic data.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Some input data

    conduit works with the xarray objects you already use. Here's a small `temperature`
    field over `time` and `site` — no fixed frequency, no spatial grid; the dimensions
    are whatever your data has. We write it to a scratch NetCDF file.
    """)
    return


@app.cell
def _(Path, np, tempfile, xr):
    workdir = Path(tempfile.mkdtemp())

    temperature = xr.DataArray(
        10.0
        + 8.0 * np.sin(np.linspace(0.0, 3.14, 90))[:, None]
        + np.arange(3)[None, :],
        dims=("time", "site"),
        coords={
            "time": xr.date_range("2020-01-01", periods=90, freq="D"),
            "site": ["a", "b", "c"],
        },
        attrs={"units": "degC"},
    )
    xr.Dataset({"temperature": temperature}).to_netcdf(workdir / "climate.nc")
    temperature
    return temperature, workdir


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Build a config

    A pipeline is a config — a dict with the same structure as a
    [TOML config](../reference/configuration.md), passed straight to `Config`. Here:
    `[inputs.climate]` exposes `temperature` to the DAG as `temperature_climate`
    (`{var}_{section}`); one inline `[[node]]` derives an anomaly and declares its output
    unit; `[outputs.climate]` selects what to write.

    (Already have a file? `Config.load("config.toml")`, or the one-shot
    `conduit.load_config("config.toml")`, which returns the parsed config from step 3.)
    """)
    return


@app.cell
def _(workdir):
    config_data = {
        "inputs": {
            "climate": {"path": str(workdir / "climate.nc"), "vars": ["temperature"]},
        },
        "node": [
            {
                "name": "temperature_anomaly_climate",
                "inputs": ["temperature_climate"],
                "expression": "temperature_climate - temperature_climate.mean('time')",
                "units": "degC",
            },
        ],
        "outputs": {
            "climate": {
                "path": str(workdir / "anomaly.nc"),
                "vars": ["temperature_anomaly"],
            },
        },
    }
    return (config_data,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Parse it

    `.parse()` validates the config and returns a `ParsedConfig` with everything the
    pipeline needs: `modules`, `driver_config`, `input_specs` / `output_specs`, plus the
    parsed cache / blocking / subset specs and contract policy.
    """)
    return


@app.cell
def _(Config, config_data):
    parsed = Config(config_data).parse()
    parsed.modules
    return (parsed,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Build the driver

    `build_driver()` constructs a Hamilton `Driver` **and runs the build-time contract
    check** — every edge is proven consistent before any compute. The driver is the DAG
    runtime; you can inspect it with `dr.display_all_functions()`.
    """)
    return


@app.cell
def _(build_driver, parsed):
    dr = build_driver(modules=parsed.modules, config=parsed.driver_config)
    dr
    return (dr,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Load inputs

    `load_inputs()` reads the files in `input_specs` and returns a flat dict of named
    `DataArray`s, keyed by node name. (Alongside `temperature_climate` you'll see a
    `dates_climate` helper node — conduit exposes each section's time axis too.)
    """)
    return


@app.cell
def _(load_inputs, parsed):
    inputs = load_inputs(parsed.input_specs)
    list(inputs)
    return (inputs,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Execute

    Call `dr.execute()` with the node names you want. `get_final_vars()` turns
    `output_specs` into that flat list. You can also request **any** node by name to
    inspect an intermediate, or `overrides={...}` a node's value without rebuilding the
    DAG.
    """)
    return


@app.cell
def _(dr, get_final_vars, inputs, parsed):
    results = dr.execute(get_final_vars(parsed.output_specs), inputs=inputs)
    list(results)  # a flat dict of {node name: DataArray}
    return (results,)


@app.cell
def _(dr, inputs):
    # request an intermediate node directly
    anomaly = dr.execute(["temperature_anomaly_climate"], inputs=inputs)
    anomaly["temperature_anomaly_climate"]
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Inspect and save

    `get_outputs()` merges the flat results into per-section `Dataset`s — the form most
    plotting/analysis expects (and the declared unit rides along).
    """)
    return


@app.cell
def _(get_outputs, parsed, results):
    datasets = get_outputs(results, parsed.output_specs)
    datasets["climate"]
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    In a notebook you can stop here — the `Dataset` is ready for xarray's plotting
    methods, matplotlib, or anything else. To write one file per `[outputs.*]` section
    (exactly what `conduit run` does), call `save_outputs()`:

    ```python
    save_outputs(datasets, parsed.output_specs)
    ```

    ## Where to go next

    - [Run & visualise](run-and-visualise.md) — the CLI equivalent of this notebook.
    - [Add unit contracts](../get-started/units-and-contracts.md) — the validation this
      pipeline's declared unit plugs into.
    - [Configuration reference](../reference/configuration.md) — the full config schema.
    """)
    return


if __name__ == "__main__":
    app.run()
