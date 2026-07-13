"""Gridded (CRS/pixel) I/O: the optional geospatial + parallel-Zarr layer.

This is the domain-specific counterpart to the domain-agnostic `conduit.io`. It
owns everything to do with the stacked ``pixel`` model:

- **CRS-aware stacking**: collapsing a ``(y, x)`` grid into a 1-D ``pixel``
  dimension and reconstructing it, plus computing ``latitude``/``longitude`` by
  reprojecting to EPSG:4326 (`stack_if_gridded`, `unstack_pixel`, `compute_lat_lon`);
- **parallel Zarr I/O**: pre-creating a shared stacked Zarr store and region-writing
  independent ``[subset]`` slices into it, then reassembling
  (`create_output_store`, `save_zarr_region`, `merge_subset_outputs`).

`conduit.io` imports from here **lazily**, only when an input carries CRS metadata
or a ``[subset]`` is configured, so non-gridded pipelines never touch this module.
The optional ``geo`` extra (``rioxarray``/``pyproj``) is imported lazily *within*
the CRS functions (`_ensure_rio`), so importing this module itself is cheap and
dependency-free — only actually using a CRS path requires the extra.
"""

from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from ..config import IOSpec, ParsedConfig, SubsetSpec
from .spatial import stack_spatial_dims


class MisalignedGridError(Exception):
    """Raised when two datasets do not share a common CRS and coordinates."""


def _ensure_rio() -> None:
    """Import rioxarray (registering the ``.rio`` accessor) or raise a clear error.

    The geospatial layer (CRS-aware stacking + lat/lon reprojection) is optional;
    ``rioxarray``/``pyproj`` are only needed when CRS-bearing inputs are present.
    """
    try:
        import rioxarray as rioxarray  # registers the .rio accessor
    except ImportError as exc:  # pragma: no cover - only hit without the extra
        raise ImportError(
            "geospatial (CRS-bearing) inputs require the optional 'geo' extra; "
            "install it with `pip install conduit[geo]`."
        ) from exc


def has_crs(ds: xr.Dataset) -> bool:
    """Cheaply detect CRS metadata without importing rioxarray.

    Looks for the markers CF/rioxarray round-trips through NetCDF/Zarr: a ``crs``
    global attribute, a ``spatial_ref`` grid-mapping coordinate, or a per-variable
    ``grid_mapping`` attribute. Used to decide whether to activate the (lazy)
    geospatial path, so non-gridded pipelines never touch rioxarray/pyproj.
    """
    if ds.attrs.get("crs") or "spatial_ref" in ds.coords:
        return True
    return any("grid_mapping" in da.attrs for da in ds.data_vars.values())


# ---------------------------------------------------------------------------
# Stacking / unstacking the pixel dimension
# ---------------------------------------------------------------------------


def stack_if_gridded(ds: xr.Dataset) -> xr.Dataset:
    """Stack (y, x) to pixel if CRS-bearing 2D grid; pass through otherwise."""
    if "pixel" in ds.dims:
        return ds
    _ensure_rio()
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
# Grid computation (CRS -> stacked latitude/longitude)
# ---------------------------------------------------------------------------


def _check_common_grid(
    ds1: xr.Dataset,
    ds2: xr.Dataset,
    label1: str = "ds1",
    label2: str = "ds2",
    atol: float = 1e-6,
) -> None:
    """Raise MisalignedGridError if CRS and coordinates do not match."""
    _ensure_rio()
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


def compute_lat_lon(
    spatial_datasets: dict[str, xr.Dataset],
) -> tuple[xr.DataArray, xr.DataArray]:
    """Compute stacked latitude and longitude DataArrays from CRS-bearing datasets."""
    from pyproj import Transformer

    _ensure_rio()
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
# Parallel Zarr I/O: subset region writes + store creation + merge
# ---------------------------------------------------------------------------


def subset_suffix(spec: SubsetSpec) -> str:
    """Filename suffix that uniquely identifies a pixel subset, e.g. ``_p0-500``."""
    return f"_p{spec.pixel_start}-{spec.pixel_end}"


def subset_path(path: str, spec: SubsetSpec) -> Path:
    """Insert the subset suffix before the file extension."""
    p = Path(path)
    return p.with_name(f"{p.stem}{subset_suffix(spec)}{p.suffix}")


