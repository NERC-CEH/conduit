"""Generate synthetic daily input data."""

import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray


def _generate_seasonal_cycle(
    n_days: int, amplitude: float, phase_shift: float, baseline: float
) -> NDArray[np.float64]:
    """Generate a sinusoidal seasonal cycle over n_days."""
    t = np.arange(n_days)
    return baseline + amplitude * np.sin(2 * np.pi * t / 365.25 + phase_shift)


def _ar1_noise(
    n_days: int,
    n_pixels: int,
    phi: float = 0.7,
    sigma: float = 1.0,
) -> NDArray[np.float64]:
    """AR(1) noise: noise[t] = phi * noise[t-1] + innovation[t].

    The innovation variance is scaled so the stationary marginal std equals sigma.
    Pixels are independent but each has temporal autocorrelation phi.
    """
    innovation_std = sigma * np.sqrt(1.0 - phi**2)
    noise = np.empty((n_days, n_pixels))
    noise[0] = np.random.normal(0.0, sigma, n_pixels)
    for t in range(1, n_days):
        noise[t] = phi * noise[t - 1] + np.random.normal(0.0, innovation_std, n_pixels)
    return noise


def time_coord(n_days: int, start_date: str = "2020-01-01") -> NDArray[np.datetime64]:
    """Create time coordinate."""
    start = np.datetime64(start_date)
    return start + np.arange(n_days)


def temperature_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily air temperature in degrees Celsius."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    lat_vals = np.asarray(pixel_coords.get_level_values("y").values)  # (n_pixels,)
    lon_vals = np.asarray(pixel_coords.get_level_values("x").values)
    lat_effect = (lat_vals - 52.0) * 0.5  # cooler at higher latitudes
    lon_effect = (lon_vals + 1.0) * 0.3  # milder near coast (west)
    baseline = 10.0 + lat_effect + lon_effect  # (n_pixels,)

    seasonal = _generate_seasonal_cycle(n_days, 10.0, -np.pi / 2, 0.0)  # (n_days,)
    noise = _ar1_noise(n_days, n_pixels, phi=0.7, sigma=2.0)  # (n_days, n_pixels)
    data = baseline[np.newaxis, :] + seasonal[:, np.newaxis] + noise

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "degC", "long_name": "air temperature"},
        name="temperature",
    )


def precipitation_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily precipitation in mm d-1."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    lat_vals = np.asarray(pixel_coords.get_level_values("y").values)  # (n_pixels,)
    base_precip = 2.5 + (54.0 - lat_vals) * 0.3  # (n_pixels,)

    seasonal = _generate_seasonal_cycle(n_days, 1.0, 0.0, 0.0)  # (n_days,)
    scale = np.abs(base_precip[np.newaxis, :] + seasonal[:, np.newaxis]) + 0.1
    daily_precip = np.random.exponential(scale)  # (n_days, n_pixels)
    wet_days = np.random.random((n_days, n_pixels)) < 0.6
    data = np.where(wet_days, daily_precip, 0.0)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "mm d-1", "long_name": "precipitation"},
        name="precipitation",
    )


def sunshine_fraction_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily sunshine fraction (0-1)."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    seasonal = _generate_seasonal_cycle(n_days, 0.3, 0.0, 0.5)[
        :, np.newaxis
    ]  # (n_days, 1)
    noise = _ar1_noise(n_days, n_pixels, phi=0.6, sigma=0.12)  # (n_days, n_pixels)
    data = np.clip(seasonal + noise, 0.0, 1.0)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "1", "long_name": "sunshine fraction"},
        name="sunshine_fraction",
    )


def lai_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily Leaf Area Index (dimensionless ratio, m2 m-2)."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    seasonal = _generate_seasonal_cycle(n_days, 2.5, -np.pi / 3, 3.0)[:, np.newaxis]
    noise = np.random.uniform(-0.3, 0.3, (n_days, n_pixels))
    data = np.clip(seasonal + noise, 0.1, 6.0)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "1", "long_name": "leaf area index"},
        name="lai",
    )


