"""I/O functions for loading inputs and saving outputs outside the Hamilton DAG."""

import os
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from .formats import (
    FORMATS,
    Format,
    dataset_to_frame,
    format_for,
    read_in_group,
    write_frame,
    write_in_group,
)
from .specs import IOSpec, SubsetSpec


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
    - ``vars is None`` — an input section that omits ``vars`` — maps every name in
      ``available`` (the file's variables) through the suffix.
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
    return read_in_group(path, "dataset")


def load_timeseries(path: str | PathLike) -> xr.Dataset:
    """Load a single-point time series from CSV or Parquet.

    Returns a Dataset with dims (time, pixel) where pixel has coordinate value 0.
    """
    return read_in_group(path, "table")


def load_static(path: str | PathLike) -> xr.Dataset:
    """Load single-point static inputs from JSON or TOML.

    Returns a Dataset with dim (pixel,) where pixel has coordinate value 0.
    """
    return read_in_group(path, "scalar")


def _load_raw(path: str) -> xr.Dataset:
    """Open any supported input file (`conduit.formats` picks the reader)."""
    fmt = format_for(path)
    assert fmt.read is not None  # every registered format is readable
    return fmt.read(path)


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
    return dataset_to_frame(ds)


def save_timeseries(df: pd.DataFrame, path: str | PathLike) -> None:
    """Save a DataFrame to CSV or Parquet, auto-detected by extension."""
    write_frame(df, path)


def _save_netcdf(ds: xr.Dataset, path: str | PathLike) -> None:
    """Save a dataset to NetCDF or Zarr based on extension."""
    write_in_group(ds, path, "dataset")


def _save(ds: xr.Dataset, path: str) -> None:
    """Write ``ds`` to any writable format (`conduit.formats` picks the writer)."""
    fmt = format_for(path, writable=True)
    assert fmt.write is not None
    fmt.write(ds, path)


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
) -> dict[str, xr.DataArray]:
    """Load all configured inputs and return them as a flat dict of named DataArrays.

    Node names are formed from each section's variables and its
    `effective_suffix` (``{var}{suffix}``, e.g. ``temperature_daily``, or
    ``elevation`` for a section that sets ``suffix = ""``). Section labels are
    otherwise inert — nothing is inferred from ``daily``/``weekly``/``monthly``; an
    input's frequency is validated only where a consumer declares a
    `xarray_annotated.temporal.Freq` contract for it.

    The geospatial layer (CRS-aware ``(y, x)`` → ``pixel`` stacking plus computed
    ``latitude``/``longitude``) is **opt-in**: it activates only when an input carries
    CRS metadata (see `conduit.gridded`). Pass ``geospatial=True``/``False`` to force
    it on or off.

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
    from .gridded.io import (  # lazy: optional geo extra (see conduit.gridded)
        compute_lat_lon,
        has_crs,
        stack_if_gridded,
    )

    inputs: dict[str, xr.DataArray] = {}
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


def subset_inputs(
    inputs: dict[str, xr.DataArray], subset_spec: SubsetSpec
) -> dict[str, xr.DataArray]:
    """Slice every input carrying ``subset_spec.dim`` to that spec's range.

    Inputs without the dimension (a static scalar, say) pass through untouched.
    Shared by `load_inputs` and by `conduit.gridded.io.create_output_store`, which
    reuses it to derive a single-pixel probe of the pipeline.
    """
    dim = subset_spec.dim
    sl = slice(subset_spec.start, subset_spec.stop)
    return {
        name: val.isel({dim: sl}) if dim in val.dims else val
        for name, val in inputs.items()
    }


def get_outputs(
    results: dict[str, xr.DataArray],
    output_specs: dict[str, IOSpec],
    stacked: bool = False,
) -> dict[str, xr.Dataset]:
    """Merge model results into one Dataset per output section.

    Parameters
    ----------
    results:
        Dict returned by ``driver.execute()``, keyed by Hamilton node name.
    output_specs:
        Mapping from section label to ``IOSpec``.
        Typically ``parsed_config.output_specs``.
    stacked:
        If ``False`` (default) gridded results are unstacked to a ``(y, x)`` grid.
        If ``True`` the stacked ``pixel`` layout is kept (with the MultiIndex
        flattened to serialisable 1D coords) so that subset processes can write
        partial outputs that are reassembled later — see `unstack_pixel`.
    """
    from .gridded.io import (  # lazy: optional geo extra
        flatten_pixel_index,
        unstack_if_gridded,
    )

    transform = flatten_pixel_index if stacked else unstack_if_gridded
    out: dict[str, xr.Dataset] = {}
    for label, spec in output_specs.items():
        # (Re-)assign the file variable name to each array so merging succeeds.
        arrays = [
            results[node].rename(file_var)
            for node, file_var in var_mapping(label, spec).items()
        ]
        out[label] = transform(xr.merge(arrays))
    return out


def save_outputs(
    output_datasets: dict[str, xr.Dataset],
    output_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
    provenance: dict[str, str] | None = None,
) -> None:
    """Write each output section's Dataset to disk.

    Parameters
    ----------
    output_datasets:
        Dict returned by ``get_outputs()``.
    output_specs:
        Mapping from section label to ``IOSpec``.
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
    for label, ds in output_datasets.items():
        path = output_specs[label].path
        if provenance:
            ds = ds.assign_attrs(provenance)
        if subset_spec is None:
            _save(ds, path)
            continue

        from .gridded.io import save_zarr_region, subset_path  # lazy: geo extra

        fmt = _subset_format(path, label)
        if fmt.needs_store:
            save_zarr_region(ds, path, subset_spec)
        else:
            _save_netcdf(ds, subset_path(path, subset_spec))


