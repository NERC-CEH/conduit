"""Spatial dimension stacking utilities (optional geospatial extra)."""

import xarray as xr


def stack_spatial_dims(ds: xr.Dataset) -> xr.Dataset:
    """Stack a dataset's two spatial dimensions into a single ``pixel`` dimension.

    The spatial dims are whatever ``rioxarray`` infers from the dataset's CF metadata
    (``x``/``y``, ``easting``/``northing``, …) — nothing is assumed from their position
    or name. They are stacked in ``(y, x)`` order.

    The resulting ``pixel`` coordinate keeps its ``(y, x)`` **MultiIndex**: that is what
    `conduit.gridded.io.unstack_pixel` reverses to rebuild the grid, and what
    `conduit.gridded.io.flatten_pixel_index` converts to plain 1-D level coords for
    serialisation (a MultiIndex cannot be written to NetCDF/Zarr).

    Requires the optional ``geo`` extra (``rioxarray``/``pyproj``), which is only
    imported when geospatial inputs are actually used.
    """
    import rioxarray as rioxarray

    return ds.stack(pixel=(ds.rio.y_dim, ds.rio.x_dim))
