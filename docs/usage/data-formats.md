---
title: Data Formats
icon: lucide/database
---

# Data Formats and Requirements

breadboard reads input data from files and writes results to disk.
This page covers supported formats, spatial handling, and the variables each model requires.

## Supported File Formats

Format detection is automatic — the file extension determines how data is loaded.

### Time-Series Data (Daily, Weekly, Monthly)

| Extension | Format | Loader |
|-----------|--------|--------|
| `.nc`, `.netcdf` | NetCDF | `xarray` + `netcdf4` engine |
| `.zarr` or directory | Zarr store | `xarray` + `zarr` engine |
| `.csv` | CSV (first column = date) | `pandas.read_csv` |
| `.parquet`, `.pq` | Parquet | `pandas.read_parquet` |

### Static (Time-Invariant) Data

| Extension | Format | Loader |
|-----------|--------|--------|
| `.nc`, `.netcdf` | NetCDF | `xarray` + `netcdf4` engine |
| `.zarr` or directory | Zarr store | `xarray` + `zarr` engine |
| `.json` | JSON (key → scalar mapping) | `json.load` |
| `.toml` | TOML (key → scalar mapping) | `tomllib.load` |

## Spatial Handling

breadboard handles three spatial configurations automatically:

### 2D Gridded Data (NetCDF/Zarr with CRS)

If your input file has spatial dimensions (`x`/`y` or `lat`/`lon`) with a CRS, breadboard stacks them into a single `pixel` dimension. Each grid cell becomes one pixel in the pipeline.

### Pre-Stacked Multi-Point Data

If your data already has a `pixel` dimension, it is used as-is.

### Single-Point Data (CSV/Parquet/JSON)

Flat files are treated as single-site data. A `pixel` dimension with a single coordinate (0) is added automatically.

## Temporal Requirements

Each frequency has a datetime index validation:

| Frequency | Expected Index | Validation |
|-----------|---------------|------------|
| Daily | `pd.DatetimeIndex` with freq `"D"` | Strict daily frequency check |
| Weekly | `pd.DatetimeIndex` with freq `"W"` or `"7D"` | Weekly prefix check |
| Monthly | `pd.DatetimeIndex` with freq `"ME"` or `"MS"` | Month-end or month-start check |

For CSV/Parquet files, the first column must be a parseable date and is used as the time index.

## NetCDF/Zarr Data Structure

For gridded or multi-point data, files should have:

- A `time` dimension with a datetime coordinate
- Spatial dimensions (`x`/`y` or `lat`/`lon`) with a CRS attribute, **or** a `pixel` dimension
- Data variables named without frequency suffixes (e.g., `temperature`, not `temperature_daily`)

breadboard appends the frequency suffix internally. For example, a variable `temperature` in a daily input file becomes the node `temperature_daily` in the DAG.

## Model Data Requirements

Each model requires specific input variables and produces specific outputs.
Variables marked with a suffix (`_daily`, `_weekly`, `_monthly`) indicate the temporal resolution.
Static variables have no suffix.

### SPLASH

| Category | Variable | Description |
|----------|----------|-------------|
| **Inputs (daily)** | `sunshine_fraction` | Fraction of daylight hours that are sunny (0–1) |
| | `temperature` | Air temperature (°C) |
| | `precipitation` | Precipitation (mm/day) |
| **Inputs (static)** | `elevation` | Elevation (m) |
| | `latitude` | Latitude (degrees) — or use `[grid]` section |
| | `max_soil_moisture` | Maximum soil moisture capacity (mm) |
| **Parameters** | `soil_moisture_init_max_iter` | Max iterations for initial soil moisture (default: 10) |
| | `soil_moisture_init_max_diff` | Max diff for soil moisture convergence (default: 1.0) |
| **Outputs (daily)** | `actual_evapotranspiration` | Actual evapotranspiration (mm/day) |
| | `soil_moisture` | Soil moisture content (mm) |
| | `runoff` | Runoff (mm) |

### P-Model

| Category | Variable | Description |
|----------|----------|-------------|
| **Inputs (weekly)** | `temperature` | Air temperature (°C) |
| | `vpd` | Vapor pressure deficit (Pa) |
| | `co2` | Atmospheric CO₂ (ppm) |
| | `pressure` | Atmospheric pressure (Pa) |
| | `fapar` | Fraction of absorbed PAR (0–1) |
| | `ppfd` | Photosynthetic photon flux density (μmol/m²/s) |
| **Derived (daily→weekly)** | `aridity_index` | AET/precipitation ratio — requires SPLASH output resampled to weekly |
| | `soil_moisture` | From SPLASH, resampled to weekly |
| | `mean_growth_temperature` | Mean temperature on growing degree days (computed internally) |
| **Parameters** | `method_optchi` | Optimal χ method (default: `"prentice14"`) |
| | `method_jmaxlim` | Jmax limitation method (default: `"wang17"`) |
| | `method_kphio` | Quantum yield method (default: `"temperature"`) |
| | `method_arrhenius` | Arrhenius scaling method (default: `"simple"`) |
| **Outputs (weekly)** | `gpp` | Gross primary productivity (gC/m²/day) |
| | `lue` | Light use efficiency (gC/MJ PAR) |
| | `iwue` | Intrinsic water use efficiency (Pa) |

### SGAM

