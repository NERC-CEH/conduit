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
    from typing import Annotated

    import marimo as mo
    import numpy as np
    import xarray as xr
    from xarray_annotated.units import policy

    from conduit import declare_units

    return Annotated, declare_units, mo, np, policy, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Add unit contracts

    conduit's flagship feature is **whole-DAG contract checking**: it proves your whole
    pipeline is consistent *before any compute runs*, straight from your type
    annotations. This notebook layers units onto plain functions and shows conduit
    **convert** compatible units, **reject** incompatible ones, and do it all *before*
    the numbers matter.

    We use units because they're the most familiar contract, but the same machinery
    covers dimensions, coordinates and dtypes — see
    [Contracts before compute](../concepts/contracts.md).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A node that requires — and produces — a unit

    Annotate a function's parameters and return with `Annotated[xr.DataArray, "<unit>"]`
    (CF/UDUNITS strings like `"Pa"`, `"hPa"`, `"degC"`). `@declare_units` reads those
    hints: it validates that each argument arrives in a compatible unit and stamps the
    declared unit onto the result. This turns the function into a *typed producer and
    consumer* — one conduit can reason about statically.
    """)
    return


@app.cell
def _(Annotated, declare_units, xr):
    @declare_units
    def pressure_anomaly(
        pressure: Annotated[xr.DataArray, "Pa"],
    ) -> Annotated[xr.DataArray, "Pa"]:
        """Deviation of pressure from its time mean."""
        return pressure - pressure.mean("time")

    return (pressure_anomaly,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Automatic conversion

    Our input is stored in **hectopascals**, but the node declares **pascals**. conduit
    converts it (×100) before the function runs and stamps the declared unit — you never
    hand-write `* 100`. (`policy(on_missing="error")` makes a missing/unparseable unit a
    hard error for this block; the default merely warns.)
    """)
    return


@app.cell
def _(np, policy, pressure_anomaly, xr):
    pressure_hpa = xr.DataArray(
        1013.25 + np.random.default_rng(0).normal(0.0, 5.0, size=(90, 3)),
        dims=("time", "site"),
        coords={
            "time": xr.date_range("2020-01-01", periods=90, freq="D"),
            "site": ["a", "b", "c"],
        },
        attrs={"units": "hPa"},
    )
    with policy(on_missing="error"):
        anomaly_pa = pressure_anomaly(pressure_hpa)
    anomaly_pa
    return anomaly_pa, pressure_hpa


@app.cell(hide_code=True)
def _(anomaly_pa, mo):
    mo.md(
        f"""
        The input was hectopascals; the result is stamped
        **`{anomaly_pa.attrs.get("units")}`** — conduit reconciled the two for you.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Incompatible units are rejected

    Feed a *mass* where a *pressure* is declared and there is no conversion — it's a
    dimensional error, caught instead of producing a silently wrong number.
    """)
    return


@app.cell
def _(policy, pressure_anomaly, pressure_hpa):
    pressure_wrong = pressure_hpa.copy()
    pressure_wrong.attrs["units"] = "kg"  # mass, not pressure!
    try:
        with policy(on_missing="error"):
            pressure_anomaly(pressure_wrong)
        incompatible_result = "no error (unexpected)"
    except Exception as exc:
        incompatible_result = f"{type(exc).__name__}: {exc}"
    incompatible_result
    return (incompatible_result,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tuning the strictness

    By default a *value-changing* conversion (hPa → Pa) happens silently. Set
    `on_inexact="error"` (the `exact = true` knob in a `[annotations]` config section)
    to forbid implicit conversion and demand the declared unit exactly:
    """)
    return


@app.cell
def _(policy, pressure_anomaly, pressure_hpa):
    try:
        with policy(on_missing="error", on_inexact="error"):
            pressure_anomaly(pressure_hpa)  # hPa where Pa is declared: value-changing
        inexact_result = "converted (unexpected under exact policy)"
    except Exception as exc:
        inexact_result = f"rejected under exact policy: {type(exc).__name__}"
    inexact_result
    return (inexact_result,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## From one function to the whole graph

    Everything above validated *one* function at call time. The same `@declare_units`
    declarations power conduit's real payoff: when you `build_driver(...)`, conduit
    checks that **every edge** in the DAG has a compatible producer and consumer —
    *before any node runs*. And `conduit run config.toml --dry-run` goes further, checking
    your input **files'** declared units against every consumer without executing a thing.
    A `hPa`-vs-`Pa` slip, a transposed axis, or a renamed input is caught up front, not
    40 minutes into a run.

    In a config you'd tune this globally:

    ```toml
    [annotations]
    mode = "strict"   # "strict" | "warn" (default) | "off"
    exact = false     # true = reject value-changing conversions (the on_inexact="error" above)
    ```

    See [Drive conduit from Python](../guides/drive-from-python.md) to build and run a whole DAG,
    and [Contracts before compute](../concepts/contracts.md) for how the check
    generalises to dims, coords and dtypes.
    """)
    return


if __name__ == "__main__":
    app.run()
