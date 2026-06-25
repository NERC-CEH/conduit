---
title: Splash
icon: lucide/droplet
---

# SPLASH model


## Overview

SPLASH (Simple Process-led Algorithms for Simulating Habitats) is a water balance model that estimates soil moisture, actual evapotranspiration (AET) and surface water runoff for sites.[^davis2017]

The model takes an initial estimate of soil moisture and then uses time series of precipitation, temperature and cloud cover to estimate how the daily water balance changes with incoming precipitation, condensation and AET. Calculations of AET and condensation are affected by soil moisture, temperature and downwelling solar radiation at the site – this requires that the elevation and latitude of the site are known.

We wrap the existing [NumPy-based `pyrealm` implementation](https://github.com/ImperialCollegeLondon/pyrealm) of SPLASH. 
See the [pyrealm SPLASH documentation](https://pyrealm.readthedocs.io/en/latest/users/splash.html) for further details and as the authoritative source for model theory.

## Theory

The daily water balance equation is:

$$
W_{n[t]} = W_{n[t-1]} + P_{[t]} + C_{[t]} - \textrm{AET}_{[t]},
$$

where:

- $W_{n[t]}$ – current soil moisture (mm)
- $W_{n[t-1]}$ – previous day's soil moisture (mm)
- $P_{[t]}$ – precipitation (mm·d⁻¹)
- $C_{[t]}$ – condensation (mm·d⁻¹)
- $\textrm{AET}_{[t]}$ – actual evapotranspiration (mm·d⁻¹)

The calculated soil moisture is capped at the maximum soil moisture capacity ($W_m$), with excess water allocated to surface water runoff:

$$
\text{if } W_{n[t]} > W_m: \quad W_{n[t]} = W_m, \quad R_{[t]} = W_{n[t]} - W_m
$$

The maximum soil moisture capacity defaults to 150 mm but can be set on a per-site basis.

### Initial soil moisture estimation

SPLASH estimates initial soil moisture by iterating over a full year of climate data until the difference between year-start and year-end soil moisture falls below a specified threshold. This ensures the model starts from a quasi-equilibrium state.

## Usage

### Configuration

SPLASH is configured in your TOML config file:

```toml
[models.splash]
soil_moisture_init_max_iter = 10
soil_moisture_init_max_diff = 1.0
```

Both parameters are optional. The defaults are:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `soil_moisture_init_max_iter` | 10 | Maximum number of one-year iterations for initial soil moisture estimation |
| `soil_moisture_init_max_diff` | 1.0 | Maximum acceptable difference (mm) between year-start and year-end soil moisture |

### Required inputs

SPLASH requires the following daily `DataArray` inputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `sunshine_fraction_daily` | dimensionless (0–1) | Fraction of daylight hours that are sunny |
| `temperature_daily` | °C | Air temperature |
| `precipitation_daily` | mm·d⁻¹ | Precipitation |

And the following static `DataArray` inputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `elevation` | m | Site elevation |
| `latitude` | degrees | Site latitude |
| `max_soil_moisture` | mm | Maximum soil moisture capacity |

### Outputs

SPLASH returns three daily `DataArray` outputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `actual_evapotranspiration_daily` | mm·d⁻¹ | Actual evapotranspiration |
| `soil_moisture_daily` | mm | Soil moisture content |
| `runoff_daily` | mm | Surface water runoff |

### Python API

See the [API documentation](../api/satterc.dag/splash.md) for full function signatures and parameter details.

## References

[^davis2017]: Davis, T. W., Prentice, I. C., Stocker, B. D., Thomas, R. T., Whitley, R. J., Wang, H., Evans, B. J., Gallego-Sala, A. V., Sykes, M. T., and Cramer, W.: Simple process-led algorithms for simulating habitats (SPLASH v.1.0): robust indices of radiation, evapotranspiration and plant-available moisture, Geosci. Model Dev., 10, 689–708, https://doi.org/10.5194/gmd-10-689-2017, 2017.
