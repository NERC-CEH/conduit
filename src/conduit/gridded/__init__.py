"""Optional gridded (CRS/pixel) geospatial + parallel-Zarr layer for conduit.

**The lazy-import policy, stated once.** Everywhere else in conduit, an import of
`conduit.gridded` sits inside a function body and carries at most a
``# lazy: optional geo extra`` tag. This is why:

- The core is domain-agnostic. `conduit.io` must not require a CRS, a ``pixel``
  dimension, or a geospatial dependency, so it never imports this package at module
  load — only from inside the functions that actually need it, and only once an
  input has been found to carry CRS metadata (`has_crs`, a cheap, dependency-free
  CF-metadata check) or a ``[subset]`` has been configured.
- The dependencies are optional. The CRS paths need the ``geo`` extra
  (``rioxarray``/``pyproj``), which is imported lazily *within* those functions
  (`conduit.gridded.io._ensure_rio`). Importing this package is therefore cheap and
  dependency-free; only actually reprojecting requires the extra, and a missing one
  produces an install hint rather than an ImportError at startup.

The net effect: a non-gridded pipeline never touches rioxarray or pyproj, and
``import conduit`` works whether or not the extra is installed. There is a test for
that (`test_arbitrary_dims.py::test_no_geospatial_deps_imported_without_crs`).
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
