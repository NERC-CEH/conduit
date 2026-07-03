"""Execute a pipeline defined in a configuration file."""

import warnings
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer

from ..config import CacheSpec, load_config
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

if TYPE_CHECKING:
    from ..config import ParsedConfig

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

    if parsed.units_enabled is not None:
        from xarray_annotated.units import set_policy

        set_policy(enabled=parsed.units_enabled)

    if parsed.units_on_missing is not None:
        from xarray_annotated.units import set_policy
        from xarray_annotated.units._config import OnMissing

        set_policy(on_missing=cast(OnMissing, parsed.units_on_missing))

    if parsed.units_on_inexact is not None:
        from xarray_annotated.units import set_policy
        from xarray_annotated.units._config import OnInexact

        set_policy(on_inexact=cast(OnInexact, parsed.units_on_inexact))

    if parsed.schema_on_mismatch is not None:
        from xarray_annotated.schema import set_policy as set_schema_policy
        from xarray_annotated.schema._config import OnMismatch

        set_schema_policy(on_mismatch=cast(OnMismatch, parsed.schema_on_mismatch))

    if dry_run:
        _dry_run(parsed, config_file, allow_overrides)
        return

    cache_spec = _resolve_cache(parsed.cache_spec, cache, cache_dir)

    inputs = load_inputs(parsed.input_specs, subset_spec=parsed.subset_spec)

    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        allow_module_overrides=allow_overrides,
        cache=cache_spec,
    )

    if parsed.output_specs:
        target_vars = get_final_vars(parsed.output_specs)
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
        )


def _config_provenance(config_file: Path) -> dict[str, str]:
    """Config text + its SHA-256, stamped onto outputs so a store is self-describing."""
    import hashlib

    text = Path(config_file).read_text()
    return {
        "conduit_config": text,
        "conduit_config_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _dry_run(parsed: "ParsedConfig", config_file: Path, allow_overrides: bool) -> None:
    """Validate everything a real run depends on, without executing it.

    Runs the same setup as `run` up to (but excluding) execution: parse
    config, load inputs (lazily — file metadata only), build the driver (which runs
    the build-time contract check), validate the execution plan, validate the loaded
    inputs' contracts (units + dims/coords/dtype) against what the DAG declares, and
    confirm the output destinations are writable. Prints a per-stage summary. Hard
    failures raise (non-zero exit); soft issues follow the active policy (warnings
    stay warnings). No model runs and nothing is written.
    """
    from xarray_annotated.schema import get_policy as schema_get_policy
    from xarray_annotated.units import get_policy

    from ..dag.contract_check import check_input_contracts

    typer.echo(f"Dry run for {config_file}")
    typer.echo("  ✓ config parsed")

    inputs = load_inputs(parsed.input_specs, subset_spec=parsed.subset_spec)
    typer.echo(
        f"  ✓ inputs loaded: {len(inputs)} variable(s) "
        f"from {len(parsed.input_specs)} source(s)"
    )

    # Caching is an execution-time adapter; disable it so the dry run creates no
    # cache directory. The graph structure and unit checks are unaffected.
    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        allow_module_overrides=allow_overrides,
        cache=None,
    )
    typer.echo("  ✓ DAG built (static contract check passed)")

    if parsed.output_specs:
        target_vars = get_final_vars(parsed.output_specs)
        # Wiring check first: an unbound input raises here with a clearer message
        # than Hamilton's; an unused input surfaces as a warning below.
        with warnings.catch_warnings(record=True) as wiring_warnings:
            warnings.simplefilter("always")
            check_wiring(dr, target_vars, inputs, exempt=auxiliary_input_names(inputs))
        dr.validate_execution(target_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        typer.echo(
            f"  ✓ execution plan valid: {len(target_vars)} output node(s) reachable"
        )
        for w in wiring_warnings:
            typer.echo(f"      ! {w.message}")
    else:
        typer.echo("  - execution plan: skipped (no [outputs.*] configured)")

    # Capture warn-mode contract findings so they surface in the report rather
    # than scattering across stderr; strict-mode findings raise straight out.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_input_contracts(dr, inputs)
    pol = get_policy()
    axes = (
        f"enabled={pol.enabled}, on_missing={pol.on_missing}, "
        f"on_inexact={pol.on_inexact}, on_mismatch={schema_get_policy().on_mismatch}"
    )
    if caught:
        typer.echo(f"  ✓ input contracts checked ({axes}, {len(caught)} warning(s)):")
        for w in caught:
            typer.echo(f"      ! {w.message}")
    else:
        typer.echo(f"  ✓ input contracts validated ({axes})")

    if parsed.output_specs:
        assert_output_paths_writable(parsed.output_specs, parsed.subset_spec)
        typer.echo(
            f"  ✓ output paths writable: {len(parsed.output_specs)} destination(s)"
        )
    else:
        typer.echo("  - output paths: skipped (no [outputs.*] configured)")

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
