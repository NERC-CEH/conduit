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

Time-varying NetCDF/Zarr inputs carry a dimension with a datetime coordinate, and data
variables named **without** any frequency suffix (e.g. `temperature`, not
`temperature_daily`) — conduit appends the suffix from the section label when building
node names (see [Configuration › inputs](configuration.md#inputs)).

The time dimension is **detected, not assumed**: any dimension whose coordinate is
datetime-like (NumPy `datetime64` or a cftime index) counts, so it need not be called
`time`. An input dataset may carry **at most one** such dimension — a second datetime
axis makes "the time dimension" ambiguous and is rejected at load. For CSV/Parquet, the
first column must be a parseable date and is used as the time index.

Section labels are **inert**: calling a section `daily` gives its node names the
`_daily` suffix and nothing else — no frequency is inferred or enforced from the name.

Frequency is validated where it is **declared**, not where it is named. Two independent
mechanisms cover it:

- a consumer declaring `Freq("7D")` on its input (or a `[[node]]` with `freq = "7D"` on
  its output) — validated per node by the
  [contract check](../concepts/contracts.md), at build time and in `--dry-run`;
- the [`time_aligned` / `time_equal` / `time_subset` checks](configuration.md#validation)
  — validated across whole input datasets.

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
