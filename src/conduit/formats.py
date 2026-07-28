"""The file-format registry: one table, one dispatch.

Every extension-based decision conduit makes — which reader to call, which writer,
whether a format can be region-written by a ``[subset]`` run, whether it needs a
pre-created store — is an entry in `FORMATS` and a lookup through `format_for`.
Adding a format means adding one `Format`; nothing else in the codebase enumerates
suffixes.

Formats fall into three **groups**, which is what the public loaders in
`conduit.io` mean by their names:

- ``dataset`` — NetCDF/Zarr: an n-dimensional Dataset, read as-is;
- ``table`` — CSV/Parquet: a single-point time series, reshaped to ``(time, pixel)``;
- ``scalar`` — JSON/TOML: single-point static values, reshaped to ``(pixel,)``.

``scalar`` formats are input-only (``write=None``), which is why `save_outputs`
rejects a ``.json`` destination.
"""

import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

Reader = Callable[[str | PathLike], xr.Dataset]
Writer = Callable[[xr.Dataset, str | PathLike], None]
FrameWriter = Callable[[pd.DataFrame, str | PathLike], None]


# ---------------------------------------------------------------------------
# Per-format primitives (no dispatch here — the registry does that)
# ---------------------------------------------------------------------------


def _read_netcdf(path: str | PathLike) -> xr.Dataset:
    return xr.open_dataset(path, engine="netcdf4", decode_coords="all")


def _read_zarr(path: str | PathLike) -> xr.Dataset:
    return xr.open_dataset(path, engine="zarr", decode_coords="all", consolidated=False)


def _write_netcdf(ds: xr.Dataset, path: str | PathLike) -> None:
    ds.to_netcdf(path, engine="netcdf4")


def _write_zarr(ds: xr.Dataset, path: str | PathLike) -> None:
    ds.to_zarr(path, consolidated=False)


def _timeseries_from_frame(df: pd.DataFrame) -> xr.Dataset:
    """Shape a single-point table into a ``(time, pixel)`` Dataset."""
    if "time" in df.columns:
        df = df.set_index("time")
    if df.index.name != "time":
        df.index.name = "time"
    df.index = pd.to_datetime(df.index)
    ds = df.to_xarray().expand_dims({"pixel": [0]})
    return ds.transpose("time", "pixel")


def _read_csv(path: str | PathLike) -> xr.Dataset:
    return _timeseries_from_frame(pd.read_csv(path, index_col=0, parse_dates=True))


def _read_parquet(path: str | PathLike) -> xr.Dataset:
    return _timeseries_from_frame(pd.read_parquet(path))


def dataset_to_frame(ds: xr.Dataset) -> pd.DataFrame:
    """Convert an output Dataset to a DataFrame, dropping a size-1 pixel dim."""
    if "pixel" in ds.dims:
        ds = ds.squeeze("pixel", drop=True)
    return ds.to_dataframe()


def _write_frame_csv(df: pd.DataFrame, path: str | PathLike) -> None:
    df.to_csv(path)


def _write_frame_parquet(df: pd.DataFrame, path: str | PathLike) -> None:
    df.to_parquet(path)


def _write_csv(ds: xr.Dataset, path: str | PathLike) -> None:
    _write_frame_csv(dataset_to_frame(ds), path)


def _write_parquet(ds: xr.Dataset, path: str | PathLike) -> None:
    _write_frame_parquet(dataset_to_frame(ds), path)


def _static_from_mapping(data: dict) -> xr.Dataset:
    """Shape a flat ``{name: value}`` mapping into a ``(pixel,)`` Dataset."""
    return xr.Dataset(
        {
            k: xr.DataArray(np.asarray([v], dtype=float), dims=["pixel"])
            for k, v in data.items()
        },
        coords={"pixel": [0]},
    )


def _read_json(path: str | PathLike) -> xr.Dataset:
    with open(path) as f:
        return _static_from_mapping(json.load(f))


