"""I/O functions for loading inputs and saving outputs outside the Hamilton DAG."""

import os
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from .config import IOSpec, SubsetSpec


def effective_suffix(label: str, spec: IOSpec) -> str:
    """Resolve the node-name suffix for an input/output section.

    Honours an explicit ``IOSpec.suffix`` when set; otherwise defaults to
    ``_<label>``. This is the single place the frequency-suffix naming
    convention is applied, so it is opt-out (set ``suffix = ""`` for bare
    names) and not a hard requirement.
    """
    if spec.suffix is not None:
        return spec.suffix
    return f"_{label}"


def var_mapping(
    label: str, spec: IOSpec, available: "list[str] | None" = None
) -> dict[str, str]:
    """Resolve a section's ``node_name -> file_var`` mapping.

    The single place the two `IOSpec.vars` forms are reconciled:

    - a **mapping** ``{node_name: file_var}`` is used verbatim (suffix-free);
    - a **list** yields ``{f"{var}{suffix}": var}`` using `effective_suffix`;
    - ``vars is None`` (programmatic "load everything") maps every name in
      ``available`` through the suffix.
    """
    if isinstance(spec.vars, dict):
        return dict(spec.vars)
    suffix = effective_suffix(label, spec)
    names = list(available or []) if spec.vars is None else spec.vars
    return {f"{var}{suffix}": var for var in names}


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
# Internal helpers: datetime handling
# ---------------------------------------------------------------------------


def time_dims(obj: xr.Dataset | xr.DataArray) -> list[str]:
    """Names of ``obj``'s dimensions whose coordinate is datetime-like.

    A dimension counts as temporal when its dimension coordinate is a NumPy
    ``datetime64`` array or a cftime index (``CFTimeIndex``). Scalar or
    non-dimension datetime coordinates do not count — only true dimensions.

    The single time-axis detector. It underpins the "at most one time dimension
    per input dataset" invariant enforced in `load_inputs`, and is what lets the
    rest of conduit find *the* time axis without hardcoding the name ``time`` —
    see `conduit.transforms.resample` and `conduit.checks`.
    """
    dims: list[str] = []
    for dim in obj.dims:
        coord = obj.coords.get(dim)
        if coord is not None and (
            np.issubdtype(coord.dtype, np.datetime64)
            or isinstance(obj.indexes.get(dim), xr.CFTimeIndex)
        ):
            dims.append(str(dim))
    return dims


def sole_time_dim(obj: xr.Dataset | xr.DataArray, what: str) -> str:
    """Return the name of ``obj``'s one time dimension, or raise.

    ``what`` names the object in the error message (e.g. a node name). Callers
    that need *the* time axis go through this rather than assuming ``"time"``.
    """
    dims = time_dims(obj)
    if len(dims) == 1:
        return dims[0]
    if not dims:
        raise ValueError(
            f"{what} has no time dimension (no dimension coordinate is "
            f"datetime-like); its dimensions are {list(obj.dims)}."
        )
    raise ValueError(
        f"{what} has multiple time dimensions {sorted(dims)}; conduit cannot tell "
        f"which is meant. Merge, select, or rename the extra datetime axis."
    )


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_raw_datasets(input_specs: dict[str, IOSpec]) -> dict[str, xr.Dataset]:
    """Open every configured input as a raw ``Dataset`` (pre-stack, pre-subset).

    The single source of truth for "load the raw input files": `load_inputs`
    calls it internally, and the input-checks pre-flight calls it too. Opens are
    lazy (metadata only), so calling it twice per run is cheap.
    """
    return {label: _load_raw(spec.path) for label, spec in input_specs.items()}


