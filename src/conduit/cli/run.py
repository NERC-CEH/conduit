"""Execute a pipeline defined in a configuration file."""

import warnings
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from ..config import load_config
from ..dag.blocking import execute_blocked
from ..dag.driver import build_driver
from ..dag.wiring_check import check_wiring
from ..io import (
    assert_output_paths_writable,
    auxiliary_input_names,
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
)
from ..specs import CacheSpec

if TYPE_CHECKING:
    from ..specs import ParsedConfig

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
    parsed = load_config(config_file)
    parsed.annotations.apply()

    if dry_run:
        _dry_run(parsed, config_file, allow_overrides)
        return

    cache_spec = _resolve_cache(parsed.cache_spec, cache, cache_dir)

    inputs = load_inputs(
        parsed.input_specs,
        subset_spec=parsed.subset_spec,
        point_dim=parsed.point_dim,
    )

    _run_input_checks(parsed)

    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
        allow_module_overrides=allow_overrides,
        cache=cache_spec,
    )

    if parsed.output_specs:
        target_vars = get_final_vars(parsed.output_specs)
        # Before compute, not after: an unwritable destination discovered inside
        # save_outputs would cost the whole run. Same check `--dry-run` performs.
        assert_output_paths_writable(parsed.output_specs, parsed.subset_spec)
        check_wiring(dr, target_vars, inputs, exempt=auxiliary_input_names(inputs))
        if parsed.blocking_spec is not None:
            results = execute_blocked(dr, inputs, target_vars, parsed.blocking_spec)
        else:
            results = dr.execute(target_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        stacked = parsed.subset_spec is not None
        output_datasets = get_outputs(results, parsed.output_specs, stacked=stacked)
        save_outputs(
            output_datasets,
            parsed.output_specs,
            subset_spec=parsed.subset_spec,
            provenance=_config_provenance(config_file),
            point_dim=parsed.point_dim,
        )
    else:
        # A config with no outputs is a legitimate checks-only invocation (it still
        # parsed, loaded inputs, ran the input checks and built the DAG), so this
        # exits 0 — but silently doing nothing looked like a successful run.
        typer.echo(
            "No [outputs.*] configured; nothing to execute. "
            "Config, inputs and DAG were validated."
        )


def _run_input_checks(parsed: "ParsedConfig") -> int:
    """Run the configured input-compatibility checks before the DAG is built.

    Returns the number of checks run (0 if none configured). Under ``[subset]``
    the checks operate on a pixel slice rather than the full domain, so they are
    skipped with a warning recommending a full-domain ``--dry-run``. A failure
    raises `conduit.checks.InputCheckError`.
    """
    if not parsed.checks:
        return 0
    if parsed.subset_spec is not None:
        warnings.warn(
            "input checks skipped under [subset]; run `conduit run --dry-run` on "
            "the full domain to validate them",
            stacklevel=2,
        )
        return 0
    from ..checks import run_input_checks
    from ..io import load_raw_datasets

    run_input_checks(
        load_raw_datasets(parsed.input_specs, parsed.point_dim), parsed.checks
    )
    return len(parsed.checks)


def _config_provenance(config_file: Path) -> dict[str, str]:
    """Config text + its SHA-256, stamped onto outputs so a store is self-describing."""
    import hashlib

    text = Path(config_file).read_text()
    return {
        "conduit_config": text,
        "conduit_config_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _ok(message: str) -> None:
    """Report a dry-run stage that passed.

    ``typer.echo`` strips the escape codes when stdout is not a terminal, so
    piped and captured output (the documentation build among them) stays plain.
    """
    typer.echo(f"  {typer.style('✓', fg=typer.colors.GREEN)} {message}")


def _skip(message: str) -> None:
    """Report a dry-run stage that did not apply.  See `_ok` on colour."""
    typer.echo(f"  {typer.style('-', dim=True)} {message}")


def _finding(message: str) -> None:
    """Report a soft finding under a stage.  See `_ok` on colour."""
    typer.echo(f"      {typer.style('!', fg=typer.colors.YELLOW)} {message}")


def _echo_policy() -> None:
    """Print the active contract policy, one row per policy object.

    The three axes come from three separate ``get_policy()`` calls, so they are
    grouped that way rather than run together into one parenthetical.  The
    combined form ran past 110 characters, wrapped at whatever width the reader
    had, and buried ``on_inexact`` in the middle of it.
    """
    from xarray_annotated.schema import get_policy as schema_get_policy
    from xarray_annotated.temporal import get_policy as temporal_get_policy
    from xarray_annotated.units import get_policy as units_get_policy

    units = units_get_policy()
    rows = [
        (
            "units",
            f"enabled={units.enabled}  on_missing={units.on_missing}  "
            f"on_inexact={units.on_inexact}",
        ),
        ("schema", f"on_mismatch={schema_get_policy().on_mismatch}"),
        ("temporal", f"on_uninferable={temporal_get_policy().on_uninferable}"),
    ]
    width = max(len(label) for label, _ in rows)
    for label, settings in rows:
        typer.echo(f"      {label:<{width}}  {settings}")


def _dry_run(parsed: "ParsedConfig", config_file: Path, allow_overrides: bool) -> None:
    """Validate everything a real run depends on, without executing it.

    Runs the same setup as `run` up to (but excluding) execution: parse
    config, load inputs (lazily — file metadata only), build the driver (which runs
    the build-time contract check), validate the execution plan, validate the loaded
    inputs' contracts (units + dims/coords/dtype + freq) against what the DAG
    declares, and confirm the output destinations are writable. Prints a per-stage
    summary. Hard failures raise (non-zero exit); soft issues follow the active
    policy (warnings stay warnings). No model runs and nothing is written.
    """
    from ..dag.contract_check import check_input_contracts

    typer.echo(f"Dry run for {config_file}")
    _ok("config parsed")

    inputs = load_inputs(
        parsed.input_specs,
        subset_spec=parsed.subset_spec,
        point_dim=parsed.point_dim,
    )
    _ok(
        f"inputs loaded: {len(inputs)} variable(s) "
        f"from {len(parsed.input_specs)} source(s)"
    )

    if parsed.checks:
        n_checks = _run_input_checks(parsed)
        if n_checks:
            _ok(f"input checks passed ({n_checks})")
        else:
            _skip("input checks: skipped (running under [subset])")
    else:
        _skip("input checks: none configured")

    # Caching is an execution-time adapter; disable it so the dry run creates no
    # cache directory. The graph structure and unit checks are unaffected.
    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
        allow_module_overrides=allow_overrides,
        cache=None,
    )
    _ok("DAG built (static contract check passed)")

    if parsed.output_specs:
        target_vars = get_final_vars(parsed.output_specs)
        # Wiring check first: an unbound input raises here with a clearer message
        # than Hamilton's; an unused input surfaces as a warning below.
        with warnings.catch_warnings(record=True) as wiring_warnings:
            warnings.simplefilter("always")
            check_wiring(dr, target_vars, inputs, exempt=auxiliary_input_names(inputs))
        dr.validate_execution(target_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        _ok(f"execution plan valid: {len(target_vars)} output node(s) reachable")
        for w in wiring_warnings:
            _finding(str(w.message))
    else:
        _skip("execution plan: skipped (no [outputs.*] configured)")

    # Capture warn-mode contract findings so they surface in the report rather
    # than scattering across stderr; strict-mode findings raise straight out.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_input_contracts(dr, inputs)
    if caught:
        _ok(f"input contracts checked ({len(caught)} warning(s))")
    else:
        _ok("input contracts validated")
    _echo_policy()
    for w in caught:
        _finding(str(w.message))

    if parsed.output_specs:
        assert_output_paths_writable(parsed.output_specs, parsed.subset_spec)
        _ok(f"output paths writable: {len(parsed.output_specs)} destination(s)")
    else:
        _skip("output paths: skipped (no [outputs.*] configured)")

    typer.echo("Dry run passed.")


def _resolve_cache(
    config_cache: "CacheSpec | None",
    cache_flag: bool | None,
    cache_dir: Path | None,
) -> "CacheSpec | None":
    """Combine the config's [cache] spec with CLI overrides.

    ``--no-cache`` always wins. ``--cache`` or ``--cache-dir`` enable caching
    with defaults when the config has no [cache] section.
    """
    if cache_flag is False:
        return None
    spec = config_cache
    if cache_flag is True and spec is None:
        spec = CacheSpec()
    if cache_dir is not None:
        spec = replace(spec or CacheSpec(), path=str(cache_dir))
    return spec
