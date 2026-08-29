"""Run a configured pipeline end to end, or validate one without running it.

`run` executes everything a ``config.toml`` describes. `dry_run` performs the
same setup and validation but executes nothing and writes nothing, returning a
`DryRunReport` of what each stage found.

Both accept either a path to a config file or an already-parsed `ParsedConfig`,
so you can parse, adjust the spec in Python, and run the result. Only the path
form stamps output provenance, which needs the config text.
"""

import hashlib
import logging
import time
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import xarray as xr

from .blocking import execute_blocked
from .build import build_driver
from .config import load_config
from .io import (
    assert_output_paths_writable,
    auxiliary_input_names,
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
)
from .specs import CacheSpec, ParsedConfig
from .wiring_check import check_wiring

__all__ = ["DryRunReport", "RunReport", "Stage", "WrittenOutput", "dry_run", "run"]

logger = logging.getLogger(__name__)

#: Either a path to a TOML config file or an already-parsed config.
ConfigSource = str | Path | ParsedConfig


def prepare_config(config: ConfigSource) -> tuple[ParsedConfig, Path | None]:
    """Resolve a config source to a parsed config and its source path, if any.

    Accepts a path to a TOML file or an already-parsed `ParsedConfig`. Applies the
    config's ``[annotations]`` policy before returning, so every contract check
    downstream reads the policy the config asked for. The returned path is ``None``
    for a `ParsedConfig`, which has no file to stamp provenance from.
    """
    if isinstance(config, ParsedConfig):
        parsed, config_file = config, None
    else:
        config_file = Path(config)
        parsed = load_config(config_file)
    parsed.annotations.apply()
    return parsed, config_file


@dataclass(frozen=True)
class WrittenOutput:
    """One destination a run wrote, and what went into it."""

    #: The ``[outputs.<label>]`` section this came from.
    label: str
    #: Where it was actually written. Under ``[subset]`` this carries the
    #: subset's suffix, so it is not always the path the config asked for.
    path: Path
    variables: tuple[str, ...]
    #: Size on disk, summed over a directory store. ``None`` if it could not be
    #: measured.
    size_bytes: int | None = None


@dataclass(frozen=True)
class RunReport:
    """What a run computed, where it went, and how long it took.

    A hard failure raises out of `run`, so a report exists only for a pipeline
    that ran to completion.
    """

    #: The config's path, or ``None`` when `run` was given a `ParsedConfig`.
    config_file: Path | None
    #: The dataset written for each ``[outputs.*]`` section, keyed by section
    #: name. Empty for a config that declares no outputs.
    outputs: dict[str, xr.Dataset] = field(default_factory=dict)
    written: tuple[WrittenOutput, ...] = ()
    #: Wall-clock seconds, config parse to last byte written.
    elapsed: float = 0.0


def run(
    config: ConfigSource,
    *,
    allow_overrides: bool = False,
    cache: bool | None = None,
    cache_dir: Path | None = None,
) -> RunReport:
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
    RunReport
        The datasets written, where each one went, and how long it took. A
        config declaring no outputs still parses, loads inputs, runs the input
        checks and builds the DAG, and comes back with nothing written.

    Notes
    -----
    Progress is logged to the ``conduit.pipeline`` logger at ``INFO`` as each
    stage completes, so a caller can route it wherever it wants. ``conduit run``
    prints it.
    """
    started = time.perf_counter()
    parsed, config_file = prepare_config(config)
    for source in _registered_sources(parsed):
        logger.info("%s", source)
    cache_spec = _resolve_cache(parsed.cache_spec, cache, cache_dir)
    if cache_spec is not None:
        logger.info("caching enabled: %s", cache_spec.path)

    inputs = load_inputs(
        parsed.input_specs,
        subset_spec=parsed.subset_spec,
        point_dim=parsed.point_dim,
    )
    logger.info(
        "inputs loaded: %d variable(s) from %d source(s)",
        len(inputs),
        len(parsed.input_specs),
    )

    if n_checks := _run_input_checks(parsed):
        logger.info("input checks passed (%d)", n_checks)

    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
        allow_module_overrides=allow_overrides,
        cache=cache_spec,
        base=parsed.base,
    )

    if not parsed.output_specs:
        logger.info("DAG built; no [outputs.*] configured, so nothing to execute")
        return RunReport(config_file, elapsed=time.perf_counter() - started)

    target_vars = get_final_vars(parsed.output_specs)
    logger.info("DAG built: executing %d output node(s)", len(target_vars))
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
    paths = save_outputs(
        output_datasets,
        parsed.output_specs,
        subset_spec=parsed.subset_spec,
        provenance=_config_provenance(config_file),
        point_dim=parsed.point_dim,
    )
    written = tuple(
        WrittenOutput(
            label=label,
            path=path,
            variables=tuple(str(name) for name in output_datasets[label].data_vars),
            size_bytes=_size_on_disk(path),
        )
        for label, path in paths.items()
    )
    return RunReport(
        config_file=config_file,
        outputs=output_datasets,
        written=written,
        elapsed=time.perf_counter() - started,
    )


def _size_on_disk(path: Path) -> int | None:
    """Bytes ``path`` occupies, summed over a directory store, or None if unreadable.

    A Zarr output is a directory, and a subset run region-writes into a shared
    store whose size is not this run's doing, so the number is best-effort.
    """
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except OSError:
        return None


@dataclass(frozen=True)
class Stage:
    """One step of a dry run, and what it found.

    ``detail`` is a complete phrase, e.g. "inputs loaded: 18 variable(s) from 4
    source(s)".
    """

    name: str
    status: Literal["ok", "skipped"]
    # A whole phrase, never a fragment for the caller to assemble: the wording of a
    # stage is fixed here so every renderer (the CLI, a CI script, a test) words it
    # the same way.
    detail: str
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DryRunReport:
    """The outcome of a dry run.

    A hard failure raises out of `dry_run`, so a report exists only for a pipeline
    that passed. ``findings`` on the individual stages are the soft issues the
    active contract policy allowed through.
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
    into `Stage.findings`. No model runs and nothing is written.
    """
    from .contract_check import check_input_contracts

    parsed, config_file = prepare_config(config)
    # Reported in `detail` rather than `findings`: a finding renders as a warning,
    # and where a module came from is information, not a problem.
    sources = _registered_sources(parsed)
    stages: list[Stage] = [
        Stage("config", "ok", "; ".join(("config parsed", *sources)))
    ]

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
        base=parsed.base,
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


def _registered_sources(parsed: ParsedConfig) -> tuple[str, ...]:
    """Name each section whose module came from an installed package.

    A section with no ``_import_path`` says nothing about where its code lives, so
    the run reports what the environment supplied rather than resolving it silently.
    """
    return tuple(
        f"[{mod.section}] provided by {mod.distribution}: {mod.import_path}"
        for mod in parsed.registered_modules
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
    `conduit.input_checks.InputCheckError`.
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
    from .input_checks import run_input_checks
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