def load_inputs(
    input_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
    geospatial: bool | None = None,
) -> dict[str, Any]:
    """Load all configured inputs and return them as a flat dict of named DataArrays.

    Node names are formed from each section's variables and its
    `effective_suffix` (``{var}{suffix}``, e.g. ``temperature_daily``, or
    ``elevation`` for a section that sets ``suffix = ""``). Section labels are
    otherwise inert — nothing is inferred from ``daily``/``weekly``/``monthly``; an
    input's frequency is validated only where a consumer declares a
    `xarray_annotated.temporal.Freq` contract for it.

    The geospatial layer (CRS-aware ``(y, x)`` → ``pixel`` stacking plus computed
    ``latitude``/``longitude``) is **opt-in** and lazily loaded: it activates only
    when an input carries CRS metadata, importing the optional ``geo`` extra
    (``rioxarray``/``pyproj``) at that point. Non-gridded pipelines never touch
    those dependencies. Pass ``geospatial=True``/``False`` to force it on or off.

    Parameters
    ----------
    input_specs:
        Mapping from section label to ``IOSpec`` (path, vars, suffix).
        Typically ``parsed_config.input_specs``.
    subset_spec:
        If provided, slice all pixel-bearing inputs to the specified pixel
        range after loading.  Typically ``parsed_config.subset_spec``.
    geospatial:
        Force the geospatial path on (``True``) or off (``False``). When ``None``
        (default) it is auto-detected from the presence of CRS metadata.
    """
    # The gridded (CRS/pixel) layer is optional and domain-specific; import it
    # lazily so non-gridded pipelines never touch it. `has_crs` is a cheap,
    # dependency-free CF-metadata check; the stacking/reprojection it guards is
    # what pulls the optional `geo` extra, and only when CRS metadata is present.
    from .gridded.io import compute_lat_lon, has_crs, stack_if_gridded

    inputs: dict[str, Any] = {}
    raw_datasets = load_raw_datasets(input_specs)

    # Invariant: at most one time dimension per input dataset. A second datetime
    # axis makes "the time dimension" ambiguous (for validation, resampling, and
    # output-store construction), so reject it up front with a clear message.
    for label, ds in raw_datasets.items():
        tdims = time_dims(ds)
        if len(tdims) > 1:
            raise ValueError(
                f"[inputs.{label}] has multiple time dimensions {sorted(tdims)}; "
                f"conduit requires at most one time dimension per input dataset. "
                f"Merge, select, or rename the extra datetime axis before loading."
            )

    if geospatial is None:
        geospatial = any(has_crs(ds) for ds in raw_datasets.values())

    for label, spec in input_specs.items():
        ds_raw = raw_datasets[label]
        ds = stack_if_gridded(ds_raw) if geospatial else ds_raw
        mapping = var_mapping(label, spec, available=[str(v) for v in ds.data_vars])
        for node_name, file_var in mapping.items():
            if node_name in inputs:
                raise ValueError(
                    f"input node name {node_name!r} (from [inputs.{label}]) collides "
                    f"with an already-loaded input. Use distinct suffixes or an "
                    f"explicit {{node_name = file_var}} mapping to disambiguate."
                )
            inputs[node_name] = ds[file_var]

    if geospatial:
        spatial = {label: ds for label, ds in raw_datasets.items() if has_crs(ds)}
        if spatial:
            lat, lon = compute_lat_lon(spatial)
            inputs["latitude"] = lat
            inputs["longitude"] = lon

    if subset_spec is not None:
        inputs = subset_inputs(inputs, subset_spec)

    return inputs


def subset_inputs(inputs: dict[str, Any], subset_spec: SubsetSpec) -> dict[str, Any]:
    """Slice every pixel-bearing input to ``subset_spec``'s pixel range.

    Inputs without a ``pixel`` dimension pass through untouched. Shared by
    `load_inputs` and by `conduit.gridded.io.create_output_store`, which reuses it
    to derive a single-pixel probe of the pipeline.
    """
    sl = slice(subset_spec.pixel_start, subset_spec.pixel_end)
    return {
        name: val.isel(pixel=sl)
        if isinstance(val, xr.DataArray) and "pixel" in val.dims
        else val
        for name, val in inputs.items()
    }


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
    from .gridded.io import flatten_pixel_index, unstack_if_gridded

    transform = flatten_pixel_index if stacked else unstack_if_gridded
    out: dict[str, xr.Dataset] = {}
    for freq, spec in output_specs.items():
        # (Re-)assign the file variable name to each array so merging succeeds.
        arrays = [
            results[node].rename(file_var)
            for node, file_var in var_mapping(freq, spec).items()
        ]
        out[freq] = transform(xr.merge(arrays))
    return out


def save_outputs(
    output_datasets: dict[str, xr.Dataset],
    output_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
    provenance: dict[str, str] | None = None,
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
    provenance:
        Optional attributes stamped onto every written dataset (e.g. the config
        text and its hash), so a store is self-describing. Ignored for the
        subset/Zarr-region path, whose store attrs are written once by
        ``create-store``.
    """
    for freq, ds in output_datasets.items():
        path = output_specs[freq].path
        if provenance:
            ds = ds.assign_attrs(provenance)
        if subset_spec is None:
            _save(ds, path)
            continue

        from .gridded.io import save_zarr_region, subset_path

        suffix = Path(path).suffix.lower()
        if suffix in (".nc", ".netcdf"):
            _save_netcdf(ds, subset_path(path, subset_spec))
        elif suffix == ".zarr":
            save_zarr_region(ds, path, subset_spec)
        else:
            raise ValueError(
                f"[subset] is only supported for NetCDF (.nc) and Zarr (.zarr) "
                f"outputs, but output '{freq}' has path '{path}'."
            )


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
    ``conduit run --dry-run``.
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
                from .gridded.io import subset_path

                path = subset_path(spec.path, subset_spec)
            elif suffix == ".zarr":
                if not Path(spec.path).exists():
                    raise FileNotFoundError(
                        f"Zarr store {spec.path!r} for output {freq!r} does not exist. "
                        f"Create it once before subset runs with "
                        f"`conduit gridded create-store <config>`."
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


def auxiliary_input_names(inputs: dict[str, Any]) -> set[str]:
    """Names of auto-derived inputs `load_inputs` emits that nodes needn't consume.

    The geospatial ``latitude`` / ``longitude`` arrays are computed from the input
    files' CRS rather than read from them, so a pipeline that doesn't consume them
    is not misconfigured. The wiring check
    (`conduit.dag.wiring_check.check_wiring`) excludes these from its "unused
    input" diagnostic.
    """
    return {"latitude", "longitude"} & set(inputs)


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
    names: list[str] = []
    seen: set[str] = set()
    for freq, spec in output_specs.items():
        for node in var_mapping(freq, spec):
            if node in seen:
                raise ValueError(
                    f"output node name {node!r} (from [outputs.{freq}]) is requested "
                    f"by more than one output section. Give each output a distinct "
                    f"node name (suffix or explicit mapping)."
                )
            seen.add(node)
            names.append(node)
    return names
