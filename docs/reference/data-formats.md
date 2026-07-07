---
title: Data formats
icon: lucide/database
---

# Data formats

conduit reads inputs from files and writes results to disk. Format is detected
automatically from the file extension.

## Supported formats

| Extension | Format | Loader |
|-----------|--------|--------|
| `.nc`, `.netcdf` | NetCDF | `xarray` + `netcdf4` engine |
| `.zarr` | Zarr store | `xarray` + `zarr` engine |
| `.csv` | CSV (first column = date index) | `pandas.read_csv` |
| `.parquet`, `.pq` | Parquet | `pandas.read_parquet` |
| `.json` | JSON (key → scalar mapping) | `json.load` |
| `.toml` | TOML (key → scalar mapping) | `tomllib.load` |

NetCDF and Zarr are the primary formats for N-dimensional (gridded or multi-point) data.
CSV/Parquet are for single-site time series. JSON/TOML are for time-invariant scalar
parameters.

## Spatial handling

conduit handles three spatial layouts automatically:

- **Gridded (NetCDF/Zarr with a CRS).** Spatial dimensions (`x`/`y` or `lat`/`lon`) with
  a CRS are stacked into a single `pixel` dimension — each grid cell becomes one pixel.
  This path uses the optional `geo` extra and activates only when CRS metadata is
  present. See [`conduit.gridded`](../api/conduit.gridded/io.md).
- **Pre-stacked.** Data that already has a `pixel` dimension is used as-is.
- **Single-point (CSV/Parquet/JSON/TOML).** Flat files are treated as one site; a
  `pixel` dimension with a single coordinate (`0`) is added automatically.

Grid coordinate nodes (`latitude`, `longitude`) are computed from the CRS when a gridded
input is loaded.

## Temporal handling

For NetCDF/Zarr inputs, files should carry a `time` dimension with a datetime
coordinate, and data variables named **without** any frequency suffix (e.g.
`temperature`, not `temperature_daily`) — conduit appends the suffix from the section
label when building node names (see [Configuration › inputs](configuration.md#inputs)).

Input sections whose label is a **recognised temporal frequency** (`daily`, `weekly`,
`monthly`) have their time index validated against that frequency:

| Label | Expected frequency |
|-------|--------------------|
| `daily` | one entry per calendar day (`D`) |
| `weekly` | `W` or `7D` |
| `monthly` | month-end (`ME`) or month-start (`MS`) |

Sections with any other label are not frequency-validated — their time index only has to
be a valid `DatetimeIndex`. For CSV/Parquet, the first column must be a parseable date
and is used as the time index.

## Units metadata

Set a CF-style `units` attribute on your input variables so conduit can validate and
convert them against the contracts your nodes declare (see
[Add unit contracts](../get-started/units-and-contracts.md)). A missing or unparseable
`units` attribute cannot be validated, so it follows the active
[`[annotations]` policy](configuration.md#annotations).

## Output provenance

`conduit run` stamps the config used to produce an output — its full text and SHA-256 —
into the output's `attrs` (`conduit_config`, `conduit_config_sha256`), so every result
file is a self-describing, reproducible record of the run that made it.
