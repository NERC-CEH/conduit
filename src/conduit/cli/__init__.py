"""CLI subcommands for conduit."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from .._version import __version__
from ..errors import ConduitError
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


def _prepare_import_path() -> None:
    """Make modules under the working directory importable by `_import_path`.

    A config's `_import_path` is resolved as an ordinary Python import, so
    `conduit` must be able to find user modules that are not installed. Console
    scripts do not put the working directory on `sys.path` (only `python -m` and
    `python script.py` do), so conduit adds it here.

    It is *appended*, not prepended: an installed distribution of the same name
    always wins, so a stray `xarray.py` in the working directory cannot shadow
    the real one. `PYTHONSAFEPATH=1` disables this, as it does elsewhere.
    """
    if sys.flags.safe_path:
        return
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.append(cwd)


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

    Typer allows one root callback, so every app-wide concern hangs off this one:
    it declares the app-wide options and does the setup each subcommand needs. Each
    concern lives in its own function; this body is only the wiring. `--version` is
    handled by its own eager callback, which exits before this runs.
    """
    _prepare_import_path()


app.add_typer(graph_app)
app.add_typer(run_app)
# Gridded (CRS/pixel) parallel-Zarr commands are nested: `conduit gridded <cmd>`.
app.add_typer(gridded_app, name="gridded")


def main() -> None:
    """Entry point for the conduit CLI.

    A `ConduitError` is a condition conduit anticipated and wrote a message for, so
    the message is all a user needs; the frames above it are conduit's own call
    stack. Every other exception propagates with its traceback, because that is a
    bug and the frames are the point.
    """
    try:
        app()
    except ConduitError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
