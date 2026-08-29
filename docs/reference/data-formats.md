---
title: Data formats
icon: lucide/database
---

# Data formats

conduit reads inputs from files and writes results to disk, and works out the format from
the file extension.

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
CSV/Parquet are for single-site time series. JSON/TOML are for time-invariant scalar
parameters, and are input-only.

The table is [`conduit.formats.FORMATS`](modules/conduit.formats.md), which is where
conduit looks up the reader, the writer, and whether a `[subset]` run can write the
format.

## Spatial handling

conduit handles three spatial layouts automatically:

- **Gridded (NetCDF/Zarr with a CRS).** Spatial dimensions (`x`/`y` or `lat`/`lon`) with
  a CRS are stacked into a single `pixel` dimension — each grid cell becomes one pixel.
  This path uses the optional `geo` extra and activates only when CRS metadata is
  present. See [`conduit.gridded`](modules/conduit.gridded/io.md).
- **Pre-stacked.** Data that already has a `pixel` dimension is used as-is.
- **Single-point (CSV/Parquet/JSON/TOML).** Flat files are treated as one site; a size-1
  dimension with a single coordinate (`0`) is added automatically — named by the
  top-level [`point_dim`](configuration.md#point-dimension) key, `pixel` by default.
  Tables become `(time, point_dim)` and scalar files `(point_dim,)`. Set `point_dim` to
  match whatever a non-gridded pipeline blocks or subsets over.

Grid coordinate nodes (`latitude`, `longitude`) are computed from the CRS when a gridded
input is loaded.

## Temporal handling

Time-varying NetCDF/Zarr inputs carry a dimension with a datetime coordinate, and data
variables named **without** any frequency suffix (e.g. `temperature`, not
`temperature_daily`) — conduit appends the suffix from the section label when building
node names (see [Configuration › inputs](configuration.md#inputs)).

conduit finds the time dimension by looking for a datetime-like coordinate (NumPy
`datetime64` or a cftime index), so the dimension can have any name. An input dataset may
carry **at most one** such dimension; a second datetime axis is rejected at load.
For CSV/Parquet, the first column must be a parseable date and is used as the time index.

Section labels only supply a node-name suffix: calling a section `daily` gives its node
names the `_daily` suffix, and that is all it does.

Frequency is validated wherever it is **declared**. Two mechanisms cover it:

- a consumer declaring `Freq("7D")` on its input (or a `[[node]]` with `freq = "7D"` on
  its output) — validated per node by the
  [contract check](../guides/nodes/contracts.md), at build time and in `--dry-run`;
- the [`time_equal` / `time_subset` checks](configuration.md#validation)
  — validated across whole input datasets.

## Units metadata

Set a CF-style `units` attribute on your input variables so conduit can validate and
convert them against the contracts your nodes declare (see
[Declaring contracts](../guides/nodes/contracts.md)). A missing or unparseable
`units` attribute cannot be validated, so it falls to the active
[`[annotations]` policy](configuration.md#annotations).

## Output provenance

`conduit run` stamps the config used to produce an output, its full text and SHA-256,
into the output's `attrs` (`conduit_config`, `conduit_config_sha256`), so every result
file records the run that made it.