def _read_toml(path: str | PathLike) -> xr.Dataset:
    with open(path, "rb") as f:
        return _static_from_mapping(tomllib.load(f))


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Format:
    """One supported file format."""

    key: str
    #: Recognised extensions, lowercase and dot-prefixed. The first is canonical.
    suffixes: tuple[str, ...]
    #: ``dataset`` (n-d), ``table`` (single-point time series) or ``scalar`` (static).
    group: str
    read: Reader | None
    write: Writer | None
    #: Whether a ``[subset]`` run can write a partial result to this format.
    supports_subset: bool
    #: Whether a subset write targets a store that must be created up front
    #: (``conduit gridded create-store``) rather than a file per subset.
    needs_store: bool = False
    #: DataFrame-level writer, for the ``table`` group only (`write_frame`).
    write_frame: FrameWriter | None = None


FORMATS: tuple[Format, ...] = (
    Format("netcdf", (".nc", ".netcdf"), "dataset", _read_netcdf, _write_netcdf, True),
    Format("zarr", (".zarr",), "dataset", _read_zarr, _write_zarr, True, True),
    Format(
        "csv",
        (".csv",),
        "table",
        _read_csv,
        _write_csv,
        False,
        write_frame=_write_frame_csv,
    ),
    Format(
        "parquet",
        (".parquet", ".pq"),
        "table",
        _read_parquet,
        _write_parquet,
        False,
        write_frame=_write_frame_parquet,
    ),
    Format("json", (".json",), "scalar", _read_json, None, False),
    Format("toml", (".toml",), "scalar", _read_toml, None, False),
)


def supported_suffixes(*, writable: bool = False) -> list[str]:
    """Every recognised extension, or only those that can be written."""
    return sorted(
        suffix
        for fmt in FORMATS
        for suffix in fmt.suffixes
        if not writable or fmt.write is not None
    )


def format_for(path: str | PathLike, *, writable: bool = False) -> Format:
    """Return the `Format` handling ``path``, by extension.

    A suffix-less path that is an existing directory is read as Zarr — that is the
    shape a Zarr store takes on disk. Anything unrecognised raises a ``ValueError``
    naming *every* supported extension, rather than only those of whichever loader
    happened to be last in an if-chain.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if not suffix and p.is_dir():
        return _BY_KEY["zarr"]

    for fmt in FORMATS:
        if suffix in fmt.suffixes:
            if writable and fmt.write is None:
                raise ValueError(
                    f"Cannot write {fmt.key} ({suffix}) — it is an input-only "
                    f"format. Writable formats: {supported_suffixes(writable=True)}."
                )
            return fmt

    raise ValueError(
        f"Unsupported file extension {suffix or '(none)'!r} (path {str(path)!r}). "
        f"Supported: {supported_suffixes(writable=writable)}."
    )


_BY_KEY: dict[str, Format] = {fmt.key: fmt for fmt in FORMATS}


def group_suffixes(group: str) -> list[str]:
    """Every extension in one format group."""
    return sorted(s for f in FORMATS if f.group == group for s in f.suffixes)


def _in_group(path: str | PathLike, group: str, *, writable: bool = False) -> Format:
    """Look ``path`` up, requiring it to be in ``group``."""
    fmt = format_for(path, writable=writable)
    if fmt.group != group:
        raise ValueError(
            f"Unsupported file extension {Path(path).suffix or '(none)'!r} for a "
            f"{group} file (path {str(path)!r}). Use one of {group_suffixes(group)}."
        )
    return fmt


def read_in_group(path: str | PathLike, group: str) -> xr.Dataset:
    """Read ``path``, requiring it to be in ``group`` (see the module docstring)."""
    fmt = _in_group(path, group)
    assert fmt.read is not None  # every registered format is readable
    return fmt.read(path)


def write_in_group(ds: xr.Dataset, path: str | PathLike, group: str) -> None:
    """Write ``ds`` to ``path``, requiring it to be in ``group``."""
    fmt = _in_group(path, group, writable=True)
    assert fmt.write is not None
    fmt.write(ds, path)


def write_frame(df: pd.DataFrame, path: str | PathLike) -> None:
    """Write a DataFrame to a ``table`` format (CSV/Parquet), by extension."""
    fmt = _in_group(path, "table", writable=True)
    assert fmt.write_frame is not None
    fmt.write_frame(df, path)
