"""I/O functions for loading inputs and saving outputs outside the Hamilton DAG."""

import os
from os import PathLike
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import rioxarray as rioxarray
import xarray as xr
from pyproj import Transformer

from .config import RESAMPLE_FREQ_MAP, IOSpec, SubsetSpec
from .spatial import stack_spatial_dims


class MisalignedGridError(Exception):
    """Raised when two datasets do not share a common CRS and coordinates."""


# ---------------------------------------------------------------------------
# Internal helpers: opening datasets
# ---------------------------------------------------------------------------


def load_dataset(path: str | PathLike) -> xr.Dataset:
    """Open a NetCDF or Zarr dataset with coordinates decoded."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".nc", ".netcdf"):
        return xr.open_dataset(path, engine="netcdf4", decode_coords="all")
    elif suffix == ".zarr":
        return xr.open_dataset(
            path, engine="zarr", decode_coords="all", consolidated=False
        )
    else:
        raise ValueError(f"Unsupported file extension: {p.suffix}.")


def load_timeseries(path: str | PathLike) -> xr.Dataset:
    """Load a single-point time series from CSV or Parquet.

    Returns a Dataset with dims (time, pixel) where pixel has coordinate value 0.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    elif suffix in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    else:
        raise ValueError(
            f"Unsupported format: '{suffix}'. Use '.csv', '.parquet', or '.pq'."
        )

    if "time" in df.columns:
        df = df.set_index("time")
    if df.index.name != "time":
        df.index.name = "time"
    df.index = pd.to_datetime(df.index)

    ds = df.to_xarray()
    ds = ds.expand_dims({"pixel": [0]})
    return ds.transpose("time", "pixel")


def load_static(path: str | PathLike) -> xr.Dataset:
    """Load single-point static inputs from JSON or TOML.

    Returns a Dataset with dim (pixel,) where pixel has coordinate value 0.
    """
    import json
    import tomllib

    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".json":
        with open(p) as f:
            data: dict = json.load(f)
    elif suffix == ".toml":
        with open(p, "rb") as f:
            data = tomllib.load(f)
    else:
        raise ValueError(f"Unsupported format: '{suffix}'. Use '.json' or '.toml'.")

    return xr.Dataset(
        {
            k: xr.DataArray(np.asarray([v], dtype=float), dims=["pixel"])
            for k, v in data.items()
        },
        coords={"pixel": [0]},
    )


def _load_raw(path: str) -> xr.Dataset:
    """Dispatch to the right loader based on file extension."""
    suffix = Path(path).suffix.lower()
    if suffix in (".nc", ".netcdf", ".zarr"):
        return load_dataset(path)
    if suffix in (".json", ".toml"):
        return load_static(path)
    return load_timeseries(path)  # raises ValueError for unsupported extensions


# ---------------------------------------------------------------------------
# Internal helpers: stacking / unstacking
# ---------------------------------------------------------------------------


def stack_if_gridded(ds: xr.Dataset) -> xr.Dataset:
    """Stack (y, x) to pixel if CRS-bearing 2D grid; pass through otherwise."""
    if "pixel" in ds.dims:
        return ds
    if ds.rio.crs is not None:
        return stack_spatial_dims(ds)
    return ds


def unstack_if_gridded(ds: xr.Dataset) -> xr.Dataset:
    """Unstack pixel to (y, x) if MultiIndex; pass through otherwise."""
    if "pixel" in ds.dims and isinstance(ds.indexes.get("pixel"), pd.MultiIndex):
        return ds.unstack("pixel")
    return ds


def _pixel_level_coords(ds: xr.Dataset) -> list[str]:
    """Names of the non-index coords that vary along ``pixel`` (the grid levels)."""
    return [str(c) for c in ds.coords if c != "pixel" and ds[c].dims == ("pixel",)]


