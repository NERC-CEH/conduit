# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo",
#     "matplotlib==3.10.9",
#     "satterc==0.4.1",
# ]
#
# [tool.uv.sources]
# satterc = { path = ".." }
# ///

import marimo

__generated_with = "0.23.5"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Example notebook

    This notebook is intended to show how to run a pipeline from within a Python environment, rather than using the CLI command. We will keep the computed outputs, which are `xarray.Dataset` objects, in memory rather than saving them to netcdf files.
    """)
    return


@app.cell
def _():
    import tempfile
    import tomllib
    from pathlib import Path

    import marimo as mo  # required for Markdown etc.
    import matplotlib.pyplot as plt

    from satterc import build_driver, get_final_vars, get_outputs, load_inputs
    from satterc.config import Config
    from satterc.setup_utils.data_gen import generate_synthetic_data

    return (
        Config,
        Path,
        build_driver,
        generate_synthetic_data,
        get_final_vars,
        get_outputs,
        load_inputs,
        mo,
        plt,
        tempfile,
        tomllib,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Pipeline configuration

    The pipeline configuration is defined in a [TOML](https://toml.io/en/) file.

    `satterc` provides a loader / parser for pipeline configurations, which takes a path to a config file and returns a `ParsedConfig` with four attributes:

    1. `modules`: a list of Python modules containing the nodes (functions) which will be used to construct the pipeline.
    2. `driver_config`: a dictionary of additional config options that is applied to the driver at _build time_ (not run time).
    3. `input_specs`: a mapping from frequency to `IOSpec` (path, vars) — consumed by `load_inputs()`.
    4. `output_specs`: a mapping from frequency to `IOSpec` — consumed by `get_outputs()` and `save_outputs()`.
    """)
    return


@app.cell
def _(Config, tomllib):
    _config_toml = """

    [models.splash]

    [models.pmodel]
    method_kphio = "sandoval"
    method_optchi = "lavergne20_c3"

    [models.sgam]

    [models.rothc]
    n_years_spinup = 1
    equilibrium_threshold = 0.0001

    [grid]

    [inputs.daily]
    path = "daily.nc"
    vars = [
      "precipitation",
      "sunshine_fraction",
      "temperature",
      "lai",
      "gpp",
    ]

    [inputs.weekly]
    path = "weekly.nc"
    vars = [
      "co2",
      "fapar",
      "ppfd",
      "pressure",
      "vpd",
    ]

    [inputs.monthly]
    path = "monthly.nc"
    vars = [
      "dummy_variable",
    ]

    [inputs.static]
    path = "static.nc"
    vars = [
      "elevation",
      "plant_type",
      "max_soil_moisture",
      "clay_content",
      "soil_depth",
      "organic_carbon_stocks",
      "root_pool_init",
      "leaf_pool_init",
      "stem_pool_init",
    ]

    [[node]]
    name = "aridity_index_daily"
    inputs = ["precipitation_daily", "actual_evapotranspiration_daily"]
    expression = "precipitation_daily / actual_evapotranspiration_daily"
    units = "1"  # ratio of two mm d-1 fluxes -> dimensionless

    [[node]]
    name = "leaf_area_index_weekly"
    inputs = ["leaf_pool_weekly", "pft_params"]
    expression = 'leaf_pool_weekly / pft_params["leaf_carbon_area"]'
    units = "m2 m-2"  # leaf carbon per ground area / leaf carbon per leaf area

    # SPLASH AET is a daily rate (mm d-1); RothC wants a monthly total (mm).
    # Summing the daily rate over the month integrates it (daily Δt = 1 day, so
    # Σ mm d-1 is numerically the monthly mm total); units = "mm" relabels the
    # rate as the resulting total.
    [[node]]
    name = "evaporation_monthly"
    inputs = ["actual_evapotranspiration_daily"]
    expression = "actual_evapotranspiration_daily.resample(time='1ME').sum()"
    units = "mm"

    # Precipitation is likewise a daily rate (mm d-1); aggregate to a monthly
    # total (mm) for RothC the same way. (Done as a derive rather than a plain
    # [[resample]] because that would feed the mm d-1 rate straight into RothC's
    # mm input and the resample output name would collide with this one.)
    [[node]]
    name = "precipitation_monthly"
    inputs = ["precipitation_daily"]
    expression = "precipitation_daily.resample(time='1ME').sum()"
    units = "mm"

    # Carbon entering the soil each month = the litter produced that month. SGAM's
    # litter_pool is an accumulate-only stock (no decomposition; that is RothC's
    # job), so the monthly litterfall is its *increment*: diff the weekly pool and
    # sum within each month. Using the increment (rather than summing turnover_*)
    # also captures litter from disturbance events, which the turnover outputs omit.
    # SGAM reports g m-2; RothC wants t ha-1, so convert with pint (factor 100).
    [[node]]
    name = "soil_carbon_input_monthly"
    inputs = ["litter_pool_weekly"]
    expression = "litter_pool_weekly.diff('time').resample(time='1ME').sum().assign_attrs(units='g m-2').pint.quantify().pint.to('t ha-1').pint.dequantify()"
    units = "t ha-1"

    [[node]]
    name = "inert_organic_matter"
    inputs = ["organic_carbon_stocks"]
    expression = "0.049 * organic_carbon_stocks**1.139"  # Falloon IOM (t ha-1)
    units = "t ha-1"

    [[resample]]
    vars = [
      "temperature",
      "precipitation",
      "soil_moisture",
      "aridity_index",
    ]
    from_freq = "daily"
    to_freq = "weekly"

    [[resample]]
    vars = [
      "temperature",
    ]
    from_freq = "daily"
    to_freq = "monthly"

    [[resample]]
    vars = ["disturbances"]
    from_freq = "daily"
    to_freq = "weekly"
    aggfunc = "max"

    [outputs.daily]
    path = "results/daily.nc"
    vars = [
      "actual_evapotranspiration",
      "soil_moisture",
      "runoff",
    ]

    [outputs.weekly]
    path = "results/weekly.nc"
    vars = [
      "gpp",
      "leaf_pool",
      "stem_pool",
      "root_pool",
      "litter_pool",
      "leaf_area_index",
    ]

    [outputs.monthly]
    path = "results/monthly.nc"
    vars = [
      "decomposable_plant_material",
      "resistant_plant_material",
      "microbial_biomass",
      "humified_organic_matter",
      "soil_organic_carbon",
      "heterotrophic_respiration",
    ]
    """

    # Parse config directly from the TOML string (no file needed)
    parsed_config = Config(tomllib.loads(_config_toml)).parse()

    # `parsed_config` contains (1) `modules`, (2) `driver_config`, (3) `input_specs`, (4) `output_specs`
    parsed_config
    return (parsed_config,)


