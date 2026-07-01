---
title: Troubleshooting
icon: lucide/wrench
---

# Troubleshooting & FAQ

Common issues and their solutions.

## Installation

### `graphviz` not found when running `conduit graph`

The `conduit graph` command requires the system `graphviz` binary, not just the Python package.

```sh
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz

# Fedora
sudo dnf install graphviz
```

### Missing input variable error

The pipeline reports that a required node has no producer. This usually means:

1. **Variable not listed in config** — Check that the variable name appears in the `vars` list of the appropriate `[inputs.*]` section.
2. **Wrong frequency** — The variable may be available at a different temporal resolution. Check if you need a `[[resample]]` section.
3. **Typo in variable name** — Variable names in the config must match the column names in your data file exactly.

### Resampling direction not supported

Only these resampling directions are supported:

| From | To |
|------|-----|
| `daily` | `weekly` |
| `daily` | `monthly` |
| `weekly` | `monthly` |

You cannot upsample (e.g., weekly to daily). If you need data at a finer resolution, it must be provided as input.

## Data

### CSV file not loading

CSV files must have:

- A **date column as the first column**, or a column named `time`
- Dates must be parseable by `pandas.to_datetime`
- One row per time step

Example:

```csv
time,precipitation,temperature
2020-01-01,3.2,8.1
2020-01-02,0.0,9.3
```

### NetCDF file has wrong spatial dimensions

conduit expects gridded NetCDF files to have a CRS (Coordinate Reference System) attribute. If your file uses non-standard dimension names, you may need to set the CRS:

```python
import xarray as xr

ds = xr.open_dataset("data.nc")
ds = ds.rio.write_crs("EPSG:4326")  # or your CRS
ds.to_netcdf("data_with_crs.nc")
```

### Time index frequency mismatch

For input sections whose label is a recognised frequency, conduit validates that the
time index matches it:

- **daily** must have frequency `"D"` (one entry per calendar day)
- **weekly** must have frequency `"W"` or `"7D"`
- **monthly** must have frequency `"ME"` (month-end) or `"MS"` (month-start)

If such data has gaps or irregular spacing, you'll see a validation error — fix the data
before loading. Sections with other labels are not frequency-validated.

## Running Pipelines

### Pipeline runs but produces empty output

Check that:

1. The variables listed in `[outputs.*].vars` are actually produced by the active modules/nodes
2. The output directory exists (create it with `mkdir -p outputs/`)
3. The input data covers the range you expect

### Pipeline is slow on large grids

If a node loops over pixels internally, large grids can be slow. Consider:

- Running on a `[subset]` first to validate your config
- Bounding memory with a `[blocking]` section
- Enabling `[cache]` for iterative re-runs

## DAG and Visualization

### The graph visualization is too large to read

Use the `graphviz` config option in your TOML file to control the output size:

```toml
[graphviz]
size = "20,20"
ratio = "compress"
```

Or visualise a sub-DAG in Python:

```python
from conduit import build_driver, load_config

parsed = load_config("config.toml")
dr = build_driver(modules=parsed.modules, config=parsed.driver_config)
dr.visualize_path_between("precipitation_daily", "soil_moisture_daily")
```

### What does each colour in the graph mean?

| Colour | Node Type |
|--------|-----------|
| Aquamarine | Static inputs |
| Orange | Daily-frequency nodes |
| Yellow | Weekly-frequency nodes |
| Brown | Monthly-frequency nodes |
| White/Default | Computed nodes (no frequency suffix) |


