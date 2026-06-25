"""CLI subcommands for SatTerC."""

import typer

from .create_store import app as create_store_app
from .data_gen import app as data_gen_app
from .graph import app as graph_app
from .merge import app as merge_app
from .run import app as run_app
from .setup import app as setup_app
from .version import app as version_app

app = typer.Typer(
    help="Command-line interface for the SatTerC framework.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(graph_app)
app.add_typer(setup_app)
app.add_typer(run_app)
app.add_typer(create_store_app)
app.add_typer(merge_app)
app.add_typer(data_gen_app, name="data-gen")
app.add_typer(version_app)


def main() -> None:
    """Entry point for the satterc CLI."""
    app()
