"""Run a configured pipeline end to end, or validate one without running it.

This module is conduit's top-level Python API: `run` executes everything a
``config.toml`` describes, and `dry_run` performs the same setup and validation
while executing nothing and writing nothing.

**Why these live here and not in the CLI.** conduit is a framework — downstream
projects depend on it *instead of* depending on Hamilton directly. The sequence a
run performs (parse, apply the annotation policy, load inputs, run the input
checks, build the driver, check wiring, execute, collect, save) is therefore part
of the product, not an implementation detail of a terminal command. ``conduit.cli``
is a presentation layer over these two functions and holds no pipeline logic of
its own.

**`dry_run` returns a `DryRunReport` rather than printing one.** Validation and
presentation are separable concerns: the report is an ordered list of `Stage`
records that the CLI renders with colour and glyphs, a CI script can serialise,
and a test can assert on without parsing stdout. Hard failures still raise, so a
`DryRunReport` that comes back at all is a pipeline that passed; `Stage.findings`
carry the soft issues that the active contract policy allowed through as warnings.

Both functions accept either a path to a config file or an already-parsed
`ParsedConfig`, so a caller can parse, adjust the spec in Python, and run the
result. Only the path form can stamp output provenance, which needs the config
text (see `_config_provenance`).
"""

import hashlib
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import xarray as xr

from .config import load_config
from .dag.blocking import execute_blocked
from .dag.driver import build_driver
from .dag.wiring_check import check_wiring
from .io import (
    assert_output_paths_writable,
    auxiliary_input_names,
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
)
from .specs import CacheSpec, ParsedConfig

__all__ = ["DryRunReport", "Stage", "dry_run", "run"]

#: Either a path to a TOML config file or an already-parsed config.
ConfigSource = str | Path | ParsedConfig


def _prepare(config: ConfigSource) -> tuple[ParsedConfig, Path | None]:
    """Resolve a config source to a parsed config and its source path, if any.

    The annotation policy is applied here rather than by each caller: it is global
    state that every downstream contract check reads, so it must be in place before
    inputs are loaded or a driver is built.
    """
    if isinstance(config, ParsedConfig):
        parsed, config_file = config, None
    else:
        config_file = Path(config)
        parsed = load_config(config_file)
    parsed.annotations.apply()
    return parsed, config_file


def run(
    config: ConfigSource,
    *,
    allow_overrides: bool = False,
    cache: bool | None = None,
    cache_dir: Path | None = None,
) -> dict[str, xr.Dataset]:
    """Execute a pipeline and write its outputs.

    Parameters
    ----------
    config
        Path to a TOML config file, or a `ParsedConfig` to run directly.
    allow_overrides
        Allow a later module to override a node defined by an earlier one.
    cache
        Enable or disable result caching, overriding the config's ``[cache]``
        section. ``None`` defers to the config.
    cache_dir
        Directory for cached results. Implies caching is enabled.

    Returns
    -------
    dict
        The dataset written for each ``[outputs.*]`` section, keyed by section
        name. Empty when the config declares no outputs — a legitimate
        checks-only invocation, which still parses, loads inputs, runs the input
        checks and builds the DAG.
    """
    parsed, config_file = _prepare(config)
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

    if not parsed.output_specs:
        return {}

    target_vars = get_final_vars(parsed.output_specs)
    # Before compute, not after: an unwritable destination discovered inside
    # save_outputs would cost the whole run. Same check `dry_run` performs.
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
    return output_datasets


@dataclass(frozen=True)
class Stage:
    """One step of a dry run, and what it found.

    ``detail`` is a complete phrase ("inputs loaded: 18 variable(s) from 4
    source(s)"), not a fragment to be assembled by the caller, so every renderer
    words a stage the same way.
    """

    name: str
    status: Literal["ok", "skipped"]
    detail: str
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DryRunReport:
    """The outcome of a dry run.

    There is no ``passed`` flag: a hard failure raises out of `dry_run`, so a
    report exists only for a pipeline that passed. ``findings`` on the individual
    stages are the soft issues the active contract policy allowed through.
    """

    #: The config's path, or ``None`` when `dry_run` was given a `ParsedConfig`.
    config_file: Path | None
    stages: tuple[Stage, ...] = ()
    #: One line per contract policy object, keyed by axis (units/schema/temporal).
    policy: dict[str, str] = field(default_factory=dict)


