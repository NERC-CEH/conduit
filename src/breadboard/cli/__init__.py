"""CLI subcommands for breadboard."""

import typer

from .create_store import app as create_store_app
from .graph import app as graph_app
from .merge import app as merge_app
from .run import app as run_app
from .version import app as version_app

app = typer.Typer(
    help="Command-line interface for the breadboard framework.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(graph_app)
app.add_typer(run_app)
app.add_typer(create_store_app)
app.add_typer(merge_app)
app.add_typer(version_app)


def main() -> None:
    """Entry point for the breadboard CLI."""
    app()
