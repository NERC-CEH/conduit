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
    # Unit-safe pipelines

    conduit's flagship feature is **unit validation**, built on
    [pint](https://pint.readthedocs.io) and [cf-xarray](https://cf-xarray.readthedocs.io).
    A node declares the units it expects and produces via type annotations; conduit then
    *converts* compatible inputs, *rejects* incompatible ones, and *stamps* the declared
    unit onto outputs — so a `"g m-2 d-1"` can never be silently fed where a `"kg"` is
    expected.
    """)
    return


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import xarray as xr
    from xarray_annotated.units import policy

    from conduit import declare_units

    return declare_units, mo, np, policy, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Declaring units on a node

    Annotate parameters and the return value with `Annotated[xr.DataArray, "<unit>"]`. The
    units are CF/UDUNITS strings (e.g. `"Pa"`, `"hPa"`, `"umol m-2 s-1"`). Here a trivial
    node simply passes pressure through, declaring it in pascals.
    """)
    return


@app.cell
def _(declare_units, xr):
    from typing import Annotated

    @declare_units
    def mean_pressure(
        pressure: Annotated[xr.DataArray, "Pa"],
    ) -> Annotated[xr.DataArray, "Pa"]:
        return pressure.mean("time")

    return (mean_pressure,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Automatic conversion

    Our input is in **hectopascals**, but the node declares **pascals**. conduit converts
    it (×100) and stamps the declared unit — no manual bookkeeping.
    """)
    return


@app.cell
def _(mean_pressure, np, units, xr):
    pressure_hpa = xr.DataArray(
        np.full((3, 2), 1013.25),
        dims=("time", "site"),
        coords={"time": np.arange(3), "site": ["a", "b"]},
        attrs={"units": "hPa"},
    )
    with policy(on_missing="error"):
        converted = mean_pressure(pressure_hpa)
    converted  # ~101325 Pa, units attribute == "Pa"
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Incompatible units are rejected

    Feeding a mass where a pressure is declared is a dimensional error — caught instead of
    producing a silently wrong result.
    """)
    return


@app.cell
def _(mean_pressure, np, units, xr):
    pressure_wrong = xr.DataArray(
        np.full((3, 2), 1.0),
        dims=("time", "site"),
        coords={"time": np.arange(3), "site": ["a", "b"]},
        attrs={"units": "kg"},  # not a pressure!
    )
    try:
        with policy(on_missing="error"):
            mean_pressure(pressure_wrong)
        message = "no error (unexpected)"
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
    message
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Validation policies and build-time checks

    The validation policy is process-wide (`xarray_annotated.units.set_policy(...)`, the
    ``XARRAY_ANNOTATED_ENABLED``, ``XARRAY_ANNOTATED_UNITS_ON_MISSING``, and
    ``XARRAY_ANNOTATED_UNITS_ON_INEXACT`` env vars, or the traditional ``[units]`` config
    section):

    - **on_missing=`"error"`** — missing/unparseable units raise.
    - **on_missing=`"warn"`** (default) — missing units warn (`UnitsWarning`) but
      don't fail.
    - **on_inexact=`"error"`** — value-changing conversions (e.g. hPa → Pa) raise.
    - **enabled=`False`** — skip validation entirely.

    The same declarations also power *build-time* checks: when you `build_driver(...)`,
    conduit verifies that every edge's producer and consumer units agree, and
    ``conduit run --dry-run`` validates your input files' units — all before a single node
    executes.
    """)
    return


if __name__ == "__main__":
    app.run()
