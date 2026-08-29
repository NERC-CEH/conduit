"""The typer application: the root callback, its options, and the subcommands.

Lives beside `conduit.cli.main` rather than in ``conduit/cli/__init__.py`` so that
importing `conduit.cli` needs no typer. That is what lets the ``conduit`` console
script exist in an install without the ``cli`` extra and answer with an install
hint instead of an ImportError traceback.
"""

from typing import Annotated

import typer

from .._version import __version__
from ..gridded.cli import app as gridded_app
from .graph import app as graph_app
from .run import app as run_app

app = typer.Typer(
    help="Command-line interface for the conduit framework.",
    context_settings={"help_option_names": ["-h", "--help"]},
    # `main` renders ConduitError itself; typer's traceback would bury the message.
    pretty_exceptions_enable=False,
)


def _show_version(value: bool) -> None:
    """Print the installed version and exit.

    Attached to `--version` as an *eager* option callback, so it runs before the
    subcommand is resolved and `conduit --version` answers without a command.
    """
    if value:
        typer.echo(f"conduit version {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=_show_version,
            is_eager=True,
            help="Show the installed version of conduit and exit.",
        ),
    ] = False,
) -> None:
    """Run before any subcommand.

    Typer allows one root callback, so every app-wide option hangs off this one.
    `--version` is handled by its own eager callback, which exits before this runs.
    """


app.add_typer(graph_app)
app.add_typer(run_app)
# Gridded (CRS/pixel) parallel-Zarr commands are nested: `conduit gridded <cmd>`.
app.add_typer(gridded_app, name="gridded")
