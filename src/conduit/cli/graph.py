"""``conduit graph``: write the pipeline visualisation to a file.

Options in, `conduit.graph.build_graph` out, rendered to disk. The graph itself
is built and styled in `conduit.graph`; picking formats and destinations is what
belongs to the command.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from ..graph import build_graph

if TYPE_CHECKING:
    # graphviz ships in the optional `viz` extra, and `conduit.build_graph` is
    # re-exported from the package root, so importing it here would make
    # `import conduit` fail for anyone who did not install that extra.
    import graphviz

app = typer.Typer(help="Visualise a pipeline defined in a configuration file.")


@app.command()
def graph(
    config_file: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    output: Annotated[
        str, typer.Option("-o", "--output", help="Name of output file")
    ] = "pipeline",
    style: Annotated[
        Path | None,
        typer.Option(
            "-s",
            "--style",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Optional TOML file customising the DAG styling.",
        ),
    ] = None,
    allow_overrides: Annotated[
        bool,
        typer.Option(
            "--allow-overrides",
            help="Allow later modules to override earlier ones.",
        ),
    ] = False,
    png: Annotated[bool, typer.Option(help="Convert to PNG format")] = False,
    pdf: Annotated[bool, typer.Option(help="Convert to PDF format")] = False,
) -> None:
    """Visualise a pipeline defined in a configuration file.

    Each node shows its declared unit; requested outputs are highlighted and
    edges are coloured by temporal frequency.  Pass ``--style`` to override the
    default styling (see ``conduit.graph_style``).

    Attention
    ---------
    This requires graphviz to be installed.
    """
    digraph = build_graph(config_file, style=style, allow_overrides=allow_overrides)

    output_path = Path(output).with_suffix(".dot")
    output_path.write_text(digraph.source)
    typer.echo(f"Wrote {output_path}")

    for enabled, fmt in ((png, "png"), (pdf, "pdf")):
        if enabled:
            _render(digraph, output_path.with_suffix(f".{fmt}"), fmt)


def _render(digraph: "graphviz.Digraph", dest: Path, fmt: str) -> None:
    """Render ``digraph`` to ``dest`` via the graphviz API, surfacing failures.

    The previous ``subprocess.run(["dot", ...])`` round-trip through the .dot file
    ignored the exit status, so a missing ``dot`` binary or a malformed graph left no
    output and no error — the flag simply did nothing.
    """
    import graphviz

    try:
        dest.write_bytes(digraph.pipe(format=fmt))
    except graphviz.ExecutableNotFound as exc:
        raise typer.BadParameter(
            f"Cannot write {dest.name}: the graphviz 'dot' executable was not "
            f"found. Install graphviz (e.g. `apt install graphviz` / "
            f"`brew install graphviz`), or drop --{fmt} to emit only the .dot source."
        ) from exc
    except graphviz.CalledProcessError as exc:  # graphviz ran, but failed
        raise typer.BadParameter(
            f"graphviz failed to render {dest.name}: {exc.stderr or exc}"
        ) from exc
    typer.echo(f"Wrote {dest}")
