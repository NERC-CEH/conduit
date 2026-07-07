"""``conduit gridded`` CLI: parallel Zarr store creation and subset merge."""

from pathlib import Path
from typing import Annotated

import typer

from ..config import load_config
from .io import create_output_store, merge_subset_outputs

app = typer.Typer(
    help="Gridded (CRS/pixel) parallel Zarr I/O: pre-create stores and merge subsets."
)


def _require_geo_extra() -> None:
    """Fail fast with an install hint if the optional ``geo`` extra is absent.

    The gridded commands reproject through ``rioxarray``/``pyproj``. Checking at
    the group level means ``conduit gridded <cmd>`` reports one clear, actionable
    message up front, rather than a deep ``ImportError`` part way through a run.
    """
    from importlib.util import find_spec

    missing = [pkg for pkg in ("rioxarray", "pyproj") if find_spec(pkg) is None]
    if missing:
        typer.echo(
            f"The 'conduit gridded' commands require the optional 'geo' extra "
            f"(missing: {', '.join(missing)}). Install it with "
            f"`pip install conduit[geo]`.",
            err=True,
        )
        raise typer.Exit(code=1)


@app.callback()
def gridded() -> None:
    """Validate the optional geospatial dependencies before any gridded command."""
    _require_geo_extra()


@app.command()
def create_store(
    config_file: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    pixel_chunk: Annotated[
        int | None,
        typer.Option(
            "--pixel-chunk",
            help="Pixel chunk size for the store. Subset boundaries must align to "
            "this value. Defaults to [blocking].block_size, or the full grid.",
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Recreate stores that already exist. This erases any data already "
            "written into them by subset runs.",
        ),
    ] = False,
) -> None:
    """Create empty Zarr stores so subset runs can region-write concurrently.

    Run this once before launching independent ``conduit run`` processes that
    each handle a different ``[subset]`` of the same grid and write to a shared
    Zarr store.
    """
    parsed = load_config(config_file)

    chunk = pixel_chunk
    if chunk is None and parsed.blocking_spec is not None:
        chunk = parsed.blocking_spec.block_size

    created = create_output_store(
        parsed.input_specs, parsed.output_specs, pixel_chunk=chunk, overwrite=overwrite
    )

    if not created:
        typer.echo("No Zarr outputs in config; nothing to create.")
        return
    for path in created:
        typer.echo(f"Created store: {path}")


@app.command()
def merge(
    config_file: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            "-o",
            help="Explicit destination for the merged, gridded output. Only valid "
            "with a single output section. Defaults to the config's path for "
            "NetCDF and a sibling gridded store for Zarr.",
        ),
    ] = None,
) -> None:
    """Merge per-subset outputs back into a single gridded file per frequency.

    NetCDF parts (``*_p<start>-<end>.nc``) are concatenated and written to the
    config's declared path; a shared Zarr store is unstacked into a sibling
    ``*_gridded.zarr`` store.  Use ``--out`` to override the destination.
    """
    parsed = load_config(config_file)
    written = merge_subset_outputs(parsed.output_specs, out=out)

    if not written:
        typer.echo("No mergeable outputs in config.")
        return
    for path in written:
        typer.echo(f"Wrote gridded output: {path}")
