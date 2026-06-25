# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

SatTerC is in **alpha** with no users outside the core collaboration. Backwards
compatibility is *not* a constraint: prefer the cleanest design and make breaking
changes (config schema, public APIs, behaviour) freely rather than adding
compatibility shims.

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

SatTerC is a data-driven terrestrial carbon modelling framework. It uses [Hamilton](https://github.com/DAGWorks-Inc/hamilton) to define computational DAGs that transform satellite/environmental inputs through biogeochemical models into carbon-related outputs.

### Core modules

**`src/satterc/config.py`** — parses TOML config files into a `ParsedConfig` dataclass. Recognised top-level sections: `[inputs.*]`, `[outputs.*]`, `[grid]` (silently ignored — grid computation is in `io.py`), `[models.*]`, `[[node]]`, `[[resample]]`, `[cache]` (Hamilton result caching → `ParsedConfig.cache_spec`). Any other section is treated as an external module and must include `_import_path`. Key types exported: `Config`, `ParsedConfig`, `IOSpec`, `ResampleSpec`, `NodeSpec`, `CacheSpec`.

**`src/satterc/dag/driver.py`** — builds Hamilton `Driver` objects from a `ParsedConfig`. The `MODULES` dict maps config section names (e.g. `"models.pmodel"`) to importable paths (e.g. `"satterc.dag.pmodel"`). External modules are imported directly.

**`src/satterc/io.py`** — all I/O lives here, outside the Hamilton DAG. Key public functions:
- `load_inputs(input_specs)` — reads NetCDF/Zarr/CSV/Parquet/JSON/TOML files; returns a flat dict of named `DataArray`s following Hamilton naming conventions (`{var}_{freq}`, `dates_{freq}`, `latitude`, `longitude`)
- `get_outputs(results, output_specs)` — assembles Hamilton execute results into per-frequency `Dataset`s
- `save_outputs(output_datasets, output_specs)` — writes datasets to disk
- `get_final_vars(output_specs)` — returns the flat node name list to pass to `driver.execute(final_vars=...)`

**`src/satterc/dag/`** — the Hamilton DAG modules:
- `pmodel.py`, `splash.py`, `sgam.py`, `rothc.py` — ecological model wrappers
- `resample.py` — temporal resampling (daily ↔ weekly ↔ monthly), driven by `resample_specs` in driver config
- `node.py` — dynamically generates Hamilton-compatible modules from `[[node]]` config entries using `exec()`; supports inline expressions or import-path + function name
- `caching.py` — registers a content-based fingerprint for `xarray.DataArray` (Hamilton can't hash them by default) and applies `Builder.with_cache()` from a `CacheSpec`; imported lazily by `driver.build_driver` when caching is enabled
- `_utils.py` — `@xarray_io()` decorator that wraps numpy functions to accept/return xarray objects
- `_hamilton_fixes.py` — workarounds for Hamilton edge cases

### Hamilton DAG conventions

Each module contains plain functions that become DAG nodes. Key patterns:

- `@extract_fields` (from `hamilton.function_modifiers`) — splits a dict return into multiple DAG outputs
- `@xarray_io()` — wraps numpy-based functions to accept/return xarray objects
- Variable names carry frequency suffixes: `temperature_daily`, `gpp_monthly`, etc.

### Configuration-driven composition

Config sections map directly to module names (e.g. `[models.pmodel]`, `[inputs.daily]`), so adding a built-in model means adding a module under `dag/` and a MODULES entry in `driver.py`. External modules need only a `_import_path` key in the config.

### CLI

The `typer`-based CLI (`src/satterc/cli/`) has commands: `run`, `graph` (visualise DAG as PDF/PNG), `setup` (interactive config generation), `data-gen` (synthetic data for testing), `version`.

### Testing

Tests in `tests/` use session-scoped fixtures that generate synthetic netCDF data once (`tests/conftest.py`). The `setup_utils/data_gen` utilities mirror the real input format for integration testing.

### Examples

Marimo interactive notebooks live in `examples/`. Each has `satterc==<version>` pinned in its inline `# dependencies` block — update this when bumping the package version, then re-export with `just export-all`.

`examples/` also holds two plain config files (not notebooks): `config.toml`, a full four-model pipeline mirroring `full_pipeline.py`, and `graphviz.toml`, a commented `satterc graph --style` template. Neither is loaded by any code or tooling (`just export`/`marimo check` only touch `.py`); they are user-facing references that the docs link to.
