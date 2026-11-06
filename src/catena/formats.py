"""The file-format registry.

Every extension-based decision catena makes — which reader to call, which writer,
whether a format needs a pre-created store for a ``[subset]`` run — is an entry in
`FORMATS`, looked up through `format_for`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

import xarray as xr

from .errors import CatenaValueError

Reader = Callable[[str | PathLike], xr.Dataset]
Writer = Callable[[xr.Dataset, str | PathLike], None]


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


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Format:
    """One supported file format."""

    key: str
    #: Recognised extensions, lowercase and dot-prefixed. The first is canonical.
    suffixes: tuple[str, ...]
    read: Reader
    write: Writer
    #: Whether a subset write targets a store that must be created up front
    #: (``catena gridded create-store``) rather than a file per subset.
    needs_store: bool = False


FORMATS: tuple[Format, ...] = (
    Format("netcdf", (".nc", ".netcdf"), _read_netcdf, _write_netcdf),
    Format("zarr", (".zarr",), _read_zarr, _write_zarr, True),
)


def supported_suffixes() -> list[str]:
    """Every recognised extension."""
    return sorted(suffix for fmt in FORMATS for suffix in fmt.suffixes)


def format_for(path: str | PathLike) -> Format:
    """Return the `Format` handling ``path``, by extension.

    A suffix-less path that is an existing directory is read as Zarr — that is the
    shape a Zarr store takes on disk. Anything unrecognised raises a ``ValueError``
    naming every supported extension.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if not suffix and p.is_dir():
        return _BY_KEY["zarr"]

    for fmt in FORMATS:
        if suffix in fmt.suffixes:
            return fmt

    raise CatenaValueError(
        f"Unsupported file extension {suffix or '(none)'!r} (path {str(path)!r}). "
        f"Supported: {supported_suffixes()}."
    )


_BY_KEY: dict[str, Format] = {fmt.key: fmt for fmt in FORMATS}
