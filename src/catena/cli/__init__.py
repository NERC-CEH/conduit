"""catena's command-line interface: presentation only.

**This package contains no pipeline logic.** Every command is a thin shim that
turns options into a call to the Python API — `catena.pipeline.run`,
`catena.pipeline.dry_run`, `catena.graph.build_graph`, and the
`catena.gridded` store operations — and renders the result. Anything a command
can do, a downstream project can do from Python, and that is the invariant this
package exists to keep. Add behaviour to the library module and call it here.

**typer is confined to this package.** It ships in the optional ``cli`` extra, so
no catena module outside ``catena.cli`` may import it. `main` therefore imports
the typer application lazily, which is why the app lives in `catena.cli.app`
rather than here: the ``catena`` console script is registered by every install,
including one without the extra, and it must answer with an install hint rather
than an ImportError traceback.
"""

import sys

from ..errors import CatenaError

__all__ = ["main"]

_INSTALL_HINT = (
    "The 'catena' command requires the optional 'cli' extra. "
    "Install it with "
    '`pip install "ukceh-catena[cli] @ git+https://github.com/NERC-CEH/catena"`. '
    "The Python API (catena.run, catena.dry_run, catena.build_graph) needs no extra."
)


def main() -> None:
    """Entry point for the catena CLI.

    A `CatenaError` is a condition catena anticipated and wrote a message for, so
    the message is all a user needs; the frames above it are catena's own call
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
    except CatenaError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