def _subset_format(path: str, label: str) -> "Format":
    """Return the `Format` for a ``[subset]`` output, or raise if it cannot be one."""
    fmt = format_for(path, writable=True)
    if not fmt.supports_subset:
        raise ValueError(
            f"[subset] is only supported for "
            f"{[s for f in FORMATS if f.supports_subset for s in f.suffixes]} "
            f"outputs, but output {label!r} has path {path!r}."
        )
    return fmt


def assert_output_paths_writable(
    output_specs: dict[str, IOSpec],
    subset_spec: SubsetSpec | None = None,
) -> None:
    """Check every configured output destination would accept a write.

    Raises (before any computation) if a destination would fail at save time: an
    unsupported file extension, a missing or unwritable parent directory, a subset
    run targeting a Zarr store that has not been pre-created, or a subset run
    targeting a format that cannot be partially written (CSV/Parquet). Both this and
    `save_outputs` derive those rules from `conduit.formats`, so a clean pass here
    means ``save_outputs`` will not reject the path. Used by ``conduit run
    --dry-run``.
    """
    for label, spec in output_specs.items():
        path = Path(spec.path)
        # Raises with the full list of writable formats for an unknown extension.
        format_for(spec.path, writable=True)

        if subset_spec is not None:
            fmt = _subset_format(spec.path, label)
            if fmt.needs_store:
                if not Path(spec.path).exists():
                    raise FileNotFoundError(
                        f"Zarr store {spec.path!r} for output {label!r} does not "
                        f"exist. Create it once before subset runs with "
                        f"`conduit gridded create-store <config>`."
                    )
                continue  # store exists; the region write targets it directly
            from .gridded.io import subset_path  # lazy: geo extra

            path = subset_path(spec.path, subset_spec)

        parent = path.parent
        if not parent.is_dir():
            raise FileNotFoundError(
                f"output {label!r} parent directory {str(parent)!r} does not exist "
                f"(path {spec.path!r})."
            )
        if not os.access(parent, os.W_OK):
            raise PermissionError(
                f"output {label!r} parent directory {str(parent)!r} is not writable "
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

    Converts each section's variable list into the flat list of node names
    expected by ``driver.execute(final_vars=...)``.

    Parameters
    ----------
    output_specs:
        Mapping from section label to ``IOSpec``.  Pass the full
        ``parsed_config.output_specs`` for all outputs, or a subset
        (e.g. ``{"monthly": parsed.output_specs["monthly"]}``) to
        request a single section's nodes.

    Returns
    -------
    list[str]
        Flat list of Hamilton node names (e.g. ``["gpp_daily", ...]``).
    """
    names: list[str] = []
    seen: set[str] = set()
    for label, spec in output_specs.items():
        for node in var_mapping(label, spec):
            if node in seen:
                raise ValueError(
                    f"output node name {node!r} (from [outputs.{label}]) is requested "
                    f"by more than one output section. Give each output a distinct "
                    f"node name (suffix or explicit mapping)."
                )
            seen.add(node)
            names.append(node)
    return names
