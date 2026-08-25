"""``conduit run``: execute or validate a pipeline, and print what happened.

Options in, `conduit.pipeline.run` or `conduit.pipeline.dry_run` out. The
pipeline logic lives in `conduit.pipeline`; everything here is presentation —
glyphs, colour and column alignment over a `DryRunReport`.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from ..pipeline import dry_run as _dry_run
from ..pipeline import run as _run

if TYPE_CHECKING:
    from ..pipeline import DryRunReport

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

    outputs = _run(
        config_file,
        allow_overrides=allow_overrides,
        cache=cache,
        cache_dir=cache_dir,
    )

    if not outputs:
        # A config with no outputs is a legitimate checks-only invocation (it still
        # parsed, loaded inputs, ran the input checks and built the DAG), so this
        # exits 0 — but silently doing nothing looked like a successful run.
        typer.echo(
            "No [outputs.*] configured; nothing to execute. "
            "Config, inputs and DAG were validated."
        )


def _echo_report(report: "DryRunReport") -> None:
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
