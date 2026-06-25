---
title: P-model
icon: lucide/leaf
---

# P-model


## Overview

The P-model is an optimality-based light use efficiency model for simulating ecosystem gross primary production (GPP).[^stocker2020] 
Rather than assigning fixed trait values to plant functional types (PFTs), it predicts how plants continuously acclimate to their environment based on eco-evolutionary optimality theory – the idea that plants adapt to maximise resource use efficiency.[^prentice2014]
For a broader overview of the model's challenges and future directions, see the University of Reading LEMONTREE blog.[^lemontree2025]

The model rests on three foundational hypotheses:

**Least-Cost Hypothesis** – Plants balance water loss during transpiration against carbon fixation capacity to minimise total cost. 
This predicts how the ratio of leaf-internal to ambient CO₂ (χ) varies with environment: χ decreases in dry air (conserving water), increases in warm conditions (water transport becomes cheaper due to lower viscosity), and decreases at high altitude (lower O₂ makes photosynthesis cheaper). [^prentice2014]

**Coordination Hypothesis** – Plants adjust their photosynthetic capacity (Vcmax) to fully utilise available light, avoiding waste. 
This yields a simple proportionality between photosynthetic capacity (at growth temperature) and incident light intensity.

**Cost-Benefit Hypothesis** – Leaves balance the cost of maintaining maximum electron transport rate (Jmax) against the benefit of electron-transport-limited photosynthesis, predicting the Jmax:Vcmax ratio. [^wang2017]

Together, these hypotheses allow the P-model to predict GPP across diverse ecosystems without biome-specific calibration, using only environmental drivers (light, temperature, CO₂, vapour pressure deficit, soil moisture) and fAPAR.