def flatten_pixel_index(ds: xr.Dataset) -> xr.Dataset:
    """Turn a (y, x) MultiIndex ``pixel`` coord into plain 1D level coords.

    A pandas ``MultiIndex`` cannot be serialised to NetCDF/Zarr, so this resets
    it: the (y, x) levels become ordinary 1D coordinate variables along ``pixel``
    and ``pixel`` itself becomes an unlabelled dimension.  The inverse of
    `unstack_pixel`.
    """
    if "pixel" in ds.dims and isinstance(ds.indexes.get("pixel"), pd.MultiIndex):
        return ds.reset_index("pixel")
    return ds


def unstack_pixel(ds: xr.Dataset) -> xr.Dataset:
    """Reconstruct a (y, x) grid from a stacked/flattened ``pixel`` dataset.

    Handles both a live ``pixel`` MultiIndex and a flattened dataset (as produced
    by `flatten_pixel_index` and read back from disk), where the grid levels
    are stored as ordinary 1D coords along ``pixel``.
    """
    if "pixel" not in ds.dims:
        return ds
    if not isinstance(ds.indexes.get("pixel"), pd.MultiIndex):
        levels = _pixel_level_coords(ds)
        if not levels:
            return ds
        ds = ds.set_index(pixel=levels)
    return ds.unstack("pixel")


# ---------------------------------------------------------------------------
# Internal helpers: datetime validation
# ---------------------------------------------------------------------------

_FREQ_CODES: dict[str, str] = {"daily": "D", "weekly": "W", "monthly": "ME"}


def _validate_dates(ds: xr.Dataset, freq: str) -> pd.DatetimeIndex:
    """Extract and validate the time index from a dataset."""
    idx = cast(pd.DatetimeIndex, ds.get_index("time"))
    if not isinstance(idx, pd.DatetimeIndex):
        raise ValueError(
            f"Expected a DatetimeIndex for '{freq}' inputs, got {type(idx)}"
        )

    expected = _FREQ_CODES[freq]
    inferred = pd.infer_freq(idx)

    if inferred is None:
        raise ValueError(f"Could not determine frequency from '{freq}' time index")

    if expected == "W":
        passes = any(inferred.startswith(p) for p in ("W", "7D"))
    elif expected == "ME":
        passes = any(inferred.startswith(p) for p in ("ME", "MS"))
    else:
        passes = inferred == expected

    if not passes:
        raise ValueError(
            f"Expected '{freq}' time index with frequency '{expected}', "
            f"got '{inferred}'"
        )

    return idx


# ---------------------------------------------------------------------------
# Internal helpers: cross-frequency temporal alignment
# ---------------------------------------------------------------------------


def _validate_temporal_alignment(dates: dict[str, pd.DatetimeIndex]) -> None:
    """Raise ValueError if coarser-frequency dates are not valid resample labels.

    For each (fine, coarse) pair in RESAMPLE_FREQ_MAP where both are present,
    derives the expected coarse timestamps by resampling the fine index and
    checks that all actual coarse dates are a subset of those expected timestamps.
    Pairs where one or both frequencies are absent are silently skipped.
    """
    for (fine, coarse), freq in RESAMPLE_FREQ_MAP.items():
        if fine not in dates or coarse not in dates:
            continue
        expected = pd.DatetimeIndex(
            pd.Series(0, index=dates[fine]).resample(freq).mean().index
        )
        misaligned = dates[coarse][~dates[coarse].isin(expected)]
        if len(misaligned) > 0:
            raise ValueError(
                f"Temporal alignment check failed for '{fine}' → '{coarse}': "
                f"the following '{coarse}' timestamps are not valid '{freq}' "
                f"resample period labels from the '{fine}' index: "
                f"{misaligned.tolist()}"
            )


# ---------------------------------------------------------------------------
# Internal helpers: grid computation
# ---------------------------------------------------------------------------