def _assert_coords_match(ds: xr.Dataset, store: xr.Dataset, path: str) -> None:
    """Raise unless ``ds``'s non-``pixel`` coordinates match the store's exactly.

    The ``pixel`` dimension is excluded: it is the one axis a subset run *does*
    partition, so its coordinate is legitimately a slice of the store's.
    """
    for dim in ds.dims:
        if dim == "pixel" or dim not in ds.coords:
            continue
        if dim not in store.coords:
            raise ValueError(
                f"Zarr store '{path}' has no '{dim}' coordinate, but the data being "
                f"written into it does. Re-create the store from the current config "
                f"with `conduit gridded create-store`."
            )
        ours, theirs = ds.indexes[dim], store.indexes[dim]
        if len(ours) != len(theirs) or not (ours == theirs).all():
            raise ValueError(
                f"'{dim}' coordinate does not match Zarr store '{path}': the store "
                f"has {len(theirs)} value(s) ({theirs[0]} … {theirs[-1]}), the data "
                f"being written has {len(ours)} ({ours[0]} … {ours[-1]}). Region "
                f"writes do not write coordinates, so this would silently mislabel "
                f"the store. Re-create it from the current config with "
                f"`conduit gridded create-store --overwrite`."
            )


def save_zarr_region(ds: xr.Dataset, path: str, spec: SubsetSpec) -> None:
    """Write a pixel subset into an existing Zarr store via a region write.

    The store must already exist (see ``conduit gridded create-store``).  Only the
    data variables are written; coordinates already live in the store, and writing
    them in region mode is both unnecessary and disallowed by xarray.

    Because the coordinates are *not* written, they are checked instead: a store
    whose non-``pixel`` coordinates (notably ``time``) disagree with the data being
    written into it would be silently mislabelled. `_assert_coords_match` turns that
    into an error at the write, rather than a wrong answer at the merge.
    """
    store = Path(path)
    if not store.exists():
        raise FileNotFoundError(
            f"Zarr store '{path}' does not exist. Create it once before running "
            f"subset processes with: `conduit gridded create-store <config>`."
        )

    template = xr.open_zarr(store, consolidated=False)
    _assert_coords_match(ds, template, path)
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
    parsed: ParsedConfig,
    pixel_chunk: int | None = None,
    overwrite: bool = False,
) -> list[str]:
    """Pre-create empty stacked Zarr stores for parallel subset runs.

    For each Zarr output, build an all-NaN template with a 1D ``pixel`` layout
    matching what subset ``run`` processes region-write, then write only the
    metadata and coordinates (data arrays are dask-backed and deferred, so the
    full grid is never materialised).  NetCDF/CSV/Parquet outputs are skipped —
    they don't need a shared store.  Returns the list of store paths created.

    The store's non-``pixel`` axes (notably ``time``) are **computed from the
    outputs**, by running the pipeline over a single pixel and reading the real
    coordinates, dims and dtype off the result. That makes the store's layout what
    the subset runs will actually write *by construction* — the store cannot be
    mislabelled, and a derived axis (a ``[[resample]]``'s weekly time axis, say)
    needs no input file to have that axis already. Nothing is inferred from a
    section's label.

    Refuses to clobber an existing store unless ``overwrite`` is set: re-running
    this after subset processes have populated a store would erase their data.
    """
    import dask.array as da

    from ..dag.driver import build_driver
    from ..io import get_final_vars, load_inputs, subset_inputs, var_mapping

    zarr_specs = {
        label: spec
        for label, spec in parsed.output_specs.items()
        if Path(spec.path).suffix.lower() == ".zarr"
    }
    if not zarr_specs:
        return []
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

    inputs = load_inputs(parsed.input_specs)
    skeleton = _pixel_template(inputs)
    n_pixel = skeleton.sizes["pixel"]
    chunk = pixel_chunk or n_pixel

    # Probe the pipeline over one pixel to learn each output's true layout. Caching
    # is deliberately not enabled: the probe is an implementation detail of building
    # the store and should neither consult nor populate the user's cache.
    probe_inputs = subset_inputs(inputs, SubsetSpec(pixel_start=0, pixel_end=1))
    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
    )
    probe = dr.execute(
        get_final_vars(zarr_specs),  # type: ignore[reportArgumentType]
        inputs=probe_inputs,
    )

    created: list[str] = []
    for label, spec in zarr_specs.items():
        data_vars = {}
        coords = {name: skeleton.coords[name] for name in skeleton.coords}
        for node, file_var in var_mapping(label, spec).items():
            probed = probe[node]
            # Take dims (and their order), dtype and coords from what the pipeline
            # actually produced; only ``pixel`` is resized to the full grid.
            dims = tuple(str(d) for d in probed.dims)
            shape = tuple(n_pixel if d == "pixel" else probed.sizes[d] for d in dims)
            chunks = tuple(chunk if d == "pixel" else probed.sizes[d] for d in dims)
            fill = da.full(shape, np.nan, chunks=chunks, dtype=probed.dtype)
            data_vars[file_var] = (dims, fill)
            coords |= {
                str(d): probed.coords[d]
                for d in dims
                if d != "pixel" and d in probed.coords
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
