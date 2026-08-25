---
title: Test your pipeline
icon: lucide/flask-conical
---

# Test your pipeline

Contracts show your pipeline is *consistent*.
Tests are how you show it is *right*.
The two barely overlap: a contract check will happily pass a node that sums a rate it should have averaged, and a unit test will happily pass a node whose output nothing downstream can consume.

Three things are worth testing, and each wants a different tool.

## 1. Node functions, as plain functions

A conduit node is an ordinary function of xarray objects with no framework dependency, so test it by calling it:

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

Two things to know about calling a decorated node directly:

- `@declare_units` runs on the call, so the argument's `units` attribute is validated and converted just as it would be in a pipeline. Passing an array with no `units` attribute exercises the `on_missing` policy rather than your function.
- The decorators do not need a config, a driver, or a DAG. Nothing about the test has to know conduit exists beyond the import.

This is where the science belongs.
Assert on known analytic cases, on conservation properties, on limits, or on whatever else tells you the calculation is the one you meant.

## 2. The config, without computing anything

`conduit.dry_run` builds the graph, checks every contract against your real input files, and checks the wiring, without executing a node.
That makes it fast enough to run on every commit:

```python
from pathlib import Path

import conduit


def test_config_is_valid():
    report = conduit.dry_run(Path("config.toml"))

    # A hard failure raises, so reaching here means the pipeline is valid.
    # Assert on findings too if you want soft issues to fail the build.
    assert not [f for stage in report.stages for f in stage.findings]
```

A hard failure raises out of `dry_run`, so a report exists only for a pipeline that got through.
`Stage.findings` holds the soft issues the active `[annotations]` policy let past.

Run this as a CI step and a renamed input, a mistyped section, a unit that stopped matching or an output nothing produces will all fail the build in seconds.
The [`--dry-run` guide](../running/validate-before-running.md) covers what each stage checks and what the exit codes mean.

If your inputs are large or not present in CI, point the test at a small synthetic file with the same headers.
The contract check reads metadata, not arrays, so a file of the right shape and units is enough.

## 3. The pipeline end to end

For the whole thing, run it over small synthetic inputs and assert on the outputs.
conduit's own test suite does this with session-scoped synthetic NetCDF fixtures, and the documentation recipes are tested the same way — see [`tests/test_recipes.py`](https://github.com/NERC-CEH/conduit/blob/main/tests/test_recipes.py), which executes each recipe's notebook and then checks the file it wrote:

```python
def test_pipeline_writes_expected_variables(tmp_path):
    conduit.run(Path("config.toml"))

    with xr.open_dataset("results/anomaly.nc") as result:
        assert {"temperature_anomaly", "anomaly_range"} <= set(result)
        assert result.temperature_anomaly.attrs["units"] == "degC"
```

Generate the inputs from a fixed seed so the expected values are stable.
Keep them small. This test is about the wiring and the file layout; the numerics belong in the node tests above.

## What to assert on

Roughly in order of how often they catch something:

| Assert | Catches |
|---|---|
| `dry_run(...)` completing | renamed inputs, config typos, contract drift |
| Node output values on a known case | the science being wrong |
| Output variables present in the written file | an output section that stopped matching a node |
| Output `units` attributes | a node that lost its declaration |
| Output dimension sizes | a resample or a reduction going the wrong way |

Skip asserting that a node produces the units it declares.
The contract check already covers that, and a test restating it passes for as long as the declaration exists, whether or not the declaration is right.

## Where next

- [Validate before running](../running/validate-before-running.md) — every stage `--dry-run` performs.
- [Drive conduit from Python](../running/drive-from-python.md) — the API these tests call.
- [Declaring contracts](contracts.md) — what the checks cover, so your tests do not have to.
