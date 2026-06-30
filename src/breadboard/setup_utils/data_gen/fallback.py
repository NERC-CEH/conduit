"""Fallback synthetic data generators for variables without explicit logic."""

import logging
import sys
import types

import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_SUFFIX_RULES: list[tuple[list[str], str]] = [
    (["_fraction", "_ratio", "fapar", "sunshine"], "bounded"),
    (["precipitation", "lai", "gpp", "ppfd", "vpd", "pressure"], "positive"),
    (["_type", "_class", "_flag"], "integer"),
]


def _infer_fallback_type(var_name: str) -> str:
    name = var_name.lower()
    for keywords, ftype in _SUFFIX_RULES:
        if any(k in name for k in keywords):
            return ftype
    return "gaussian"


def _make_daily_fallback(var_name: str):
    ftype = _infer_fallback_type(var_name)

    def fn(
        time_coord: NDArray[np.datetime64],
        pixel_coords: pd.MultiIndex,
    ) -> xr.DataArray:
        logger.warning(
            "No generator for '%s'; emitting %s fallback noise.", var_name, ftype
        )
        shape = (len(time_coord), len(pixel_coords))
        if ftype == "bounded":
            data = np.clip(np.random.normal(0.5, 0.2, shape), 0.0, 1.0)
        elif ftype == "positive":
            data = np.abs(np.random.normal(1.0, 0.5, shape))
        elif ftype == "integer":
            data = np.random.randint(1, 4, shape).astype(float)
        else:
            data = np.random.normal(0.0, 1.0, shape)
        return xr.DataArray(
            data=data,
            dims=["time", "pixel"],
            coords={"time": time_coord, "pixel": pixel_coords},
            attrs={
                "units": "unknown",
                "long_name": var_name,
                "note": "synthetic fallback",
            },
            name=var_name,
        )

    fn.__name__ = fn.__qualname__ = f"{var_name}_daily"
    return fn


def _make_static_fallback(var_name: str):
    ftype = _infer_fallback_type(var_name)

    def fn(
        n_lat: int,
        n_lon: int,
        pixel_coords: pd.MultiIndex,
    ) -> xr.DataArray:
        logger.warning(
            "No generator for '%s'; emitting %s fallback noise.", var_name, ftype
        )
        n_pixels = n_lat * n_lon
        if ftype == "bounded":
            data = np.clip(np.random.normal(0.5, 0.2, n_pixels), 0.0, 1.0)
        elif ftype == "positive":
            data = np.abs(np.random.normal(1.0, 0.5, n_pixels))
        elif ftype == "integer":
            data = np.random.randint(1, 4, n_pixels).astype(float)
        else:
            data = np.random.normal(0.0, 1.0, n_pixels)
        return xr.DataArray(
            data=data,
            dims=["pixel"],
            coords={"pixel": pixel_coords},
            attrs={
                "units": "unknown",
                "long_name": var_name,
                "note": "synthetic fallback",
            },
            name=var_name,
        )

    fn.__name__ = fn.__qualname__ = var_name
    return fn


def build_fallback_module(
    unknown_daily: list[str],
    unknown_static: list[str],
) -> types.ModuleType:
    """Build a dynamic Hamilton-compatible module containing fallback generators.

    Hamilton resolves nodes by function __name__, so each fallback function is
    renamed to match the expected node name before being attached to the module.
    Hamilton also only picks up functions whose ``__module__`` matches the
    module it scans, so each function's ``__module__`` is repointed here.
    """
    mod = types.ModuleType("breadboard.setup_utils.data_gen._fallbacks")
    for var in unknown_daily:
        fn = _make_daily_fallback(var)
        fn.__module__ = mod.__name__
        setattr(mod, fn.__name__, fn)
    for var in unknown_static:
        fn = _make_static_fallback(var)
        fn.__module__ = mod.__name__
        setattr(mod, fn.__name__, fn)
    # Hamilton's module scanner resolves each function's home module via
    # ``inspect.getmodule`` (i.e. ``sys.modules``); register so the nodes are found.
    sys.modules[mod.__name__] = mod
    return mod
