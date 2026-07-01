"""Coordinate-provider nodes for the synthetic-data DAG.

These supply the grid (``lat``/``lon``/``pixel_coords``) and time
(``time_coord``) coordinates that the fallback variable generators depend on.
They are domain-agnostic: a regular lat/lon grid and a daily time axis.
"""

import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray


def lat(n_lat: int) -> xr.DataArray:
    """Latitude coordinates (dim ``y``)."""
    return xr.DataArray(
        data=np.linspace(50.0, 54.0, n_lat),
        dims=["y"],
        coords={"y": np.arange(n_lat)},
        attrs={"units": "degrees_north", "long_name": "latitude"},
        name="lat",
    )


def lon(n_lon: int) -> xr.DataArray:
    """Longitude coordinates (dim ``x``)."""
    return xr.DataArray(
        data=np.linspace(-4.0, 2.0, n_lon),
        dims=["x"],
        coords={"x": np.arange(n_lon)},
        attrs={"units": "degrees_east", "long_name": "longitude"},
        name="lon",
    )


def pixel_coords(lat: xr.DataArray, lon: xr.DataArray) -> pd.MultiIndex:
    """Create a stacked ``pixel`` MultiIndex from the cartesian product of lat/lon."""
    lat_grid, lon_grid = np.meshgrid(lat.data, lon.data, indexing="ij")
    return pd.MultiIndex.from_arrays(
        [lat_grid.ravel(), lon_grid.ravel()], names=["y", "x"]
    )


def time_coord(n_days: int, start_date: str = "2020-01-01") -> NDArray[np.datetime64]:
    """Create a daily time coordinate of length ``n_days``."""
    start = np.datetime64(start_date)
    return start + np.arange(n_days)
