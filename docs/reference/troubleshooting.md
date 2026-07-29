---
title: Troubleshooting
icon: lucide/wrench
---

# Troubleshooting & FAQ

Common issues and their fixes.

## Installation

### `graphviz` not found when running `conduit graph`

`conduit graph` needs the system Graphviz binary, not just the Python package:

```sh
sudo apt install graphviz     # Ubuntu/Debian
brew install graphviz         # macOS
sudo dnf install graphviz     # Fedora
```

### `conduit gridded` reports a missing extra

The gridded (parallel-Zarr) commands need the optional `geo` extra
(`rioxarray`/`pyproj`). Install it with `pip install "conduit[geo]"`.

## Wiring and contracts

### "No producer for node X" / an unbound input

A node needs an input that nothing produces. Usually one of:

1. **Not listed in config** — check the variable appears in the `vars` of the right
   `[inputs.*]` section.
2. **Name/suffix mismatch** — node names combine the file variable with the section
   suffix (`{var}{suffix}`); a parameter named `temperature_daily` needs a
   `temperature` variable under a `daily`-suffixed section (or a `vars` mapping alias).
3. **Wrong frequency** — the variable may exist at another resolution; add a
   [`[[resample]]`](configuration.md#resample) step.

Run [`conduit run --dry-run`](../guides/validate-before-running.md) to surface this
before executing.

### A unit / dimension mismatch error

A node's declared contract disagrees with its producer's. See
[Validate before running › reading a contract failure](../guides/validate-before-running.md#reading-a-contract-failure).
To relax an over-strict check, adjust the [`[annotations]`](configuration.md#annotations)
policy.

### `[[resample]]` entry is missing required key `freq`

Every `[[resample]]` needs an explicit `freq` (a pandas offset alias such as `"7D"`,
`"1ME"` or `"W-SUN"`). `from` and `to` only name the nodes to read from and write to —
no frequency is inferred from labels like `daily`/`weekly`. You cannot upsample to a
finer resolution; provide finer data as input instead.

## Data

### CSV file not loading

CSV inputs must have a parseable date as the **first column**, one row per time step:

```csv
time,precipitation,temperature
2020-01-01,3.2,8.1
2020-01-02,0.0,9.3
```

### NetCDF file has no CRS / wrong spatial dimensions

The gridded path expects a CRS attribute. If your file lacks one, write it before
loading:

```python
import xarray as xr

ds = xr.open_dataset("data.nc")
ds = ds.rio.write_crs("EPSG:4326")   # or your CRS
ds.to_netcdf("data_with_crs.nc")
```

### Time index frequency mismatch

`frequency mismatch on 'time': expected '7D', got 'D'` means a consumer declared a
`Freq` contract the data contradicts. Section labels are not involved — nothing is
inferred from a section being called `daily` — so either the declaration or the data is
wrong. Fix whichever, or drop the declaration to opt that node out.

`frequency of 'time' is uninferable` means the axis has fewer than three timestamps or
irregular spacing, so the declaration could not be *tested*. It warns by default; set
`on_uninferable` in [`[annotations]`](configuration.md#annotations) to `"error"` to make
an untested contract fatal, or `"ignore"` to silence it (short test fixtures).

## Running pipelines

### `'time' coordinate does not match Zarr store`

A subset run produced data whose time axis differs from the shared store's. Region
writes don't write coordinates, so this is caught rather than allowed to silently
mislabel the store.

The store's axes are computed from the pipeline when it is created, so this means the
config has changed since — a different `[[resample]]` `freq`, a different input file, a
different date range. Re-create the store from the current config:

```sh
conduit gridded create-store config.toml --overwrite
```

Note `--overwrite` erases data already written into the store by other subset runs, so
re-run them all afterwards.

### Empty or missing output

Check that:

1. The `[outputs.*].vars` are actually produced by an active node.
2. The output's parent directory exists.
3. The input data covers the range you expect.

### Slow on large grids

- Validate on a small [`[subset]`](configuration.md#subset) first.
- Bound memory with [`[blocking]`](configuration.md#blocking).
- Enable [`[cache]`](configuration.md#cache) for iterative re-runs.
- Parallelise across shards — see [Scale up](../guides/scale-up.md).

## Visualisation

### The graph is too large to read

Pass a `--style` file to `conduit graph` with Graphviz sizing attributes, or inspect a
sub-DAG in Python:

```python
from conduit import build_driver, load_config

parsed = load_config("config.toml")
dr = build_driver(modules=parsed.modules, config=parsed.driver_config)
dr.visualize_path_between("temperature_daily", "aridity_index_daily")
```
