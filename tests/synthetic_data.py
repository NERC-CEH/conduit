"""Synthetic input-data generation for the test suite.

A small, self-contained replacement for the old ``conduit.setup_utils``
generator. It writes four gridded NetCDF files (daily / weekly / monthly /
static) on a regular lat/lon grid, using a domain-neutral geophysical
vocabulary and a handful of explicit value shapes (gaussian, non-negative,
bounded [0, 1], integer).

Unlike the generator it replaces, this builds the datasets with plain
numpy/xarray rather than routing through the Hamilton DAG. The only conduit
code it reuses is ``unstack_if_gridded`` from the IO layer, so the on-disk
grid/CRS layout matches exactly what ``conduit.io.load_inputs`` reads back.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from conduit.gridded.io import unstack_if_gridded

# Value "kinds" and how they map to noise. These reproduce the value contracts
# the old name-heuristic generator provided, but assigned explicitly per var.
#   gaussian  -> unconstrained
#   positive  -> >= 0
#   bounded   -> within [0, 1]
#   integer   -> whole-number valued (still float dtype)
DAILY_VARS: dict[str, str] = {
    "temperature": "gaussian",
    "precipitation": "positive",
    "humidity": "bounded",
    "wind_speed": "positive",
    "cloud_fraction": "bounded",
}
WEEKLY_VARS: dict[str, str] = {
    "pressure": "positive",
    "radiation": "positive",
    "albedo": "bounded",
    "snow_depth": "positive",
    "aerosol": "gaussian",
}
MONTHLY_VARS: dict[str, str] = {
    "dummy_variable": "gaussian",
}
STATIC_VARS: dict[str, str] = {
    "elevation": "gaussian",
    "surface_type": "integer",
    "roughness": "positive",
    "soil_moisture": "bounded",
    "land_fraction": "bounded",
}

START_DATE = "2020-01-01"


def _noise(kind: str, shape: tuple[int, ...]) -> np.ndarray:
    """Random values for the given value ``kind``."""
    if kind == "bounded":
        return np.clip(np.random.normal(0.5, 0.2, shape), 0.0, 1.0)
    if kind == "positive":
        return np.abs(np.random.normal(1.0, 0.5, shape))
    if kind == "integer":
        return np.random.randint(1, 4, shape).astype(float)
    return np.random.normal(0.0, 1.0, shape)


def _pixel_index(n_lat: int, n_lon: int) -> pd.MultiIndex:
    """Stacked ``pixel`` MultiIndex from the lat/lon cartesian product."""
    lat = np.linspace(50.0, 54.0, n_lat)
    lon = np.linspace(-4.0, 2.0, n_lon)
    lat_grid, lon_grid = np.meshgrid(lat, lon, indexing="ij")
    return pd.MultiIndex.from_arrays(
        [lat_grid.ravel(), lon_grid.ravel()], names=["y", "x"]
    )


def _temporal_ds(
    vars_: dict[str, str],
    time: np.ndarray | pd.DatetimeIndex,
    pixel: pd.MultiIndex,
) -> xr.Dataset:
    shape = (len(time), len(pixel))
    coords = {"time": np.asarray(time), "pixel": pixel}
    data = {
        name: xr.DataArray(_noise(kind, shape), dims=["time", "pixel"], coords=coords)
        for name, kind in vars_.items()
    }
    return xr.Dataset(data)


def _static_ds(vars_: dict[str, str], pixel: pd.MultiIndex) -> xr.Dataset:
    shape = (len(pixel),)
    coords = {"pixel": pixel}
    data = {
        name: xr.DataArray(_noise(kind, shape), dims=["pixel"], coords=coords)
        for name, kind in vars_.items()
    }
    return xr.Dataset(data)


def _save(ds: xr.Dataset, path: str) -> None:
    ds = unstack_if_gridded(ds)
    ds.attrs["crs"] = "EPSG:4326"
    ds.to_netcdf(path, engine="netcdf4")


def write_synthetic_inputs(
    paths: dict[str, str],
    grid: tuple[int, int] = (2, 2),
    n_days: int = 365,
    seed: int = 42,
) -> None:
    """Write synthetic ``daily``/``weekly``/``monthly``/``static`` NetCDF files.

    Parameters
    ----------
    paths
        Mapping of group name (``"daily"``, ``"weekly"``, ``"monthly"``,
        ``"static"``) to the output ``.nc`` file path.
    grid
        ``(n_lat, n_lon)``; the product is the number of pixels.
    n_days
        Length of the daily time axis (from ``2020-01-01``).
    seed
        Seed for reproducibility.
    """
    np.random.seed(seed)
    n_lat, n_lon = grid
    pixel = _pixel_index(n_lat, n_lon)

    # Derive the coarse time axes by resampling the daily index with the same
    # offsets conduit uses (RESAMPLE_FREQ_MAP: daily->weekly "7D", daily->monthly
    # "1ME"), so the loader's temporal-alignment check accepts them as valid
    # resample-period labels.
    daily_time = pd.date_range(START_DATE, periods=n_days, freq="D")
    _daily_marker = pd.Series(0, index=daily_time)
    weekly_time = _daily_marker.resample("7D").mean().index
    monthly_time = _daily_marker.resample("1ME").mean().index

    _save(_temporal_ds(DAILY_VARS, daily_time, pixel), paths["daily"])
    _save(_temporal_ds(WEEKLY_VARS, weekly_time, pixel), paths["weekly"])
    _save(_temporal_ds(MONTHLY_VARS, monthly_time, pixel), paths["monthly"])
    _save(_static_ds(STATIC_VARS, pixel), paths["static"])
