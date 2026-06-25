"""Generate synthetic static input data."""

import numpy as np
import pandas as pd
import xarray as xr

# Carbon pool defaults (root t ha-1, leaf t ha-1, stem t ha-1) indexed by plant type.
# 1=grassland, 2=C3 crop, 3=woodland
_POOL_BY_TYPE: dict[int, tuple[float, float, float]] = {
    1: (5.0, 1.0, 10.0),
    2: (3.0, 0.5, 5.0),
    3: (8.0, 2.0, 25.0),
}


def _smooth2d(arr: np.ndarray, radius: int) -> np.ndarray:
    """Box-filter smooth a 2D array, reflecting at boundaries."""
    if radius <= 0 or min(arr.shape) <= 1:
        return arr
    ny, nx = arr.shape
    out = np.zeros_like(arr, dtype=float)
    for di in range(-radius, radius + 1):
        rows = np.clip(np.arange(ny) + di, 0, ny - 1)
        for dj in range(-radius, radius + 1):
            cols = np.clip(np.arange(nx) + dj, 0, nx - 1)
            out += arr[np.ix_(rows, cols)]
    return out / (2 * radius + 1) ** 2


def lat(n_lat: int) -> xr.DataArray:
    """Latitude coordinates.

    Parameters
    ----------
    n_lat : int
        Number of latitude points.

    Returns
    -------
    xr.DataArray
        Latitude DataArray with dim "y".
    """
    return xr.DataArray(
        data=np.linspace(50.0, 54.0, n_lat),
        dims=["y"],
        coords={"y": np.arange(n_lat)},
        attrs={"units": "degrees_north", "long_name": "latitude"},
        name="lat",
    )


def lon(n_lon: int) -> xr.DataArray:
    """Longitude coordinates.

    Parameters
    ----------
    n_lon : int
        Number of longitude points.

    Returns
    -------
    xr.DataArray
        Longitude DataArray with dim "x".
    """
    return xr.DataArray(
        data=np.linspace(-4.0, 2.0, n_lon),
        dims=["x"],
        coords={"x": np.arange(n_lon)},
        attrs={"units": "degrees_east", "long_name": "longitude"},
        name="lon",
    )


def pixel_coords(lat: xr.DataArray, lon: xr.DataArray) -> pd.MultiIndex:
    """Create MultiIndex for pixel dimension from lat/lon arrays.

    Creates a cartesian product of all lat/lon combinations.

    Parameters
    ----------
    lat : xr.DataArray
        Latitude DataArray with dim "y".
    lon : xr.DataArray
        Longitude DataArray with dim "x".

    Returns
    -------
    pd.MultiIndex
        MultiIndex with 'y' and 'x' levels for each pixel.
    """
    lat_vals = lat.data
    lon_vals = lon.data

    lat_grid, lon_grid = np.meshgrid(lat_vals, lon_vals, indexing="ij")
    lat_flat = lat_grid.ravel()
    lon_flat = lon_grid.ravel()

    index = pd.MultiIndex.from_arrays([lat_flat, lon_flat], names=["y", "x"])
    return index


def elevation(n_lat: int, n_lon: int, pixel_coords: pd.MultiIndex) -> xr.DataArray:
    """Generate static elevation in meters.

    Creates a spatially coherent field using a bilinear base (south-north
    gradient) with Gaussian noise smoothed by a box filter.

    Parameters
    ----------
    n_lat : int
        Number of latitude points.
    n_lon : int
        Number of longitude points.
    pixel_coords : pd.MultiIndex
        MultiIndex with 'y' and 'x' levels.

    Returns
    -------
    xr.DataArray
        Elevation data array with dims=["pixel"].
    """
    lat_vals = np.asarray(pixel_coords.get_level_values("y").values).reshape(
        n_lat, n_lon
    )
    lat_min = lat_vals.min()
    lat_range = lat_vals.max() - lat_min or 1.0
    lat_norm = (lat_vals - lat_min) / lat_range  # [0, 1], 0=south

    base = 100.0 + 200.0 * lat_norm  # 100m at south edge, 300m at north edge
    noise = np.random.normal(0, 35, (n_lat, n_lon))
    radius = max(1, min(n_lat, n_lon) // 3)
    smoothed = _smooth2d(noise, radius=radius)
    elevation_data = np.clip((base + smoothed).ravel(), 0.0, 1000.0)

    return xr.DataArray(
        data=elevation_data,
        dims=["pixel"],
        coords={"pixel": pixel_coords},
        attrs={"units": "m", "long_name": "elevation"},
        name="elevation",
    )


def latitude(pixel_coords: pd.MultiIndex) -> xr.DataArray:
    """Return static latitude for each pixel, taken from the grid's y-coordinate.

    Parameters
    ----------
    pixel_coords : pd.MultiIndex
        MultiIndex with 'y' and 'x' levels.

    Returns
    -------
    xr.DataArray
        Latitude data array with dims=["pixel"].
    """
    lat_vals = pixel_coords.get_level_values("y").values
    return xr.DataArray(
        data=lat_vals,
        dims=["pixel"],
        coords={"pixel": pixel_coords},
        attrs={"units": "degrees_north", "long_name": "latitude"},
        name="latitude",
    )


def plant_type(n_lat: int, n_lon: int, pixel_coords: pd.MultiIndex) -> xr.DataArray:
    """Assign static plant type (1=grassland, 2=C3 crop, 3=woodland).

    Assigns types in a repeating spatial pattern so multi-pixel grids always
    contain at least two distinct plant types.

    Parameters
    ----------
    n_lat : int
        Number of latitude points.
    n_lon : int
        Number of longitude points.
    pixel_coords : pd.MultiIndex
        MultiIndex with 'y' and 'x' levels.

    Returns
    -------
    xr.DataArray
        Plant type data array with dims=["pixel"].
    """
    n_pixels = n_lat * n_lon
    # Cycle through types by pixel index so spatial layout is deterministic.
    data = np.array([1, 2, 3], dtype=np.int32)[np.arange(n_pixels) % 3]

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": pixel_coords},
        attrs={"units": "1", "long_name": "plant type"},
        name="plant_type",
    )