def _check_common_grid(
    ds1: xr.Dataset,
    ds2: xr.Dataset,
    label1: str = "ds1",
    label2: str = "ds2",
    atol: float = 1e-6,
) -> None:
    """Raise MisalignedGridError if CRS and coordinates do not match."""
    if ds1.rio.crs != ds2.rio.crs:
        raise MisalignedGridError(
            f"Mismatched CRS! {label1}={ds1.rio.crs} ≠ {label2}={ds2.rio.crs}"
        )
    x1, y1 = ds1.rio.x_dim, ds1.rio.y_dim
    x2, y2 = ds2.rio.x_dim, ds2.rio.y_dim
    if not (x1 == x2 and y1 == y2):
        raise MisalignedGridError(
            f"Mismatched dimension names: {label1}=({x1}, {y1}) ≠ {label2}=({x2}, {y2})"
        )
    try:
        np.testing.assert_allclose(ds1[x1].values, ds2[x2].values, atol=atol)
        np.testing.assert_allclose(ds1[y1].values, ds2[y2].values, atol=atol)
    except AssertionError as e:
        raise MisalignedGridError(
            f"Mismatched coordinate values between {label1} and {label2}!"
        ) from e


def _compute_lat_lon(
    spatial_datasets: dict[str, xr.Dataset],
) -> tuple[xr.DataArray, xr.DataArray]:
    """Compute stacked latitude and longitude DataArrays from CRS-bearing datasets."""
    items = list(spatial_datasets.items())
    ref_name, ref_ds = items[0]
    for name, ds in items[1:]:
        _check_common_grid(ref_ds, ds, label1=ref_name, label2=name)

    x_dim, y_dim = ref_ds.rio.x_dim, ref_ds.rio.y_dim
    x = ref_ds[x_dim].values
    y = ref_ds[y_dim].values

    # indexing="ij": x varies along axis 0, y along axis 1
    x_grid, y_grid = np.meshgrid(x, y, indexing="ij")
    transformer = Transformer.from_crs(ref_ds.rio.crs, "EPSG:4326", always_xy=True)
    lon_grid, lat_grid = transformer.transform(x_grid, y_grid)

    grid_ds = xr.Dataset(
        data_vars={
            "latitude": (["x", "y"], lat_grid),
            "longitude": (["x", "y"], lon_grid),
        },
        coords={"x": x, "y": y},
    )
    stacked = stack_spatial_dims(grid_ds)
    return stacked.latitude, stacked.longitude


# ---------------------------------------------------------------------------
# Internal helpers: saving datasets
# ---------------------------------------------------------------------------


def dataset_to_dataframe(ds: xr.Dataset) -> pd.DataFrame:
    """Convert output Dataset to DataFrame, squeezing size-1 pixel dim if present."""
    if "pixel" in ds.dims:
        ds = ds.squeeze("pixel", drop=True)
    return ds.to_dataframe()


def save_timeseries(df: pd.DataFrame, path: str | PathLike) -> None:
    """Save a DataFrame to CSV or Parquet, auto-detected by extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path)
    elif suffix in (".parquet", ".pq"):
        df.to_parquet(path)
    else:
        raise ValueError(
            f"Unsupported format: '{suffix}'. Use '.csv', '.parquet', or '.pq'."
        )


def _save_netcdf(ds: xr.Dataset, path: str | PathLike) -> None:
    """Save a dataset to NetCDF or Zarr based on extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".nc", ".netcdf"):
        ds.to_netcdf(path, engine="netcdf4")
    elif suffix == ".zarr" or (not suffix and p.is_dir()):
        ds.to_zarr(path, consolidated=False)
    else:
        raise ValueError(
            f"Unsupported file extension: '{suffix}'. Use '.nc', '.netcdf', or '.zarr'."
        )


def _save(ds: xr.Dataset, path: str) -> None:
    suffix = Path(path).suffix.lower()
    if suffix in (".nc", ".netcdf", ".zarr"):
        _save_netcdf(ds, path)
    else:
        save_timeseries(dataset_to_dataframe(ds), path)


