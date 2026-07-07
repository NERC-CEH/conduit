"""Intrinsic input-Dataset compatibility checks.

A small library of pairwise/variadic predicates over input ``Dataset``s,
``check_X(*datasets, **kwargs) -> None`` (raise on failure, return ``None`` on
pass), plus a registry (`CHECKS`) and a runner (`run_input_checks`) that applies
a parsed ``[validation].checks`` config block and aggregates failures.

Every check here is a statement about the inputs *alone* — no DAG operation is
baked in. Operation-coupled guarantees (e.g. "does a resample node land on the
right anchor?") belong to the Freq facet, not this suite.

Importing this module stays free of the optional ``geo`` extra: the spatial
checks import from ``conduit.gridded`` lazily, only when invoked.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
import xarray as xr

from .io import _time_dims

if TYPE_CHECKING:
    from .config import CheckSpec

logger = logging.getLogger(__name__)


class InputCheckError(ValueError):
    """Raised (by `run_input_checks`) when one or more input checks fail."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _single_time_index(ds: xr.Dataset) -> pd.DatetimeIndex:
    """Return the dataset's single time index, raising if there is not exactly one.

    Uses `conduit.io._time_dims` so arbitrarily-labelled time dimensions are
    handled; the "at most one time dimension per input" invariant (enforced in
    `load_inputs`) guarantees ``len(tdims) <= 1``.
    """
    tdims = _time_dims(ds)
    if not tdims:
        raise ValueError(
            "dataset has no time dimension; a time check cannot be applied to it"
        )
    return ds.get_index(tdims[0])  # type: ignore[return-value]


def _require_arity(datasets: tuple[xr.Dataset, ...], name: str, arity: int) -> None:
    """Backstop arity guard for fixed-arity checks (the parser catches this earlier)."""
    if len(datasets) != arity:
        raise ValueError(
            f"check '{name}' takes exactly {arity} datasets, got {len(datasets)}"
        )


# ---------------------------------------------------------------------------
# Time checks
# ---------------------------------------------------------------------------


def time_equal(*datasets: xr.Dataset) -> None:
    """Assert every dataset shares an identical time index."""
    if len(datasets) < 2:
        return
    ref = _single_time_index(datasets[0])
    for i, ds in enumerate(datasets[1:], start=1):
        idx = _single_time_index(ds)
        if not ref.equals(idx):
            raise ValueError(
                f"dataset {i} time index differs from dataset 0 "
                f"({len(idx)} vs {len(ref)} timestamps)"
            )


def time_subset(*datasets: xr.Dataset) -> None:
    """Assert ``datasets[1]`` timestamps are a subset of ``datasets[0]``'s.

    Directional: the first dataset is the reference (superset), the second the
    candidate subset. Raw timestamps, no resampling.
    """
    _require_arity(datasets, "time_subset", 2)
    sup = _single_time_index(datasets[0])
    sub = _single_time_index(datasets[1])
    missing = sub[~sub.isin(sup)]
    if len(missing) > 0:
        raise ValueError(
            f"dataset 1 has {len(missing)} timestamp(s) absent from dataset 0: "
            f"{missing.tolist()}"
        )


# ---------------------------------------------------------------------------
# Spatial / CRS checks (lazy gridded import — optional `geo` extra)
# ---------------------------------------------------------------------------


def spatial_grid_equal(*datasets: xr.Dataset, atol: float = 1e-6) -> None:
    """Assert every dataset shares CRS + x/y dim names + coordinate values."""
    from .gridded.io import _check_common_grid

    if len(datasets) < 2:
        return
    ref = datasets[0]
    for i, ds in enumerate(datasets[1:], start=1):
        _check_common_grid(
            ref, ds, label1="dataset 0", label2=f"dataset {i}", atol=atol
        )


def crs_equal(*datasets: xr.Dataset) -> None:
    """Assert every dataset shares a CRS (ignoring resolution/extent)."""
    from .gridded.io import _ensure_rio

    if len(datasets) < 2:
        return
    _ensure_rio()
    ref_crs = datasets[0].rio.crs
    for i, ds in enumerate(datasets[1:], start=1):
        if ds.rio.crs != ref_crs:
            raise ValueError(
                f"dataset {i} CRS ({ds.rio.crs}) differs from dataset 0 ({ref_crs})"
            )


# ---------------------------------------------------------------------------
# Coordinate checks
# ---------------------------------------------------------------------------


def coords_equal(*datasets: xr.Dataset, coords: list[str], atol: float = 1e-6) -> None:
    """Assert the named ``coords`` match across every dataset.

    Float coordinates are compared with ``atol``; other dtypes (datetime,
    string, integer) are compared exactly.
    """
    if len(datasets) < 2:
        return
    for coord in coords:
        ref = datasets[0].coords.get(coord)
        if ref is None:
            raise ValueError(f"coordinate '{coord}' missing from dataset 0")
        for i, ds in enumerate(datasets[1:], start=1):
            other = ds.coords.get(coord)
            if other is None:
                raise ValueError(f"coordinate '{coord}' missing from dataset {i}")
            if other.shape != ref.shape:
                raise ValueError(
                    f"coordinate '{coord}' has shape {other.shape} in dataset {i} "
                    f"but {ref.shape} in dataset 0"
                )
            if np.issubdtype(ref.dtype, np.floating):
                if not np.allclose(ref.values, other.values, atol=atol):
                    raise ValueError(
                        f"coordinate '{coord}' values differ between dataset 0 and "
                        f"dataset {i} (atol={atol})"
                    )
            elif not ref.equals(other):
                raise ValueError(
                    f"coordinate '{coord}' values differ between dataset 0 and "
                    f"dataset {i}"
                )


# ---------------------------------------------------------------------------
# Registry + runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    """A registry entry: the predicate plus its expected arity.

    ``arity`` is ``"variadic"`` (any number, ``>=1``) or an exact integer. The
    config parser uses it to reject an ill-sized ``inputs`` list at parse time.
    """

    func: Callable[..., None]
    arity: "Literal['variadic'] | int"


CHECKS: dict[str, Check] = {
    "time_equal": Check(time_equal, "variadic"),
    "time_subset": Check(time_subset, 2),
    "spatial_grid_equal": Check(spatial_grid_equal, "variadic"),
    "crs_equal": Check(crs_equal, "variadic"),
    "coords_equal": Check(coords_equal, "variadic"),
}


def run_input_checks(
    raw_datasets: dict[str, xr.Dataset], checks: "list[CheckSpec]"
) -> None:
    """Apply each `CheckSpec` to the loaded raw Datasets, aggregating failures.

    A variadic check that receives fewer than two datasets is a quiet no-op.
    Individual check failures are collected and raised together as a single
    `InputCheckError` naming every failed check.
    """
    failures: list[tuple[CheckSpec, Exception]] = []
    for spec in checks:
        entry = CHECKS[spec.check]
        datasets = tuple(raw_datasets[label] for label in spec.inputs)
        if entry.arity == "variadic" and len(datasets) < 2:
            logger.info(
                "check '%s' over %s is a no-op (fewer than two datasets)",
                spec.check,
                spec.inputs,
            )
            continue
        try:
            entry.func(*datasets, **spec.kwargs)
        except Exception as exc:
            failures.append((spec, exc))

    if failures:
        lines = [
            f"  - check '{spec.check}' over {spec.inputs}: {exc}"
            for spec, exc in failures
        ]
        raise InputCheckError(
            f"{len(failures)} input check(s) failed:\n" + "\n".join(lines)
        )