def gpp_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
    temperature_daily: xr.DataArray,
) -> xr.DataArray:
    """Daily Gross Primary Productivity (g m-2 d-1)."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    temp_vals = temperature_daily.values  # (n_days, n_pixels)
    seasonal = _generate_seasonal_cycle(n_days, 5.0, -np.pi / 3, 0.0)[:, np.newaxis]
    temp_factor = np.maximum(temp_vals - 5.0, 0.0) / 15.0
    noise = np.random.uniform(-1.0, 1.0, (n_days, n_pixels))
    data = np.maximum(8.0 + seasonal * temp_factor + noise, 0.1)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "g m-2 d-1", "long_name": "gross primary productivity"},
        name="gpp",
    )


def dummy_variable_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily dummy variable (NaN array)."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    return xr.DataArray(
        data=np.full((n_days, n_pixels), np.nan),
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "1", "long_name": "dummy variable"},
        name="dummy_variable",
    )


def co2_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Atmospheric CO2 concentration in ppm."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    baseline = 412.0
    trend = np.linspace(0.0, 5.0, n_days)
    seasonal = _generate_seasonal_cycle(n_days, 3.0, 0.0, 0.0)
    noise = np.random.normal(0.0, 1.0, n_days)
    data_1d = baseline + trend + seasonal + noise
    data = np.broadcast_to(data_1d[:, np.newaxis], (n_days, n_pixels)).copy()

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "ppm", "long_name": "atmospheric CO2 concentration"},
        name="co2",
    )


def fapar_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Fraction of absorbed photosynthetically active radiation (0-1)."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    seasonal = _generate_seasonal_cycle(n_days, 0.25, 0.0, 0.55)[:, np.newaxis]
    noise = np.random.uniform(-0.1, 0.1, (n_days, n_pixels))
    data = np.clip(seasonal + noise, 0.05, 0.95)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "1", "long_name": "fAPAR"},
        name="fapar",
    )


def ppfd_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Photosynthetic photon flux density in umol m-2 s-1."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    day_of_year = np.arange(n_days) % 365.25
    max_ppfd = (1200.0 * np.abs(np.sin(np.pi * day_of_year / 182.6)))[:, np.newaxis]
    cloud_effect = 0.4 + np.random.uniform(0.2, 0.6, (n_days, n_pixels))
    data = max_ppfd * cloud_effect

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={
            "units": "umol m-2 s-1",
            "long_name": "photosynthetic photon flux density",
        },
        name="ppfd",
    )


def pressure_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
    elevation: xr.DataArray,
) -> xr.DataArray:
    """Atmospheric pressure in Pascals."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    elevation_effect = -elevation.values * 10.0  # (n_pixels,)
    seasonal = _generate_seasonal_cycle(n_days, 500.0, 0.0, 0.0)[:, np.newaxis]
    noise = np.random.normal(0.0, 300.0, (n_days, n_pixels))
    data = 101325.0 + elevation_effect[np.newaxis, :] + seasonal + noise

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "Pa", "long_name": "atmospheric pressure"},
        name="pressure",
    )


def vpd_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
    temperature_daily: xr.DataArray,
) -> xr.DataArray:
    """Vapor pressure deficit in Pascals."""
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    temp = temperature_daily.values  # (n_days, n_pixels)
    svp = 610.78 * np.exp(temp / (temp + 237.3) * 17.27)
    rh = np.clip(0.5 + np.random.uniform(-0.2, 0.2, (n_days, n_pixels)), 0.1, 0.95)
    data = np.clip(svp * (1.0 - rh), 50.0, 3000.0)

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "Pa", "long_name": "vapor pressure deficit"},
        name="vpd",
    )


def wind_speed_daily(
    time_coord: NDArray[np.datetime64],
    pixel_coords: pd.MultiIndex,
) -> xr.DataArray:
    """Daily wind speed in m/s.

    Drawn from a Weibull distribution (shape k=2, typical for mid-latitudes)
    with a seasonal scale: stronger in winter, lighter in summer.
    """
    n_days = len(time_coord)
    n_pixels = len(pixel_coords)

    # Seasonal scale: peaks in winter (phase=pi puts max near day 0/365)
    seasonal = _generate_seasonal_cycle(n_days, 1.5, np.pi, 4.0)[:, np.newaxis]
    weibull_shape = 2.0
    data = np.random.weibull(weibull_shape, (n_days, n_pixels)) * seasonal

    return xr.DataArray(
        data=data,
        dims=["time", "pixel"],
        coords={"time": time_coord, "pixel": pixel_coords},
        attrs={"units": "m/s", "long_name": "wind speed"},
        name="wind_speed",
    )
