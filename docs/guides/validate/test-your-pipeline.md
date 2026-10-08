---
title: Test your pipeline
icon: lucide/flask-conical
---

# Test your pipeline

Contracts show your pipeline is *consistent*; tests show it is *right*.
The two barely overlap: a contract check will pass a node that sums a rate it should have averaged, and a unit test will pass a node whose output nothing downstream can consume.
Three things are worth testing, each with a different tool.

## 1. Node functions, as plain functions

A node is an ordinary function of xarray objects, so test it by calling it:

```python
import numpy as np
import pytest
import xarray as xr

from mypipeline.nodes import temperature_anomaly_climate


def test_anomaly_is_centred():
    time = xr.date_range("2020-01-01", periods=10, freq="D")
    temperature = xr.DataArray(
        np.arange(10.0),
        dims="time",
        coords={"time": time},
        attrs={"units": "degC"},
    )

    anomaly = temperature_anomaly_climate(temperature)

    assert float(anomaly.mean("time")) == pytest.approx(0.0)
```

`@declare_units` runs on the call, validating and converting the argument's `units` as it would in a pipeline, with no config or DAG needed.
Give test arrays a `units` attribute, or you will be testing the missing-units policy rather than your function.

This is where the science belongs: assert on known analytic cases, conservation properties, limits, or whatever else tells you the calculation is the one you meant.

## 2. The config, without computing anything

`conduit.dry_run` runs every check against your real input files without executing a node, so it is fast enough for every commit:

```python
from pathlib import Path

import conduit


def test_config_is_valid():
    report = conduit.dry_run(Path("config.toml"))

    # A hard failure raises, so reaching here means the pipeline is valid.
    # Assert on findings too if you want soft issues to fail the build.
    assert not [f for stage in report.stages for f in stage.findings]
```

`Stage.findings` holds the soft issues the active `[annotations]` policy let through.
In CI, this catches a renamed input, a mistyped section, a unit that stopped matching or an output nothing produces, in seconds.
[Validate before running](validate-before-running.md) lists every stage.

If your inputs are large or absent in CI, point the test at a small synthetic file with the same variables and metadata: the checks read headers, not arrays.

## 3. The pipeline end to end

Run the whole pipeline over small synthetic inputs and assert on the outputs.
conduit tests its own recipes this way; see [`tests/test_recipes.py`](https://github.com/NERC-CEH/conduit/blob/main/tests/test_recipes.py).

```python
def test_pipeline_writes_expected_variables():
    conduit.run(Path("config.toml"))

    with xr.open_dataset("results/anomaly.nc") as result:
        assert {"temperature_anomaly", "anomaly_range"} <= set(result)
        assert result.temperature_anomaly.attrs["units"] == "degC"
```

Generate the inputs from a fixed seed so expected values are stable, and keep them small.
This test is about wiring and file layout; the numerics belong in the node tests.

## What to assert on

Roughly in order of how often they catch something:

| Assert | Catches |
|---|---|
| `dry_run(...)` completing | renamed inputs, config typos, contract drift |
| Node output values on a known case | the science being wrong |
| Output variables present in the written file | an output section that stopped matching a node |
| Output `units` attributes | a node that lost its declaration |
| Output dimension sizes | a resample or a reduction going the wrong way |

Don't assert that a node produces the units it declares.
The contract check covers that, and such a test passes whenever the declaration exists, right or wrong.
