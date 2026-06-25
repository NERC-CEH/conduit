---
title: RothC
icon: lucide/worm
---

# Rothamsted Carbon model (RothC)


## Overview

RothC is a widely-used model for simulating the turnover of soil organic carbon (SOC) in non-waterlogged soils.[^jenkinson1990] It splits SOC into five distinct compartments – four active and one inert – and accounts for soil type (clay content), temperature, moisture, and plant cover to calculate decay rates.

The five pools are:

| Pool | Name | Description |
|------|------|-------------|
| DPM | Decomposable Plant Material | Easily decomposed organic matter |
| RPM | Resistant Plant Material | More slowly decomposed organic matter |
| BIO | Microbial Biomass | Living microbial biomass |
| HUM | Humified Organic Matter | Stable humus |
| IOM | Inert Organic Matter | Chemically inert, does not decompose |

We forked the Python implementation from [Rothamsted Research](https://github.com/Rothamsted-Models/RothC_Py/), repackaged it for pip installation, and achieved a ~20× speedup. Our fork is available at [github.com/SatTerC/RothC_Py](https://github.com/SatTerC/RothC_Py).

## Theory

Carbon turnover follows first-order kinetics, where each active pool $k$ evolves according to:

$$
\frac{dC_k}{dt} = I_k - k_k \cdot C_k
$$

where $C_k$ is the carbon content of pool $k$, $I_k$ is the carbon input to that pool, and $k_k$ is the decomposition rate constant, modified by temperature, moisture, and soil cover factors.

The decomposition rates are scaled by:

- **Temperature rate modifier** – increases with temperature
- **Moisture rate modifier** – depends on the ratio of rainfall to evaporation
- **Soil cover factor** – reduces decomposition when soil is covered by vegetation

### Spin-up

RothC requires initial pool sizes to begin simulation. A spin-up phase runs the model over repeated climate cycles until the pools reach equilibrium, providing consistent initial conditions.

For full model details, see:

- [SatTerC RothC_Py documentation](https://satterc.github.io/RothC_Py/science.html)
- [Original model description paper](https://github.com/Rothamsted-Models/RothC_Py/blob/main/RothC_description.pdf) (Coleman, Prout and Milne, Rothamsted Research)

## Usage

### Configuration

RothC is configured in your TOML config file:

```toml
[models.rothc]
n_years_spinup = 1
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_years_spinup` | 1 | Number of years of climate data to use for model spin-up |

### Required inputs

RothC requires the following monthly `DataArray` inputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `temperature_monthly` | °C | Monthly mean air temperature |
| `precipitation_monthly` | mm | Monthly precipitation |
| `evaporation_monthly` | mm | Monthly open pan evaporation |
| `plant_cover_monthly` | dimensionless (0–1) | Monthly plant cover (boolean: covered or bare) |
| `dpm_rpm_ratio_monthly` | dimensionless | Ratio of decomposable to resistant plant material |
| `soil_carbon_input_monthly` | tC·ha⁻¹ | Carbon input from litter for the month |
| `farmyard_manure_input_monthly` | tC·ha⁻¹ | Farmyard manure input for the month |

And the following static `DataArray` inputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `clay_content` | % | Soil clay content |
| `soil_depth` | cm | Soil depth |
| `inert_organic_matter` | tC·ha⁻¹ | Initial inert organic matter |

### Outputs

RothC returns six monthly `DataArray` outputs, all in tC·ha⁻¹:

| Variable | Units | Description |
|----------|-------|-------------|
| `decomposable_plant_material_monthly` | tC·ha⁻¹ | DPM pool |
| `resistant_plant_material_monthly` | tC·ha⁻¹ | RPM pool |
| `microbial_biomass_monthly` | tC·ha⁻¹ | Microbial biomass (BIO) pool |
| `humified_organic_matter_monthly` | tC·ha⁻¹ | HUM pool |
| `soil_organic_carbon_monthly` | tC·ha⁻¹ | Total soil organic carbon (sum of all pools) |
| `heterotrophic_respiration_monthly` | tC·ha⁻¹ | CO₂ released by microbial decomposition during the month |

### Python API

See the [API documentation](../api/satterc.dag/rothc.md) for full function signatures and parameter details.

## References

[^jenkinson1990]: Jenkinson, D. S.: The Turnover of Organic Carbon and Nitrogen in Soil, Philosophical Transactions of the Royal Society of London, Series B: Biological Sciences, 329, 361–368, 1990.

[^jenkinson1987]: Jenkinson, D. S., et al.: Modelling the turnover of organic matter in long-term experiments at Rothamsted, INTECOL Bulletin, 15, 1–8, 1987.

[^jenkinson1977]: Jenkinson, D. S., and Rayner, J. H.: Turnover of soil organic matter in some of the Rothamsted classical experiments, Soil Science, 123, 298–305, 1977.

[^bolinder2007]: Bolinder, M. A., et al.: An approach for estimating net primary productivity and annual carbon inputs to soil for common agricultural crops in Canada, Agriculture, Ecosystems & Environment, 118, 29–42, 2007.

[^farina2013]: Farina, R., et al.: Modification of the RothC model for simulations of soil organic C dynamics in dryland regions, Geoderma, 200, 18–30, 2013.

[^giongo2020]: Giongo, V., et al.: Optimizing multifunctional agroecosystems in irrigated dryland agriculture to restore soil carbon – Experiments and modelling, Science of the Total Environment, 725, 2020.