def max_soil_moisture(elevation: xr.DataArray) -> xr.DataArray:
    """Compute static maximum soil moisture capacity in mm.

    Decreases linearly with elevation: 300 mm at sea level, 100 mm at 1000 m.

    Parameters
    ----------
    elevation : xr.DataArray
        Elevation DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Max soil moisture data array with dims=["pixel"].
    """
    data = np.clip(300.0 - 0.2 * elevation.values, 100.0, 300.0)

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": elevation.coords["pixel"]},
        attrs={"units": "mm", "long_name": "maximum soil moisture"},
        name="max_soil_moisture",
    )


def clay_content(n_lat: int, n_lon: int, pixel_coords: pd.MultiIndex) -> xr.DataArray:
    """Generate static clay content as a percentage (0-100).

    RothC consumes clay content in percent, so it is generated in percent here
    (typical topsoil clay fractions of 10-40%).

    Parameters
    ----------
    n_lat : int
        Number of latitude points.
    n_lon : int
        Number of longitude points.
    pixel_coords : pd.MultiIndex
        MultiIndex with 'y' and 'x' levels.

    Returns
    -------
    xr.DataArray
        Clay content data array with dims=["pixel"].
    """
    n_pixels = n_lat * n_lon
    data = np.random.uniform(10.0, 40.0, n_pixels)

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": pixel_coords},
        attrs={"units": "percent", "long_name": "clay content"},
        name="clay_content",
    )


def soil_depth(elevation: xr.DataArray) -> xr.DataArray:
    """Compute static soil depth in cm.

    Decreases with elevation: deeper soils in lowland valleys (120 cm) and
    shallower on upland terrain (40 cm).

    Parameters
    ----------
    elevation : xr.DataArray
        Elevation DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Soil depth data array with dims=["pixel"].
    """
    data = np.clip(120.0 - 0.08 * elevation.values, 40.0, 120.0)

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": elevation.coords["pixel"]},
        attrs={"units": "cm", "long_name": "soil depth"},
        name="soil_depth",
    )


def organic_carbon_stocks(elevation: xr.DataArray) -> xr.DataArray:
    """Compute static soil organic carbon stocks in t ha-1.

    Higher-elevation upland mineral soils carry less SOC than lowland peats.

    Parameters
    ----------
    elevation : xr.DataArray
        Elevation DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Organic carbon stocks data array with dims=["pixel"].
    """
    n_pixels = len(elevation)
    base = 130.0 - 0.06 * elevation.values  # ~130 at sea level, ~70 at 1000 m
    noise = np.random.uniform(-10.0, 10.0, n_pixels)
    data = np.clip(base + noise, 30.0, 200.0)

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": elevation.coords["pixel"]},
        attrs={"units": "t ha-1", "long_name": "soil organic carbon stocks"},
        name="organic_carbon_stocks",
    )


def root_pool_init(plant_type: xr.DataArray) -> xr.DataArray:
    """Compute initial root carbon pool in t ha-1, varying by plant type.

    Parameters
    ----------
    plant_type : xr.DataArray
        Plant type DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Root pool init data array with dims=["pixel"].
    """
    data = np.array(
        [_POOL_BY_TYPE.get(int(t), _POOL_BY_TYPE[1])[0] for t in plant_type.values]
    )

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": plant_type.coords["pixel"]},
        attrs={"units": "t ha-1", "long_name": "initial root carbon pool"},
        name="root_pool_init",
    )


def leaf_pool_init(plant_type: xr.DataArray) -> xr.DataArray:
    """Compute initial leaf carbon pool in t ha-1, varying by plant type.

    Parameters
    ----------
    plant_type : xr.DataArray
        Plant type DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Leaf pool init data array with dims=["pixel"].
    """
    data = np.array(
        [_POOL_BY_TYPE.get(int(t), _POOL_BY_TYPE[1])[1] for t in plant_type.values]
    )

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": plant_type.coords["pixel"]},
        attrs={"units": "t ha-1", "long_name": "initial leaf carbon pool"},
        name="leaf_pool_init",
    )


def stem_pool_init(plant_type: xr.DataArray) -> xr.DataArray:
    """Compute initial stem carbon pool in t ha-1, varying by plant type.

    Parameters
    ----------
    plant_type : xr.DataArray
        Plant type DataArray with dim "pixel".

    Returns
    -------
    xr.DataArray
        Stem pool init data array with dims=["pixel"].
    """
    data = np.array(
        [_POOL_BY_TYPE.get(int(t), _POOL_BY_TYPE[1])[2] for t in plant_type.values]
    )

    return xr.DataArray(
        data=data,
        dims=["pixel"],
        coords={"pixel": plant_type.coords["pixel"]},
        attrs={"units": "t ha-1", "long_name": "initial stem carbon pool"},
        name="stem_pool_init",
    )