def subset_suffix(spec: SubsetSpec) -> str:
    """Filename suffix that uniquely identifies a pixel subset, e.g. ``_p0-500``."""
    return f"_p{spec.pixel_start}-{spec.pixel_end}"


def _subset_path(path: str, spec: SubsetSpec) -> Path:
    """Insert the subset suffix before the file extension."""
    p = Path(path)
    return p.with_name(f"{p.stem}{subset_suffix(spec)}{p.suffix}")


def _save_zarr_region(ds: xr.Dataset, path: str, spec: SubsetSpec) -> None:
    """Write a pixel subset into an existing Zarr store via a region write.

    The store must already exist (see the ``create-store`` CLI command).  Only
    the data variables are written; coordinates already live in the store, and
    writing them in region mode is both unnecessary and disallowed by xarray.
    """
    store = Path(path)
    if not store.exists():
        raise FileNotFoundError(
            f"Zarr store '{path}' does not exist. Create it once before running "
            f"subset processes with: `breadboard create-store <config>`."
        )

    template = xr.open_zarr(store, consolidated=False)
    n_pixel = template.sizes["pixel"]
    # Only the data variables are region-written, so their on-disk pixel chunking
    # is what governs concurrency safety (coords are written once by create-store).
    sample = template[next(iter(template.data_vars))]
    chunks_enc = sample.encoding.get("chunks")
    chunk = (
        chunks_enc[list(sample.dims).index("pixel")]
        if chunks_enc and "pixel" in sample.dims
        else n_pixel
    )
    if spec.pixel_start % chunk != 0 or (
        spec.pixel_end % chunk != 0 and spec.pixel_end != n_pixel
    ):
        raise ValueError(
            f"[subset] range {spec.pixel_start}-{spec.pixel_end} is not aligned to "
            f"the store's pixel chunk size ({chunk}). Concurrent region writes "
            f"require subset boundaries to fall on chunk boundaries. Re-create the "
            f"store with a matching --pixel-chunk, or adjust the subset range."
        )

    data_only = ds.drop_vars(list(ds.coords))
    region = {"pixel": slice(spec.pixel_start, spec.pixel_end)}
    data_only.to_zarr(store, region=region, consolidated=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_inputs(
    input_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
) -> dict[str, Any]:
    """Load all configured inputs and return them as a flat dict of named DataArrays.

    Keys follow Hamilton naming conventions:
    - Temporal variables: ``{var}_{freq}`` (e.g. ``temperature_daily``)
    - Static variables: ``{var}`` (no suffix)
    - Time indices: ``dates_{freq}``
    - Grid: ``latitude``, ``longitude`` (only when CRS-bearing inputs are present)

    Parameters
    ----------
    input_specs:
        Mapping from frequency string to ``IOSpec`` (path, vars, format).
        Typically ``parsed_config.input_specs``.
    subset_spec:
        If provided, slice all pixel-bearing inputs to the specified pixel
        range after loading.  The pixel ordering follows the row-major
        stacking of the spatial grid.  Typically ``parsed_config.subset_spec``.
    """
    inputs: dict[str, Any] = {}
    raw_datasets: dict[str, xr.Dataset] = {}

    for freq, spec in input_specs.items():
        ds_raw = _load_raw(spec.path)
        raw_datasets[freq] = ds_raw

        ds = stack_if_gridded(ds_raw)
        suffix = "" if freq == "static" else f"_{freq}"
        vars_to_load = list(ds.data_vars) if spec.vars is None else spec.vars
        for var in vars_to_load:
            inputs[f"{var}{suffix}"] = ds[var]

        if freq != "static":
            inputs[f"dates_{freq}"] = _validate_dates(ds_raw, freq)

    dates = {
        key[len("dates_") :]: val
        for key, val in inputs.items()
        if key.startswith("dates_")
    }
    _validate_temporal_alignment(dates)

    spatial = {f: ds for f, ds in raw_datasets.items() if ds.rio.crs is not None}
    if spatial:
        lat, lon = _compute_lat_lon(spatial)
        inputs["latitude"] = lat
        inputs["longitude"] = lon

    if subset_spec is not None:
        sl = slice(subset_spec.pixel_start, subset_spec.pixel_end)
        inputs = {
            name: val.isel(pixel=sl)
            if isinstance(val, xr.DataArray) and "pixel" in val.dims
            else val
            for name, val in inputs.items()
        }

    return inputs


def get_outputs(
    results: dict[str, xr.DataArray],
    output_specs: dict[str, IOSpec],
    stacked: bool = False,
) -> dict[str, xr.Dataset]:
    """Merge model results into per-frequency Datasets.

    Parameters
    ----------
    results:
        Dict returned by ``driver.execute()``, keyed by Hamilton node name.
    output_specs:
        Mapping from frequency string to ``IOSpec``.
        Typically ``parsed_config.output_specs``.
    stacked:
        If ``False`` (default) gridded results are unstacked to a ``(y, x)`` grid.
        If ``True`` the stacked ``pixel`` layout is kept (with the MultiIndex
        flattened to serialisable 1D coords) so that subset processes can write
        partial outputs that are reassembled later — see `unstack_pixel`.
    """
    transform = flatten_pixel_index if stacked else unstack_if_gridded
    out: dict[str, xr.Dataset] = {}
    for freq, spec in output_specs.items():
        suffix = "" if freq == "static" else f"_{freq}"
        # (Re-)assign names to all arrays to ensure merging succeeds
        arrays = [results[f"{var}{suffix}"].rename(var) for var in spec.vars]
        out[freq] = transform(xr.merge(arrays))
    return out


def save_outputs(
    output_datasets: dict[str, xr.Dataset],
    output_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
) -> None:
    """Write per-frequency Datasets to disk.

    Parameters
    ----------
    output_datasets:
        Dict returned by ``get_outputs()``.
    output_specs:
        Mapping from frequency string to ``IOSpec``.
        Typically ``parsed_config.output_specs``.
    subset_spec:
        If provided, the datasets are partial (a stacked pixel subset) and are
        written so independent processes don't collide: NetCDF outputs go to a
        uniquely-suffixed file, and Zarr outputs are region-written into a
        pre-created shared store.  CSV/Parquet outputs don't support subsetting.
    """
    for freq, ds in output_datasets.items():
        path = output_specs[freq].path
        if subset_spec is None:
            _save(ds, path)
            continue

        suffix = Path(path).suffix.lower()
        if suffix in (".nc", ".netcdf"):
            _save_netcdf(ds, _subset_path(path, subset_spec))
        elif suffix == ".zarr":
            _save_zarr_region(ds, path, subset_spec)
        else:
            raise ValueError(
                f"[subset] is only supported for NetCDF (.nc) and Zarr (.zarr) "
                f"outputs, but output '{freq}' has path '{path}'."
            )


def _pixel_template(inputs: dict[str, Any]) -> xr.Dataset:
    """Coordinate-only Dataset capturing the full stacked ``pixel`` grid.

    Derived from a representative pixel-bearing input so the level coordinates
    match exactly what subset ``run`` processes write.  The MultiIndex is
    flattened to serialisable 1D coords.
    """
    da_first = next(
        (
            v
            for v in inputs.values()
            if isinstance(v, xr.DataArray) and "pixel" in v.dims
        ),
        None,
    )
    if da_first is None:
        raise ValueError(
            "No pixel-bearing inputs found; cannot create a spatial output store."
        )
    reduced = da_first.isel({d: 0 for d in da_first.dims if d != "pixel"}, drop=True)
    skeleton = reduced.to_dataset(name="__tmp__").drop_vars("__tmp__")
    return flatten_pixel_index(skeleton)


def create_output_store(
    input_specs: dict[str, IOSpec],
    output_specs: dict[str, IOSpec],
    pixel_chunk: int | None = None,
    overwrite: bool = False,
) -> list[str]:
    """Pre-create empty stacked Zarr stores for parallel subset runs.

    For each Zarr output, build an all-NaN template with a 1D ``pixel`` layout
    matching what subset ``run`` processes region-write, then write only the
    metadata and coordinates (data arrays are dask-backed and deferred, so the
    full grid is never materialised).  NetCDF/CSV/Parquet outputs are skipped —
    they don't need a shared store.  Returns the list of store paths created.

    Refuses to clobber an existing store unless ``overwrite`` is set: re-running
    this after subset processes have populated a store would erase their data.
    """
    import dask.array as da

    zarr_specs = {
        freq: spec
        for freq, spec in output_specs.items()
        if Path(spec.path).suffix.lower() == ".zarr"
    }
    if not overwrite:
        existing = [
            spec.path for spec in zarr_specs.values() if Path(spec.path).exists()
        ]
        if existing:
            raise FileExistsError(
                f"Zarr store(s) already exist: {existing}. Re-creating them would "
                f"erase data already written by subset processes. Pass overwrite=True "
                f"(CLI: --overwrite) to recreate them from scratch."
            )

    inputs = load_inputs(input_specs)
    skeleton = _pixel_template(inputs)
    n_pixel = skeleton.sizes["pixel"]
    chunk = pixel_chunk or n_pixel

    created: list[str] = []
    for freq, spec in zarr_specs.items():
        coords = {name: skeleton.coords[name] for name in skeleton.coords}
        if freq == "static":
            shape, dims, chunks = (n_pixel,), ("pixel",), (chunk,)
        else:
            dates = inputs[f"dates_{freq}"]
            coords["time"] = dates
            shape = (len(dates), n_pixel)
            dims = ("time", "pixel")
            chunks = (len(dates), chunk)

        data_vars = {
            var: (dims, da.full(shape, np.nan, chunks=chunks, dtype="float64"))
            for var in spec.vars
        }
        template = xr.Dataset(data_vars=data_vars, coords=coords)
        template.to_zarr(spec.path, compute=False, consolidated=False, mode="w")
        created.append(spec.path)

    return created


def merge_subset_outputs(
    output_specs: dict[str, IOSpec],
    out: str | PathLike | None = None,
    out_suffix: str = "_gridded",
) -> list[str]:
    """Reassemble stacked subset outputs into gridded files.

    For NetCDF outputs, concatenates the per-subset ``*_p<start>-<end>.nc`` parts;
    for Zarr outputs, reads the shared store.  In both cases the ``pixel`` layout
    is unstacked back to a ``(y, x)`` grid.  Returns the list of files written.

    By default NetCDF results are written to the config's declared (un-suffixed)
    path and Zarr results to a sibling store with ``out_suffix`` appended.  Pass
    ``out`` to write to an explicit path instead; this is only valid when there is
    a single output section (otherwise the destination would be ambiguous).
    """
    if out is not None and len(output_specs) > 1:
        raise ValueError(
            f"'out' cannot be used with multiple [outputs.*] sections "
            f"({sorted(output_specs)}); the destination would be ambiguous. "
            f"Omit it to use the per-output defaults."
        )

    written: list[str] = []
    for freq, spec in output_specs.items():
        path = Path(spec.path)
        suffix = path.suffix.lower()

        if suffix in (".nc", ".netcdf"):
            parts = sorted(path.parent.glob(f"{path.stem}_p*{path.suffix}"))
            if not parts:
                raise FileNotFoundError(
                    f"No subset parts found matching "
                    f"'{path.stem}_p*{path.suffix}' in {path.parent}."
                )
            ds = xr.open_mfdataset(
                parts, combine="nested", concat_dim="pixel", decode_coords="all"
            )
            dest = Path(out) if out is not None else path
            unstack_pixel(ds).to_netcdf(dest, engine="netcdf4")
            written.append(str(dest))
        elif suffix == ".zarr":
            ds = xr.open_zarr(path, consolidated=False, decode_coords="all")
            dest = (
                Path(out)
                if out is not None
                else path.with_name(f"{path.stem}{out_suffix}{path.suffix}")
            )
            unstack_pixel(ds).to_zarr(dest, consolidated=False, mode="w")
            written.append(str(dest))
        else:
            raise ValueError(
                f"merge is only supported for NetCDF (.nc) and Zarr (.zarr) "
                f"outputs, but output '{freq}' has path '{spec.path}'."
            )

    return written


#: Output file extensions `save_outputs` knows how to write.
_SUPPORTED_OUTPUT_SUFFIXES: frozenset[str] = frozenset(
    {".nc", ".netcdf", ".zarr", ".csv", ".parquet", ".pq"}
)


def assert_output_paths_writable(
    output_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
) -> None:
    """Check every configured output destination would accept a write.

    Raises (before any computation) if a destination would fail at save time: an
    unsupported file extension, a missing or unwritable parent directory, a subset
    run targeting a Zarr store that has not been pre-created, or a subset run
    targeting an unsupported (CSV/Parquet) output. This mirrors the dispatch and
    guards in `save_outputs`, `_save` and `_save_zarr_region`, so a
    clean pass here means ``save_outputs`` will not reject the path. Used by
    ``breadboard run --dry-run``.
    """
    for freq, spec in output_specs.items():
        path = Path(spec.path)
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_OUTPUT_SUFFIXES:
            raise ValueError(
                f"output {freq!r} has unsupported file extension "
                f"{suffix or '(none)'!r} (path {spec.path!r}). Use one of "
                f"{sorted(_SUPPORTED_OUTPUT_SUFFIXES)}."
            )

        if subset_spec is not None:
            if suffix in (".nc", ".netcdf"):
                path = _subset_path(spec.path, subset_spec)
            elif suffix == ".zarr":
                if not Path(spec.path).exists():
                    raise FileNotFoundError(
                        f"Zarr store {spec.path!r} for output {freq!r} does not exist. "
                        f"Create it once before subset runs with "
                        f"`breadboard create-store <config>`."
                    )
                continue  # store exists; the region write targets it directly
            else:
                raise ValueError(
                    f"[subset] is only supported for NetCDF (.nc) and Zarr (.zarr) "
                    f"outputs, but output {freq!r} has path {spec.path!r}."
                )

        parent = path.parent
        if not parent.is_dir():
            raise FileNotFoundError(
                f"output {freq!r} parent directory {str(parent)!r} does not exist "
                f"(path {spec.path!r})."
            )
        if not os.access(parent, os.W_OK):
            raise PermissionError(
                f"output {freq!r} parent directory {str(parent)!r} is not writable "
                f"(path {spec.path!r})."
            )


def get_final_vars(output_specs: dict[str, IOSpec]) -> list[str]:
    """Build Hamilton node names from output specifications.

    Converts per-frequency variable lists into the flat list of node names
    expected by ``driver.execute(final_vars=...)``.

    Parameters
    ----------
    output_specs:
        Mapping from frequency string to ``IOSpec``.  Pass the full
        ``parsed_config.output_specs`` for all outputs, or a subset
        (e.g. ``{"monthly": parsed.output_specs["monthly"]}``) to
        request a single frequency.

    Returns
    -------
    list[str]
        Flat list of Hamilton node names (e.g. ``["gpp_daily", ...]``).
    """
    return [
        var if freq == "static" else f"{var}_{freq}"
        for freq, spec in output_specs.items()
        for var in spec.vars
    ]
