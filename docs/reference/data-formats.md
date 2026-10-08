---
title: Data formats
icon: lucide/database
---

# Data formats

conduit picks a file's format from its extension.

## Supported formats

| Extension | Format | Loader | Output? | `[subset]`? |
|-----------|--------|--------|---------|-------------|
| `.nc`, `.netcdf` | NetCDF | `xarray` + `netcdf4` engine | ✅ | ✅ (one file per part) |
| `.zarr` | Zarr store | `xarray` + `zarr` engine | ✅ | ✅ (regions of a shared store) |
| `.csv` | CSV (first column = date index) | `pandas.read_csv` | ✅ | ❌ |
| `.parquet`, `.pq` | Parquet | `pandas.read_parquet` | ✅ | ❌ |
| `.json` | JSON (key → scalar mapping) | `json.load` | ❌ input only | ❌ |
| `.toml` | TOML (key → scalar mapping) | `tomllib.load` | ❌ input only | ❌ |

NetCDF and Zarr are the primary formats for N-dimensional (gridded or multi-point) data.
CSV/Parquet are for single-site time series.
JSON/TOML are for time-invariant scalar parameters, and are input-only.

The table is defined in [`conduit.formats.FORMATS`](modules/conduit.formats.md).

## Spatial handling

conduit handles three spatial layouts automatically:

- **Gridded (NetCDF/Zarr with a CRS).** Spatial dimensions (`x`/`y` or `lat`/`lon`) with a CRS are stacked into a single `pixel` dimension — each grid cell becomes one pixel.
  This path uses the optional `geo` extra and activates only when CRS metadata is present.
  See [`conduit.gridded`](modules/conduit.gridded/io.md).
- **Pre-stacked.** Data that already has a `pixel` dimension is used as-is.
- **Single-point (CSV/Parquet/JSON/TOML).** Flat files are treated as one site; a size-1 dimension with a single coordinate (`0`) is added automatically — named by the top-level [`point_dim`](configuration.md#point-dimension) key, `pixel` by default.
  Tables become `(time, point_dim)` and scalar files `(point_dim,)`.
  Set `point_dim` to match whatever a non-gridded pipeline blocks or subsets over.

Grid coordinate nodes (`latitude`, `longitude`) are computed from the CRS when a gridded input is loaded.

## Temporal handling

conduit finds the time dimension by its datetime-like coordinate (NumPy `datetime64` or a cftime index), so the dimension can have any name.
An input may have at most one such dimension.
For CSV/Parquet, the first column must be a parseable date and becomes the time index.

File variables are named without a frequency suffix (`temperature`, not `temperature_daily`); conduit appends the section's suffix to make the [node name](configuration.md#inputs), and infers nothing else from it.
Frequency is checked only where it is declared: by a `Freq` [contract](../guides/nodes/contracts.md), or across whole inputs by the [`time_equal` / `time_subset` checks](configuration.md#validation).

## Units metadata

Give input variables a CF-style `units` attribute so conduit can validate and convert them against your nodes' [contracts](../guides/nodes/contracts.md).
A missing or unparseable `units` attribute is handled by the [`[annotations]` policy](configuration.md#annotations).

## Output provenance

A run from a config file stamps the config's full text and SHA-256 into each output's `attrs` (`conduit_config`, `conduit_config_sha256`), so every result records the pipeline that made it.
A run from an in-memory `ParsedConfig` has no text to stamp, so its outputs carry neither.
