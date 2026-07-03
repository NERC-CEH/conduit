"""Optional gridded (CRS/pixel) geospatial + parallel-Zarr layer for conduit.

The domain-agnostic core (`conduit.io`) never imports this at module load; it
delegates here lazily only when an input carries CRS metadata or a ``[subset]`` is
configured. The CRS reprojection paths need the optional ``geo`` extra
(``rioxarray``/``pyproj``), imported lazily within the functions that use them.
"""

from .io import (
    MisalignedGridError,
    compute_lat_lon,
    create_output_store,
    flatten_pixel_index,
    has_crs,
    merge_subset_outputs,
    stack_if_gridded,
    subset_suffix,
    unstack_if_gridded,
    unstack_pixel,
)

__all__ = [
    "MisalignedGridError",
    "compute_lat_lon",
    "create_output_store",
    "flatten_pixel_index",
    "has_crs",
    "merge_subset_outputs",
    "stack_if_gridded",
    "subset_suffix",
    "unstack_if_gridded",
    "unstack_pixel",
]