@app.cell
def _(Path, generate_synthetic_data, load_inputs, parsed_config, tempfile):
    # Generate synthetic input data into a temporary directory
    _tmpdir = Path(tempfile.mkdtemp())

    parsed_config.input_specs["daily"].path = str(_tmpdir / "daily.nc")
    parsed_config.input_specs["weekly"].path = str(_tmpdir / "weekly.nc")
    parsed_config.input_specs["monthly"].path = str(_tmpdir / "monthly.nc")
    parsed_config.input_specs["static"].path = str(_tmpdir / "static.nc")

    generate_synthetic_data(config=parsed_config, grid=(4, 4), n_days=730, seed=42)

    inputs = load_inputs(parsed_config.input_specs)
    return (inputs,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Building the pipeline

    Building the pipeline really means building the 'driver'.

    `satterc` provides a function `build_driver` which takes a list of modules and a driver configuration, and returns a built driver.
    Notice that we do not pass `targets` during build stage; we are only required to supply `targets` when actually executing the pipeline.

    Once we have constructed the driver, we can inspect it in various ways, including visualising the DAG.
    Since the entire pipeline is very large, we can focus on visualising sub-DAGs between two given nodes.
    """)
    return


@app.cell
def _(build_driver, parsed_config):
    # Build the driver object
    dr = build_driver(
        modules=parsed_config.modules,
        config=parsed_config.driver_config,
    )

    # This produces a visualisation of the entire DAG, which is too large..
    # dr
    return (dr,)


@app.cell
def _(dr):
    # Here we restrict the visualisation to a sub-DAG between sgam and rothc
    # NOTE: I need to figure out how to filter out the config inputs!
    dr.visualize_path_between(
        "sgam",
        "rothc",
        # strict_path_visualization=True,
        show_legend=False,
        # Make the graph smaller to fit the screen
        graphviz_kwargs={
            "graph_attr": {
                "ratio": "compress",
                "size": "10,15",  # Width and height in inches
            }
        },
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Running the pipeline

    To run the pipeline we call `dr.execute()`, providing:

    1. `final_vars`: the output variable names to compute.
    2. `inputs`: the raw input DataArrays returned by `load_inputs()`.
    3. Optionally, `overrides`: overrides for any computed node in the DAG.\*

    We collect the output variable names from `parsed_config.output_specs` and merge them
    into per-frequency Datasets using `get_outputs()`.

    \* The `overrides` option will be useful later on when we want to run the DAG repeatedly with different parameter values, without rebuilding it from scratch each time.
    """)
    return


@app.cell
def _(dr, get_final_vars, get_outputs, inputs, parsed_config):
    _target_vars = get_final_vars(parsed_config.output_specs)
    _results = dr.execute(_target_vars, inputs=inputs)
    _output_datasets = get_outputs(_results, parsed_config.output_specs)
    _output_datasets["monthly"].info()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Comparing input LAI with modelled LAI

    We can compare input and modelled LAI by requesting those two nodes as `final_vars`.
    """)
    return


@app.cell
def _(dr, inputs, plt):
    _outputs = dr.execute(["lai_daily", "leaf_area_index_weekly"], inputs=inputs)

    input_lai, modelled_lai = _outputs["lai_daily"], _outputs["leaf_area_index_weekly"]

    n_pixels = input_lai.sizes["pixel"]
    fig, axes = plt.subplots(n_pixels, 1, figsize=(10, 3 * n_pixels), sharex=True)
    for i, ax in enumerate(axes):
        input_lai[:, i].plot(ax=ax, label="Input LAI")
        modelled_lai[:, i].plot(ax=ax, label="Modelled LAI")
        ax.legend()
    fig.tight_layout()

    fig
    return


if __name__ == "__main__":
    app.run()
