"""Show the installed version of conduit."""

import typer

from .._version import __version__

app = typer.Typer(help="Show the installed version of conduit.")


@app.command()
def version() -> None:
    """Show the installed version of conduit."""
    typer.echo(f"conduit version {__version__}")
