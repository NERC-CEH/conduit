"""Reassemble stacked subset outputs into gridded files."""

from pathlib import Path
from typing import Annotated

import typer

from ..config import load_config
from ..io import merge_subset_outputs

app = typer.Typer(help="Reassemble stacked subset outputs into gridded files.")


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
