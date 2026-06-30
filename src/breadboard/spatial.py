"""Spatial dimension stacking utilities."""

import rioxarray as rioxarray
import xarray as xr


def stack_spatial_dims(ds: xr.Dataset) -> xr.Dataset:
    """Stack spatial dimensions into a single pixel dimension.

    Parameters
    ----------
    ds : xr.Dataset
        Input Dataset with spatial dimensions at positions 1 and 2 in the
        dimensions list (with 'time' being the first dimension).

    Returns
    -------
    xr.Dataset
        Dataset with two spatial dimensions stacked into a single 'pixel' dimension.
    """
    # Use rioxarray to identify spatial dimensions (y, x)
    spatial_dims = ds.rio.y_dim, ds.rio.x_dim

    # Stack (y, x) -> pixel
    ds_stacked = ds.stack(pixel=spatial_dims)

    # 4. "Clean up" the MultiIndex
    # This turns 'pixel' into a simple 0, 1, 2... index and
    # transforms y and x into standard 1D arrays aligned with 'pixel'
    # ds_lexi = ds_stacked.reset_index("pixel", drop=True)
    # NOTE: This may be a good idea, but need to change lat-lon grid
    # computation if so.

    return ds_stacked
