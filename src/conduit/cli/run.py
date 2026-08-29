"""``conduit run``: execute or validate a pipeline, and print what happened.

Options in, `conduit.pipeline.run` or `conduit.pipeline.dry_run` out. The
pipeline logic lives in `conduit.pipeline`; everything here is presentation —
glyphs, colour and column alignment over a `RunReport` or a `DryRunReport`, plus
a handler that prints the library's progress logging as a run reaches it.
"""

import logging
from pathlib import Path
from typing import Annotated

import typer

from ..pipeline import DryRunReport, RunReport
from ..pipeline import dry_run as _dry_run
from ..pipeline import run as _run

app = typer.Typer(help="Execute a pipeline defined in a configuration file.")


@app.command()
def run(
    config_file: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    allow_overrides: Annotated[
        bool,
        typer.Option(
            "--allow-overrides",
            help="Allow later modules to override earlier ones.",
        ),
    ] = False,
    cache: Annotated[
        bool | None,
        typer.Option(
            "--cache/--no-cache",
            help="Enable or disable result caching, overriding the [cache] "
            "section of the config.",
        ),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Directory for cached results (implies caching is enabled).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Validate config, inputs, DAG plan, wiring, contracts and output "
            "paths without executing the pipeline or writing any outputs.",
        ),
    ] = False,
) -> None:
    """Execute a pipeline defined in a configuration file."""
    if dry_run:
        _echo_report(_dry_run(config_file, allow_overrides=allow_overrides))
        return

    _echo_progress_as_it_happens()
    typer.echo(f"Running {config_file}")
    _echo_run(
        _run(
            config_file,
            allow_overrides=allow_overrides,
            cache=cache,
            cache_dir=cache_dir,
        )
    )


class _EchoHandler(logging.Handler):
    """Print a log record as one indented line, through typer."""

    def emit(self, record: logging.LogRecord) -> None:
        typer.echo(f"  {record.getMessage()}")


def _echo_progress_as_it_happens() -> None:
    """Route the library's INFO progress lines to the terminal as the run reaches them.

    A `RunReport` only exists once the run is over, so the stages a user waits
    through are logged rather than returned. The library sets no handler; this is
    the application deciding where they go.
    """
    logger = logging.getLogger("conduit")
    if not any(isinstance(h, _EchoHandler) for h in logger.handlers):
        logger.addHandler(_EchoHandler())
    logger.setLevel(logging.INFO)


def _echo_run(report: RunReport) -> None:
    """Print what a run wrote, then how long the whole thing took."""
    if not report.outputs:
        # A config with no outputs is a legitimate checks-only invocation (it still
        # parsed, loaded inputs, ran the input checks and built the DAG), so this
        # exits 0 — but silently doing nothing looked like a successful run.
        typer.echo(
            "No [outputs.*] configured; nothing to execute. "
            "Config, inputs and DAG were validated."
        )
    for output in report.written:
        tick = typer.style("✓", fg=typer.colors.GREEN)
        size = (
            "" if output.size_bytes is None else f", {_format_size(output.size_bytes)}"
        )
        typer.echo(
            f"  {tick} wrote {_shorten(output.path)} "
            f"({len(output.variables)} variable(s){size})"
        )
    typer.echo(f"Run completed in {report.elapsed:.2f}s")


def _shorten(path: Path) -> Path:
    """Express a written path relative to the working directory where possible.

    Output paths resolve against the config file's directory, so they come back
    absolute. Printing the whole thing is noise in a terminal and machine-specific
    in captured output, e.g. a documentation build.
    """
    cwd = Path.cwd()
    return path.relative_to(cwd) if path.is_relative_to(cwd) else path


def _format_size(size_bytes: int) -> str:
    """Format a byte count in the largest unit that leaves it above 1."""
    size = float(size_bytes)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    raise AssertionError("unreachable")


def _echo_report(report: DryRunReport) -> None:
    """Print a `DryRunReport` as the per-stage summary, with findings indented under.

    ``typer.echo`` strips the escape codes when stdout is not a terminal, so piped
    and captured output (the documentation build among them) stays plain.
    """
    typer.echo(f"Dry run for {report.config_file}")
    for stage in report.stages:
        glyph = (
            typer.style("✓", fg=typer.colors.GREEN)
            if stage.status == "ok"
            else typer.style("-", dim=True)
        )
        typer.echo(f"  {glyph} {stage.detail}")
        if stage.name == "contracts":
            _echo_policy(report.policy)
        for finding in stage.findings:
            typer.echo(f"      {typer.style('!', fg=typer.colors.YELLOW)} {finding}")
    typer.echo("Dry run passed.")


def _echo_policy(policy: dict[str, str]) -> None:
    """Print the active contract policy, one row per policy object, columns aligned."""
    if not policy:
        return
    width = max(len(label) for label in policy)
    for label, settings in policy.items():
        typer.echo(f"      {label:<{width}}  {settings}")
