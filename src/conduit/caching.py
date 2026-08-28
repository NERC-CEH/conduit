"""Hamilton result caching for conduit.

Hamilton's native caching (``Builder.with_cache``) keys each node on a fingerprint
of its code and inputs, and treats ``xarray.DataArray`` objects as unhashable,
assigning them a random per-result version. Importing this module registers a
content-based fingerprint for ``xarray.DataArray`` instead, so cache keys are stable
across runs and processes and sensitive to changes in the underlying data.
"""

import xarray as xr
from hamilton import driver
from hamilton.caching import fingerprinting

from .specs import CacheSpec


@fingerprinting.hash_value.register(xr.DataArray)
def _hash_dataarray(obj: xr.DataArray, *args, depth: int = 0, **kwargs) -> str:
    """Content-based fingerprint for an xarray.DataArray.

    Delegates the numeric payload to Hamilton's numpy handler and folds in the
    name, dims, coordinate values and ``attrs``. Hashing ``attrs`` is what makes
    a *units* change invalidate the cache: the same numbers labelled ``kg``
    rather than ``g`` are a different array, and a downstream node's converted
    result must not be served from the cache computed under the old label.
    """
    parts = [
        fingerprinting.hash_value(obj.values, depth=depth),
        fingerprinting.hash_value(str(obj.name), depth=depth),
        fingerprinting.hash_value(list(obj.dims), depth=depth),
        fingerprinting.hash_value(
            {k: v.values for k, v in obj.coords.items()}, depth=depth
        ),
        fingerprinting.hash_value(dict(obj.attrs), depth=depth),
    ]
    return fingerprinting.hash_value(parts, depth=depth)


def apply_cache(builder: driver.Builder, cache: CacheSpec) -> driver.Builder:
    """Enable Hamilton caching on a Builder according to a CacheSpec."""
    kwargs: dict = {"path": cache.path}
    if cache.recompute:
        kwargs["recompute"] = cache.recompute
    if cache.disable:
        kwargs["disable"] = cache.disable
    return builder.with_cache(**kwargs)
