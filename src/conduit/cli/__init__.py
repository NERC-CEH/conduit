"""CLI subcommands for conduit."""

import typer

from ..gridded.cli import app as gridded_app
from .graph import app as graph_app
from .run import app as run_app
from .version import app as version_app

app = typer.Typer(
    help="Command-line interface for the conduit framework.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(graph_app)
app.add_typer(run_app)
# Gridded (CRS/pixel) parallel-Zarr commands are nested: `conduit gridded <cmd>`.
app.add_typer(gridded_app, name="gridded")
app.add_typer(version_app)


def main() -> None:
    """Entry point for the conduit CLI."""
    app()