def dry_run(config: ConfigSource, *, allow_overrides: bool = False) -> DryRunReport:
    """Validate everything a real run depends on, without executing it.

    Runs the same setup as `run` up to (but excluding) execution: parse the
    config, load inputs (lazily — file metadata only), run the input checks, build
    the driver (which runs the build-time contract check), validate the execution
    plan, validate the loaded inputs' contracts (units + dims/coords/dtype + freq)
    against what the DAG declares, and confirm the output destinations are
    writable.

    Hard failures raise; soft issues follow the active policy and are collected
    into `Stage.findings` rather than left to scatter across stderr. No model runs
    and nothing is written.
    """
    from .dag.contract_check import check_input_contracts

    parsed, config_file = _prepare(config)
    stages: list[Stage] = [Stage("config", "ok", "config parsed")]

    inputs = load_inputs(
        parsed.input_specs,
        subset_spec=parsed.subset_spec,
        point_dim=parsed.point_dim,
    )
    stages.append(
        Stage(
            "inputs",
            "ok",
            f"inputs loaded: {len(inputs)} variable(s) "
            f"from {len(parsed.input_specs)} source(s)",
        )
    )

    if parsed.checks:
        n_checks = _run_input_checks(parsed)
        if n_checks:
            stages.append(Stage("checks", "ok", f"input checks passed ({n_checks})"))
        else:
            stages.append(
                Stage(
                    "checks",
                    "skipped",
                    "input checks: skipped (running under [subset])",
                )
            )
    else:
        stages.append(Stage("checks", "skipped", "input checks: none configured"))

    # Caching is an execution-time adapter; disable it so the dry run creates no
    # cache directory. The graph structure and unit checks are unaffected.
    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
        allow_module_overrides=allow_overrides,
        cache=None,
    )
    stages.append(Stage("dag", "ok", "DAG built (static contract check passed)"))

    if parsed.output_specs:
        target_vars = get_final_vars(parsed.output_specs)
        # Wiring check first: an unbound input raises here with a clearer message
        # than Hamilton's; an unused input surfaces as a finding below.
        with warnings.catch_warnings(record=True) as wiring_warnings:
            warnings.simplefilter("always")
            check_wiring(dr, target_vars, inputs, exempt=auxiliary_input_names(inputs))
        dr.validate_execution(target_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        stages.append(
            Stage(
                "plan",
                "ok",
                f"execution plan valid: {len(target_vars)} output node(s) reachable",
                tuple(str(w.message) for w in wiring_warnings),
            )
        )
    else:
        stages.append(
            Stage(
                "plan", "skipped", "execution plan: skipped (no [outputs.*] configured)"
            )
        )

    # Capture warn-mode contract findings so they surface in the report rather
    # than scattering across stderr; strict-mode findings raise straight out.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_input_contracts(dr, inputs)
    detail = (
        f"input contracts checked ({len(caught)} warning(s))"
        if caught
        else "input contracts validated"
    )
    stages.append(
        Stage("contracts", "ok", detail, tuple(str(w.message) for w in caught))
    )

    if parsed.output_specs:
        assert_output_paths_writable(parsed.output_specs, parsed.subset_spec)
        stages.append(
            Stage(
                "outputs",
                "ok",
                f"output paths writable: {len(parsed.output_specs)} destination(s)",
            )
        )
    else:
        stages.append(
            Stage(
                "outputs",
                "skipped",
                "output paths: skipped (no [outputs.*] configured)",
            )
        )

    return DryRunReport(
        config_file=config_file, stages=tuple(stages), policy=_policy_summary()
    )


def _policy_summary() -> dict[str, str]:
    """Summarise the active contract policy, one entry per policy object.

    The three axes come from three separate ``get_policy()`` calls, so they are
    reported that way rather than run together into one line. The combined form
    ran past 110 characters and buried ``on_inexact`` in the middle of it.
    """
    from xarray_annotated.schema import get_policy as schema_get_policy
    from xarray_annotated.temporal import get_policy as temporal_get_policy
    from xarray_annotated.units import get_policy as units_get_policy

    units = units_get_policy()
    return {
        "units": (
            f"enabled={units.enabled}  on_missing={units.on_missing}  "
            f"on_inexact={units.on_inexact}"
        ),
        "schema": f"on_mismatch={schema_get_policy().on_mismatch}",
        "temporal": f"on_uninferable={temporal_get_policy().on_uninferable}",
    }


def _run_input_checks(parsed: ParsedConfig) -> int:
    """Run the configured input-compatibility checks before the DAG is built.

    Returns the number of checks run (0 if none configured). Under ``[subset]``
    the checks operate on a pixel slice rather than the full domain, so they are
    skipped with a warning recommending a full-domain dry run. A failure raises
    `conduit.checks.InputCheckError`.
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
    from .checks import run_input_checks
    from .io import load_raw_datasets

    run_input_checks(
        load_raw_datasets(parsed.input_specs, parsed.point_dim), parsed.checks
    )
    return len(parsed.checks)


def _config_provenance(config_file: Path | None) -> dict[str, str]:
    """Config text + its SHA-256, stamped onto outputs so a store is self-describing.

    A `ParsedConfig` carries no source path and no round-trippable text, so a run
    driven from an in-memory config stamps nothing rather than stamping something
    that cannot be trusted to reproduce it.
    """
    if config_file is None:
        return {}
    text = Path(config_file).read_text()
    return {
        "conduit_config": text,
        "conduit_config_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _resolve_cache(
    config_cache: CacheSpec | None,
    cache_flag: bool | None,
    cache_dir: Path | None,
) -> CacheSpec | None:
    """Combine the config's [cache] spec with caller overrides.

    ``cache=False`` always wins. ``cache=True`` or a ``cache_dir`` enable caching
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
