# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "satterc==0.4.1",
#   "marimo",
#   "matplotlib==3.10.9",
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
    # Getting started with SatTerC

    This notebook walks through running a SatTerC pipeline step by step.
    It is aimed at users who are new to SatTerC, and assumes only basic familiarity with Python.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    /// admonition | Running this notebook yourself

    ### Option A — standalone, using `uv` (recommended)

    [uv](https://docs.astral.sh/uv/) is a fast Python package manager and installer.
    If you have it installed, download this file and run:

    ```bash
    uv run 00-getting-started-csv.py
    ```

    `uv` will read the dependency list embedded at the top of this file, install everything
    it needs into a temporary isolated environment, and open the notebook in your browser.
    You do not need to install SatTerC separately.

    ### Option B — using an existing Python environment

    If SatTerC is already installed in a Python environment (for example, the project
    development environment), activate that environment and run:

    ```bash
    marimo run 00-getting-started-csv.py
    ```
    ///
    """)
    return


@app.cell
def _():
    import tempfile
    from pathlib import Path

    import marimo as mo
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
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 1: Configure the pipeline

    A SatTerC pipeline is described by a configuration file written in
    [TOML](https://toml.io/en/) — a simple, human-readable format.
    Every section in the config activates a pipeline component — `[models.splash]` runs the
    SPLASH water-balance model, `[inputs.daily]` loads daily climate data from the given path,
    and `[outputs.daily]` saves the named variables to disk when the pipeline finishes.
    """)
    return


@app.cell
def _():
    config_toml = """
    [models.splash]

    [inputs.daily]
    path = "daily.csv"
    vars = [
      "precipitation",
      "sunshine_fraction",
      "temperature",
    ]

    [inputs.static]
    path = "static.json"
    vars = [
      "elevation",
      "latitude",
      "max_soil_moisture",
    ]

    [outputs.daily]
    path = "results/daily.csv"
    vars = [
      "actual_evapotranspiration",
      "soil_moisture",
      "runoff",
    ]
    """
    return (config_toml,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 2: Generate synthetic input data

    SatTerC reads input data from files — the format is detected automatically from
    the file extension listed in the configuration. SatTerC's built-in synthetic
    data generator supports NetCDF, Zarr, CSV, Parquet, and JSON output, making
    it easy to produce realistic stand-in inputs in whatever format you need.

    Since we do not have real data to hand, we will use the generator to produce
    single-site CSV and JSON inputs. The generated data covers one virtual site
    over a two-year period.

    > **If you have real data**, skip ahead to the *Using your own data* section at the bottom
    > of this notebook before running the pipeline.
    """)
    return


@app.cell
def _(
    Config,
    Path,
    config_toml,
    generate_synthetic_data,
    load_inputs,
    tempfile,
):
    _tmpdir = Path(tempfile.mkdtemp())

    # Parse the embedded config string
    parsed_config = Config.loads(config_toml).parse()

    # Redirect the input paths to files we will generate in a temporary directory
    parsed_config.input_specs["daily"].path = str(_tmpdir / "daily.csv")
    parsed_config.input_specs["static"].path = str(_tmpdir / "static.json")

    # Generate synthetic data — this may take a few seconds
    generate_synthetic_data(config=parsed_config, grid=(1, 1), n_days=730, seed=42)

    # Load the generated data as inputs for the pipeline
    inputs = load_inputs(parsed_config.input_specs)

    print(f"Synthetic data written to: {_tmpdir}")
    return inputs, parsed_config


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 3: Build the pipeline

    SatTerC represents a pipeline as a Directed Acyclic Graph (DAG) — a network of nodes
    where each node is a computation, and edges show which computations depend on which others.

    Building the pipeline means constructing this graph from the modules and configuration
    you specified. Below we visualise the portion of the graph running from the daily
    precipitation input through to the soil moisture output.
    """)
    return


@app.cell
def _(build_driver, parsed_config):
    dr = build_driver(
        modules=parsed_config.modules,
        config=parsed_config.driver_config,
    )
    return (dr,)


@app.cell
def _(dr):
    dr.visualize_path_between(
        "precipitation_daily",
        "soil_moisture_daily",
        show_legend=False,
        graphviz_kwargs={"graph_attr": {"ratio": "compress", "size": "10,15"}},
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 4: Run the pipeline

    We run the pipeline by calling `dr.execute()`, passing the loaded inputs and naming
    the output variables we want back.

    Here we request the output variables listed in `[outputs.daily]` and merge them into
    a single in-memory Dataset — useful for exploration and plotting without writing any files.
    """)
    return


@app.cell
def _(dr, get_final_vars, get_outputs, inputs, parsed_config):
    _results = dr.execute(
        get_final_vars({"daily": parsed_config.output_specs["daily"]}),
        inputs=inputs,
    )
    get_outputs(_results, parsed_config.output_specs)["daily"].info()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 5: Inspect the results

    Let us plot the simulated soil moisture over the two-year period.
    Soil moisture rises after precipitation events and falls during dry periods —
    a clear seasonal signal should be visible.
    """)
    return


@app.cell
def _(dr, inputs, plt):
    _outputs = dr.execute(["soil_moisture_daily"], inputs=inputs)
    soil_moisture = _outputs["soil_moisture_daily"].isel(pixel=0)

    fig, ax = plt.subplots(figsize=(10, 3))
    soil_moisture.plot(ax=ax)
    ax.set_ylabel("Soil moisture (mm)")
    fig.tight_layout()
    fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Using your own data

    To run the pipeline on real data instead of synthetic data, follow these steps.

    ### 1. Save the config to a file

    Run the cell below. It will write the embedded config to a file called
    `my_pipeline.toml` in your current working directory.
    """)
    return


@app.cell
def _(Path):
    _output_path = Path("my_pipeline.toml")

    # Uncomment this line!
    # _output_path.write_text(config_toml.strip())
    # print(f"Config written to: {_output_path.resolve()}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2. Prepare your data files

    **Daily CSV** — one row per day, first column a parseable date:

    ```csv
    time,precipitation,sunshine_fraction,temperature
    2020-01-01,3.2,0.45,8.1
    2020-01-02,0.0,0.71,9.3
    ...
    ```

    **Static JSON** — a plain key → scalar mapping:

    ```json
    {
      "elevation": 150.0,
      "latitude": 51.5,
      "max_soil_moisture": 200.0
    }
    ```

    ### 3. Edit the config file

    Open `my_pipeline.toml` in a text editor.
    Under each `[inputs.*]` section, change the `path` value to point to your real file.
    Paths can be absolute or relative to the location of the config file. For example:

    ```toml
    [inputs.daily]
    path = "/data/my-site/daily.csv"
    vars = [
      "precipitation",
      "sunshine_fraction",
      "temperature",
    ]

    [inputs.static]
    path = "/data/my-site/static.json"
    vars = [
      "elevation",
      "latitude",
      "max_soil_moisture",
    ]
    ```

    ### 4. Load the config from the file

    Replace the config and data-generation cells in this notebook with:

    ```python
    from satterc import load_config

    parsed_config = load_config("my_pipeline.toml")
    ```

    `load_config` reads the TOML file and resolves all paths relative to the file's location.

    ### 5. Remove the data generation cell

    You no longer need to generate synthetic data — delete that cell.
    The pipeline will load your real CSV and JSON files directly.
    """)
    return


if __name__ == "__main__":
    app.run()
