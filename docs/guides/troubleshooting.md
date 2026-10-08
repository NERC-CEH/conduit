---
title: Troubleshooting
icon: lucide/wrench
---

# Troubleshooting

## Installation

### `graphviz` not found when running `conduit graph`

`conduit graph` needs the system Graphviz binary, not just the Python package:

```sh
sudo apt install graphviz     # Ubuntu/Debian
brew install graphviz         # macOS
sudo dnf install graphviz     # Fedora
```

### `conduit gridded` reports a missing extra

Install the `geo` extra; see [Installation](install.md#extras).

## Wiring and contracts

### "No producer for node X" / an unbound input

A node needs an input that nothing produces.
Usually one of:

1. **Not listed in config** — the variable is missing from the `vars` of the right `[inputs.*]` section.
2. **Suffix mismatch** — a parameter named `temperature_daily` needs a `temperature` variable under `[inputs.daily]`, or a `vars` mapping alias.
3. **Wrong resolution** — the variable exists only at another frequency; add a [`[[resample]]`](../reference/configuration.md#resample).

### A unit / dimension mismatch error

A node's declared contract disagrees with its producer's; see [Reading a contract failure](validate/validate-before-running.md#reading-a-contract-failure).
To relax the check, adjust the [`[annotations]`](../reference/configuration.md#annotations) policy.

### `[[resample]]` entry is missing required key `freq`

Every `[[resample]]` needs an explicit `freq`, a pandas offset alias such as `"7D"`, `"1ME"` or `"W-SUN"`, because no frequency is inferred from labels like `daily`.
Resampling only aggregates; for a finer resolution, provide finer input data.

### Time index frequency mismatch

`frequency mismatch on 'time': expected '7D', got 'D'` means the data contradicts a declared `Freq` contract.
Either the declaration or the data is wrong; fix whichever, or drop the declaration.

`frequency of 'time' is uninferable` means the axis has fewer than three timestamps or irregular spacing, so the declaration could not be tested.
This warns by default; set `on_uninferable` in [`[annotations]`](../reference/configuration.md#annotations) to `"error"` to make it fatal, or `"ignore"` for short test fixtures.

## Data

### CSV file not loading

CSV inputs must have a parseable date as the **first column**, one row per time step:

```csv
time,precipitation,temperature
2020-01-01,3.2,8.1
2020-01-02,0.0,9.3
```

### NetCDF file has no CRS / wrong spatial dimensions

The gridded path expects a CRS attribute.
If your file lacks one, write it before loading:

```python
import xarray as xr

ds = xr.open_dataset("data.nc")
ds = ds.rio.write_crs("EPSG:4326")  # or your CRS
ds.to_netcdf("data_with_crs.nc")
```

## Running pipelines

### `'time' coordinate does not match Zarr store`

A subset run produced a time axis that differs from the shared store's, so the config has changed since the store was created: a different `[[resample]]` `freq`, input file, or date range.
Re-create the store from the current config:

```sh
conduit gridded create-store config.toml --overwrite
```

`--overwrite` erases what other subset runs have written, so re-run them all afterwards.

### Empty or missing output

Check that the `[outputs.*]` `vars` name nodes that exist, that the output's parent directory exists, and that the input data covers the range you expect.
`--dry-run` checks the first two.

### Slow on large grids

- Validate on a small [`[subset]`](../reference/configuration.md#subset) first.
- Bound memory with [`[blocking]`](../reference/configuration.md#blocking).
- Enable [`[cache]`](../reference/configuration.md#cache) for iterative re-runs.
- Parallelise across shards; see [Scale up](run/scale-up.md).

## Visualisation

### The graph is too large to read

Pass `conduit graph` a `--style` file with Graphviz sizing attributes, or draw part of the DAG in Python:

```python
from conduit import build_driver, load_config

parsed = load_config("config.toml")
dr = build_driver(
    modules=parsed.modules,
    config=parsed.driver_config,
    node_specs=parsed.node_specs,
)
dr.visualize_path_between("temperature_daily", "aridity_index_daily")
```
