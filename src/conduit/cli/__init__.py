"""conduit's command-line interface: presentation only.

**This package contains no pipeline logic.** Every command is a thin shim that
turns options into a call to the Python API — `conduit.pipeline.run`,
`conduit.pipeline.dry_run`, `conduit.graph.build_graph`, and the
`conduit.gridded` store operations — and renders the result. Anything a command
can do, a downstream project can do from Python, and that is the invariant this
package exists to keep. Add behaviour to the library module and call it here.

**typer is confined to this package.** It ships in the optional ``cli`` extra, so
no conduit module outside ``conduit.cli`` may import it. `main` therefore imports
the typer application lazily, which is why the app lives in `conduit.cli.app`
rather than here: the ``conduit`` console script is registered by every install,
including one without the extra, and it must answer with an install hint rather
than an ImportError traceback.
"""

import sys

from ..errors import ConduitError

__all__ = ["main"]

_INSTALL_HINT = (
    "The 'conduit' command requires the optional 'cli' extra. "
    "Install it with `pip install conduit[cli]`. "
    "The Python API (conduit.run, conduit.dry_run, conduit.build_graph) needs no extra."
)


def main() -> None:
    """Entry point for the conduit CLI.

    A `ConduitError` is a condition conduit anticipated and wrote a message for, so
    the message is all a user needs; the frames above it are conduit's own call
    stack. Every other exception propagates with its traceback, because that is a
    bug and the frames are the point.
    """
    try:
        from .app import app
    except ModuleNotFoundError as exc:
        if exc.name != "typer":
            raise
        print(_INSTALL_HINT, file=sys.stderr)
        raise SystemExit(1) from exc

    import typer

    try:
        app()
    except ConduitError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