We wrap the existing [NumPy-based `pyrealm` implementation](https://github.com/ImperialCollegeLondon/pyrealm) of the P-model. 
See the [pyrealm P-model documentation](https://pyrealm.readthedocs.io/en/latest/users/pmodel/module_overview.html) for further details.

## Theory

The P-model builds on the Farquhar–von Caemmerer–Berry (FvCB) model of C3 photosynthesis, which describes the instantaneous response of photosynthesis to environmental conditions. 
The FvCB model expresses the net CO₂ assimilation rate $A$ as the minimum of two limiting rates:

$$A = \min(W_c, W_j) - R_d$$

where $W_c$ is the Rubisco-limited rate, $W_j$ is the electron-transport-limited rate, and $R_d$ is dark respiration.

### Key quantities

The FvCB model depends on several quantities:

- **$\Gamma^*$** – the photorespiratory CO₂ compensation point, which varies predictably with temperature and O₂ partial pressure
- **$K$** – the effective Michaelis–Menten coefficient of Rubisco, also temperature- and O₂-dependent
- **$\phi_0$** – the maximum light-use efficiency of photosynthesis (theoretical maximum ≈ 0.125, i.e., at least 8 photons per fixed carbon atom)

Three quantities are treated as unknowns that plants optimise:

- **$V_{\text{cmax}}$** – maximum CO₂ fixation capacity (Rubisco activity)
- **$J_{\text{max}}$** – maximum electron transport capacity
- **$\chi = c_i / c_a$** – the ratio of leaf-internal to ambient CO₂

### Optimal $\chi$ (Least-Cost Hypothesis)

The least-cost hypothesis yields an expression for optimal $\chi$ that depends on temperature, vapour pressure deficit $D$, atmospheric pressure $p$, and the relative viscosity of water $\eta^*$:

$$\chi = \frac{\Gamma^*}{c_a} + \left(1 - \frac{\Gamma^*}{c_a}\right) \frac{\xi}{\xi + \sqrt{D \cdot \eta^*}}$$

where $\xi$ is a cost factor that depends on $p$ and $\eta^*$. 
This formulation captures the observed responses: $\chi$ decreases with increasing VPD, increases with temperature (via $\eta^*$), and decreases with altitude (via $p$).

### Light use efficiency

Under the coordination hypothesis, $V_{\text{cmax}}$ is set so that $W_c = W_j$ at typical light levels. 
Combined with the optimal $\chi$, this leads to a prediction of light use efficiency (LUE, denoted $\text{LUE}$ or $m$):

$$\text{LUE} = \frac{A}{\text{PPFD} \cdot f_{\text{APAR}}}$$

where PPFD is photosynthetic photon flux density and $f_{\text{APAR}}$ is the fraction of absorbed PAR. 
GPP is then:

$$\text{GPP} = \text{LUE} \cdot \text{PPFD} \cdot f_{\text{APAR}}$$

### Soil moisture stress

The P-model includes a soil moisture stress factor $\beta(\theta)$ that reduces GPP under dry conditions.
The implementation in `pyrealm` uses the soil moisture parameter $\theta$ (volumetric water content) to modulate both $\chi$ and LUE.

### Method options

The implementation supports several methodological choices:

| Parameter | Options | Description |
|-----------|---------|-------------|
| `method_optchi` | `prentice14` (default), `lavergne20_c3`, `lavergne20_c4` | Formulation for optimal $\chi$ |
| `method_jmaxlim` | `wang17` (default), `none` | Whether to apply Jmax limitation |
| `method_kphio` | `temperature` (default), `sandoval`, `constant` | Temperature dependence of $\phi_0$ |
| `method_arrhenius` | `simple` (default), `heskel` | Arrhenius temperature scaling |

## Usage

### Configuration

The P-model is configured in your TOML config file:

```toml
[models.pmodel]
method_kphio = "sandoval"
method_optchi = "lavergne20_c3"
```

All method parameters are optional and default to `("prentice14", "wang17", "temperature", "simple")`.

### Required inputs

The P-model requires the following weekly `DataArray` inputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `temperature_weekly` | °C | Air temperature |
| `vpd_weekly` | Pa | Vapour pressure deficit |
| `co2_weekly` | ppm | Atmospheric CO₂ concentration |
| `pressure_weekly` | Pa | Atmospheric pressure |
| `fapar_weekly` | dimensionless (0–1) | Fraction of absorbed PAR |
| `ppfd_weekly` | μmol m⁻² s⁻¹ | Photosynthetic photon flux density |
| `soil_moisture_weekly` | mm | Soil moisture content |
| `mean_growth_temperature_weekly` | °C | Mean temperature on growing days (T > 0°C) |
| `aridity_index_weekly` | dimensionless | Aridity index |

Helper functions are provided to derive `mean_growth_temperature_weekly` from daily temperature and `aridity_index_daily` from AET and precipitation.

### Outputs

The P-model returns three weekly `DataArray` outputs:

| Variable | Units | Description |
|----------|-------|-------------|
| `gpp_weekly` | gC m⁻² day⁻¹ | Gross primary productivity |
| `lue_weekly` | gC MJ⁻¹ PAR | Light use efficiency |
| `iwue_weekly` | Pa | Intrinsic water use efficiency |

### Python API

See the [API documentation](../api/satterc.dag/pmodel.md) for full function signatures and parameter details.

## References

[^stocker2020]: Stocker, B. D., Wang, H., Smith, N. G., Harrison, S. P., Keenan, T. F., Sandoval, D., Davis, T., and Prentice, I. C.: P-model v1.0: an optimality-based light use efficiency model for simulating ecosystem gross primary production, Geosci. Model Dev., 13, 1545–1581, https://doi.org/10.5194/gmd-13-1545-2020, 2020.

[^prentice2014]: Prentice, I. C., Dong, N., Gleason, S. M., Maire, V., and Wright, I. J.: Balancing the costs of carbon gain and water transport: testing a new theoretical framework for plant functional ecology, Ecol. Lett., 17, 82–91, https://doi.org/10.1111/ele.12211, 2014.

[^lemontree2025]: Sanders, N. (ed.): The P model: challenges we face and plan to address, University of Reading LEMONTREE blog, https://research.reading.ac.uk/lemontree/the-p-model-challenges-we-face-and-plan-to-address/, 2025.

[^wang2017]: Wang, H., Prentice, I. C., Keenan, T. F., Davis, T. W., Wright, I. J., Cornwell, W. K., Breon, F. M., Atkin, O. K., and Dong, N.: Towards a universal model for carbon dioxide uptake by plants, Nat. Plants, 3, 734–741, https://doi.org/10.1038/s41477-017-0006-x, 2017.

[^bloomfield2023]: Bloomfield, K. J., et al.: Environmental responses of light use efficiency from the P-model and FLUXNET sites, Global Change Biology, 2023.

[^mengoli2025]: Mengoli, G., et al.: Breakpoint model of water stress in the P-model, Global Change Biology, in press, 2025.

