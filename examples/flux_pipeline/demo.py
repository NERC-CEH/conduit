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
    import numpy as np
    import xarray as xr
    from xarray_annotated.units import use_cf_units

    use_cf_units()
    return mo, np, xr


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
def _(data_dir, np, xr):
    rng = np.random.default_rng(20240301)
    time = np.arange(
        "2023-01-01", "2024-01-01", np.timedelta64(30, "m"), dtype="datetime64[s]"
    )
    day = (time.astype("datetime64[D]") - np.datetime64("2023-01-01", "D")).astype(int)
    hour = (time.astype("datetime64[s]").astype(int) % 86400) / 3600.0

    declination = np.deg2rad(23.44) * np.sin(2 * np.pi * (day - 80) / 365.25)
    latitude = np.deg2rad(52.0)
    hour_angle = np.deg2rad(15.0 * (hour - 12.0))
    solar_elevation = np.clip(
        np.sin(latitude) * np.sin(declination)
        + np.cos(latitude) * np.cos(declination) * np.cos(hour_angle),
        0,
        None,
    )
    ppfd_values = (
        2100.0
        * solar_elevation
        * (0.85 + 0.15 * rng.normal(size=time.size).clip(-1, 1))
    ).clip(0)
    tair_c = (
        9.5
        + 8.5 * np.sin(2 * np.pi * (day - 110) / 365.25)
        + 4.0 * np.sin(2 * np.pi * (hour - 9) / 24.0)
        + 0.8 * rng.normal(size=time.size)
    )
    reco = 2.60 * 2.0 ** ((tair_c - 10.0) / 10.0)
    lai = 0.25 + 0.75 * np.clip(np.sin(np.pi * (day - 90) / 190.0), 0, None)
    gpp_max = 21.4 * lai
    gpp = np.where(
        ppfd_values > 0,
        0.055 * ppfd_values * gpp_max / (0.055 * ppfd_values + gpp_max),
        0.0,
    ) / (1.0 + np.exp(-(tair_c - 2.0)))
    nee = reco - gpp + 0.35 * rng.normal(size=time.size)
    qc = np.zeros(time.size, dtype="int8")
    qc[rng.random(time.size) < 0.07] = 1
    qc[rng.random(time.size) < 0.02] = 2

    def series(values, units, dtype="float64"):
        return xr.DataArray(
            values.astype(dtype),
            dims="time",
            coords={"time": time},
            attrs={"units": units},
        )

    nee_raw = series(nee, "umol m-2 s-1")
    tair = series(tair_c + 273.15, "K")
    ppfd = series(ppfd_values, "umol m-2 s-1")
    qc_data = series(qc, "1", dtype="int8")

    flux_dataset = xr.Dataset(
        {"nee_raw": nee_raw, "tair": tair, "ppfd": ppfd, "qc": qc_data}
    )
    flux_dataset.to_netcdf(data_dir / "flux.nc")

    conversion = 1e-6 * 12.011 * 86400.0
    gpp_daily = series(gpp, "umol m-2 s-1").resample(time="D").mean() * conversion
    sat_gpp = (
        gpp_daily.resample(time="W-SUN").mean()
        * (1.0 + 0.08 * rng.normal(size=gpp_daily.resample(time="W-SUN").count().size))
    ).assign_attrs(units="g m-2 d-1")
    xr.Dataset({"sat_gpp": sat_gpp}).to_netcdf(data_dir / "satellite.nc")
    return


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
