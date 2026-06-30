"""Show the installed version of breadboard."""

import typer

from .._version import __version__

app = typer.Typer(help="Show the installed version of breadboard.")


@app.command()
def version() -> None:
    """Show the installed version of breadboard."""
    typer.echo(f"breadboard version {__version__}")
