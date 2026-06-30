# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

breadboard is in **alpha** with no external users. It was extracted from the
(now-archived) `satterc` terrestrial-carbon framework to become a general-purpose,
domain-agnostic foundation for data pipelines and forward models. Backwards
compatibility is *not* a constraint: prefer the cleanest design and make breaking
changes (config schema, public APIs, behaviour) freely rather than adding
compatibility shims.

The refactor is **phased**: Phase 1 (done) renamed the package and stripped all
carbon-domain models. Later phases generalise the I/O layer away from the baked-in
temporal-frequency (`{var}_{freq}`, daily/weekly/monthly/static) and geospatial
`(time, pixel)` + CRS conventions, which are still present but slated to become
opt-in. See the plan file if working through subsequent phases.

## Guiding philosophy

breadboard is an opinionated integration of Apache Hamilton (DAG), xarray (+ dask
for scaling), and pint/cf-xarray/pint-xarray (units validation), driven by a TOML
spec that can describe a whole DAG — including dynamically generated nodes — in
plain text. Its value is the *integration*; favour **exposing** Hamilton and xarray
machinery over building opaque wrappers. The units subsystem is the flagship
feature and should be preserved and extended, not bypassed.

## Commands

All common tasks are managed via `just` (see `justfile`):

```bash
just lint            # ruff format + check + marimo notebook lint (modifies files)
just lint-check      # same as lint but read-only (used in CI)
just typecheck       # pyright static type check
just test            # pytest only (no lint)
just test-cov        # pytest with coverage report (fails under 90%)
just docs            # build docs with zensical
just export <name>   # export a marimo example notebook to markdown + HTML
just export-all      # export all example notebooks
```

Run a single test file:
```bash
uv run pytest tests/test_config.py -v
```

Install dependencies:
```bash
uv sync
```

Pre-commit hooks run `uv-lock`, `pyright`, and `ruff` on every commit — not the full test suite.

## Architecture

breadboard uses [Hamilton](https://github.com/DAGWorks-Inc/hamilton) to define
computational DAGs that transform xarray inputs through user-supplied modules into
outputs, with a TOML configuration spec and runtime/build-time unit validation.

### Core modules

**`src/breadboard/config.py`** — parses TOML config files into a `ParsedConfig` dataclass. Recognised top-level sections: `[inputs.*]`, `[outputs.*]`, `[grid]` (silently accepted — grid computation is in `io.py`), `[[node]]`, `[[resample]]`, `[cache]`, `[blocking]`, `[subset]`, `[units]`. **Any other section is treated as a user module and must include `_import_path = "pkg.module"`** — there is no special "models" namespace; user models are just modules. Key types exported: `Config`, `ParsedConfig`, `IOSpec`, `ResampleSpec`, `NodeSpec`, `CacheSpec`, `BlockingSpec`, `SubsetSpec`.

**`src/breadboard/dag/driver.py`** — builds Hamilton `Driver` objects from a `ParsedConfig`. The `MODULES` dict maps the two built-in short names (`"node"`, `"resample"`) to importable paths; every other module identifier is a dotted `_import_path` imported directly. `build_driver` also runs the build-time unit check (`check_dag_units`).

**`src/breadboard/units.py` + `dag/unit_check.py` + `dag/_utils.py`** — the units subsystem (the flagship feature). `units.py` wires pint/cf-xarray/pint-xarray (UDUNITS registry) and provides the `Annotated[DataArray, "<unit>"]` signature convention plus strict/warn/off modes (env vars `BREADBOARD_UNITS_MODE`/`BREADBOARD_UNITS_EXACT`). `_utils.py:declare_units` enforces units at runtime; `unit_check.py` adds build-time (`check_dag_units`) and dry-run input (`check_input_units`) checks.

**`src/breadboard/io.py`** — all I/O lives here, outside the Hamilton DAG. Key public functions:
- `load_inputs(input_specs)` — reads NetCDF/Zarr/CSV/Parquet/JSON/TOML files; returns a flat dict of named `DataArray`s following Hamilton naming conventions (`{var}_{freq}`, `dates_{freq}`, `latitude`, `longitude`)
- `get_outputs(results, output_specs)` — assembles Hamilton execute results into per-frequency `Dataset`s
- `save_outputs(output_datasets, output_specs)` — writes datasets to disk
- `get_final_vars(output_specs)` — returns the flat node name list to pass to `driver.execute(final_vars=...)`
- `create_output_store` / `merge_subset_outputs` — pre-create Zarr stores and reassemble parallel subset runs

(Note: io.py's frequency vocabulary and stacked-`pixel`/CRS geospatial model are the main domain-flavoured conventions still baked in; later phases make them opt-in.)

**`src/breadboard/dag/`** — the built-in Hamilton DAG modules:
- `resample.py` — temporal resampling (daily ↔ weekly ↔ monthly), driven by `resample_specs` in driver config; unit-preserving
- `node.py` — dynamically generates Hamilton-compatible modules from `[[node]]` config entries using `exec()`; supports inline expressions or import-path + function name, with optional declared `units`. This is the "user model in TOML" path.
- `caching.py` — registers a content-based fingerprint for `xarray.DataArray` and applies `Builder.with_cache()` from a `CacheSpec`
- `blocking.py` — pixel-blocked driver execution (partition invariance)
- `_utils.py` — `@declare_units` decorator (unit enforcement/stamping)
- `_hamilton_fixes.py` — workarounds for Hamilton edge cases

### Hamilton DAG conventions (for user-defined modules)

Each module contains plain functions that become DAG nodes. The conventions a user
model follows:

- **Public node function name = the output node name** (single-output), or use `@extract_fields()` (from `hamilton.function_modifiers`) with a `TypedDict` return to split into multiple named outputs.
- `@declare_units` (innermost) reads `Annotated[DataArray, "<unit>"]` from the signature/return and validates/stamps units.
- **Parameter names = input node names** (following io.py's `{var}_{freq}` / bare-static / `dates_{freq}` / `latitude` conventions).
- **Keyword-only args (after `*`) = config parameters**, populated from the module's own config section.

### Configuration-driven composition

A user module is added by writing a config section `[mymodel]` with
`_import_path = "mypkg.mymodel"` (plus any keyword params), or inline via `[[node]]`.
The built-ins `node` and `resample` are addressable by their short names.

### CLI

The `typer`-based CLI (`src/breadboard/cli/`) has commands: `run`, `graph`
(visualise DAG as PDF/PNG/DOT), `version`, `create-store` and `merge` (for parallel
subset runs). All are model-agnostic.

### Testing

Tests in `tests/` use session-scoped fixtures that generate synthetic netCDF data once (`tests/conftest.py`) via `setup_utils/data_gen` — a generic, name-heuristic synthetic-data generator (`coords.py` + `fallback.py`, no domain semantics). The session pipeline (`tests/test_config.toml`) is model-free: a single `[[node]]` derived variable stands in for a model. Coverage gate is 90% (`just test-cov`).

### Examples

`examples/` holds `graphviz.toml`, a commented `breadboard graph --style` template
(a user-facing reference, not loaded by any tooling). Generic example notebooks are
added in a later phase.
