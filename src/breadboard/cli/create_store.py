"""Pre-create empty Zarr output stores for parallel subset runs."""

from pathlib import Path
from typing import Annotated

import typer

from ..config import load_config
from ..io import create_output_store

app = typer.Typer(help="Pre-create empty Zarr output stores for parallel subset runs.")


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

    Run this once before launching independent ``breadboard run`` processes that
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