| Category | Variable | Description |
|----------|----------|-------------|
| **Inputs (weekly)** | `temperature` | Air temperature (°C) |
| | `gpp` | Gross primary productivity (from P-Model) |
| | `soil_moisture` | Soil moisture (from SPLASH) |
| | `vpd` | Vapor pressure deficit (Pa) |
| | `lue` | Light use efficiency (from P-Model) |
| | `iwue` | Intrinsic water use efficiency (from P-Model) |
| **Inputs (static)** | `plant_type` | Plant functional type as integer (0=tree, 1=grass, 2=shrub, 3=crop) |
| | `leaf_pool_init` | Initial leaf pool size |
| | `stem_pool_init` | Initial stem pool size |
| | `root_pool_init` | Initial root pool size |
| | `latitude` | Latitude (degrees) — for hemisphere determination |
| **Optional (static)** | `litter_pool_init` | Initial litter pool (default: 0.0) |
| | `removed_init` | Initial removed-carbon pool (default: 0.0) |
| **Parameters** | `use_dynamic_allocation` | Variable allocation fractions (default: `true`) |
| | `strict_mass_balance` | Raise on mass balance violation (default: `false`) |
| **Outputs (weekly)** | `leaf_pool`, `stem_pool`, `root_pool`, `litter_pool` | Carbon pools |
| | `npp_leaf`, `npp_stem`, `npp_root` | Net primary production fluxes |
| | `cue`, `drought_modifier`, `allocation_*` | Diagnostics |

### RothC

| Category | Variable | Description |
|----------|----------|-------------|
| **Inputs (monthly)** | `temperature` | Monthly mean temperature (°C) |
| | `precipitation` | Monthly precipitation (mm) |
| **Derived (from SPLASH)** | `evaporation` | Monthly actual evapotranspiration (mm) |
| **Derived (from SGAM)** | `soil_carbon_input` | From `litter_pool`, resampled to monthly |
| **Inputs (static)** | `clay_content` | Clay content (%) |
| | `soil_depth` | Soil depth (cm) |
| | `organic_carbon_stocks` | Organic carbon stocks (tC/ha) — used to compute inert organic matter |
| **Computed internally** | `plant_cover` | PFT-dependent: tree/grass/shrub always 1; crops bare in winter (NH: Nov–Feb, SH: May–Aug) |
| | `dpm_rpm_ratio` | PFT-dependent (configurable): tree=0.25, grass=1.44, shrub=0.67, crop=1.44 |
| | `farmyard_manure_input` | Set to zeros (future: SGAM grazing C flux for grass) |
| | `inert_organic_matter` | Computed from `organic_carbon_stocks` |
| **Parameters** | `n_years_spinup` | Years for model spin-up (default: 1) |
| | `dpm_rpm_ratio_tree` | DPM/RPM ratio for tree (default: 0.25) |
| | `dpm_rpm_ratio_grass` | DPM/RPM ratio for grass (default: 1.44) |
| | `dpm_rpm_ratio_shrub` | DPM/RPM ratio for shrub (default: 0.67) |
| | `dpm_rpm_ratio_crop` | DPM/RPM ratio for crop (default: 1.44) |
| **Outputs (monthly)** | `decomposable_plant_material` | DPM pool (tC/ha) |
| | `resistant_plant_material` | RPM pool (tC/ha) |
| | `microbial_biomass` | BIO pool (tC/ha) |
| | `humified_organic_matter` | HUM pool (tC/ha) |
| | `soil_organic_carbon` | Total SOC (tC/ha) |

## Typical Input Configurations by Model Chain

### SPLASH Only

```toml
[inputs.daily]
path = "data/daily.nc"
vars = ["precipitation", "sunshine_fraction", "temperature"]

[inputs.static]
path = "data/static.nc"
vars = ["elevation", "max_soil_moisture"]
```

### SPLASH + P-Model

```toml
[inputs.daily]
path = "data/daily.nc"
vars = ["precipitation", "sunshine_fraction", "temperature"]

[inputs.weekly]
path = "data/weekly.nc"
vars = ["co2", "fapar", "ppfd", "pressure", "vpd"]

[inputs.static]
path = "data/static.nc"
vars = ["elevation", "max_soil_moisture"]

[[resample]]
from_freq = "daily"
to_freq = "weekly"
vars = ["temperature", "precipitation"]
```

### Full Chain (SPLASH + P-Model + SGAM + RothC)

```toml
[inputs.daily]
path = "data/daily.nc"
vars = ["precipitation", "sunshine_fraction", "temperature"]

[inputs.weekly]
path = "data/weekly.nc"
vars = ["co2", "fapar", "ppfd", "pressure", "vpd"]

[inputs.static]
path = "data/static.nc"
vars = [
  "elevation", "clay_content", "soil_depth",
  "max_soil_moisture", "plant_type",
  "leaf_pool_init", "stem_pool_init", "root_pool_init",
  "organic_carbon_stocks",
]

[[resample]]
from_freq = "daily"
to_freq = "weekly"
vars = ["temperature", "precipitation"]

[[resample]]
from_freq = "weekly"
to_freq = "monthly"
vars = ["litter_pool"]
```

/// admonition | Tip
    type: tip

Use `breadboard setup` to generate a config with the correct variables for your selected models automatically.
///
