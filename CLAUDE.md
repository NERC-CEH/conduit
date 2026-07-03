# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

conduit is in **alpha** with no external users. It was extracted from the
(now-archived) `satterc` terrestrial-carbon framework to become a general-purpose,
domain-agnostic foundation for data pipelines and forward models. Backwards
compatibility is *not* a constraint: prefer the cleanest design and make breaking
changes (config schema, public APIs, behaviour) freely rather than adding
compatibility shims.

The initial satterc→conduit refactor (rename, strip carbon models, generalise the
I/O layer) is done. A subsequent **generalisation pass** (see
`notes/GENERALISATION_PLAN.md`) then landed the current architecture:
whole-DAG **contract** checking generic over all `xarray-annotated` facets
(units + dims/coords/dtype); before-compute **wiring** validation; an explicit,
aliasable file↔node **mapping** with provenance stamping; a general **fan-out
`[[node]]`** engine with `[[resample]]` as a preset over an annotation-preserving
transform; and extraction of the geospatial + parallel-Zarr code into the optional
**`conduit.gridded`** subpackage so the core is domain-agnostic. Backwards
compatibility remained a non-constraint throughout.

## Guiding philosophy

conduit is an opinionated integration of Apache Hamilton (DAG), xarray (+ dask
for scaling), and `xarray-annotated` (contract validation: units + dims/coords/
dtype), driven by a TOML spec that can describe a whole DAG — including
dynamically generated nodes — in plain text. Its value is the *integration*;
favour **exposing** Hamilton and xarray machinery over building opaque wrappers.
The flagship feature is lifting `xarray-annotated`'s per-function contracts to a
whole-DAG, before-compute guarantee (`dag/contract_check.py`); preserve and extend
it, don't bypass it.

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

conduit uses [Hamilton](https://github.com/DAGWorks-Inc/hamilton) to define
computational DAGs that transform xarray inputs through user-supplied modules into
outputs, with a TOML configuration spec and runtime/build-time **contract**
validation (units + dims/coords/dtype, via `xarray-annotated`).

### Core modules

**`src/conduit/config.py`** — parses TOML config files into a `ParsedConfig` dataclass. Recognised top-level sections: `[inputs.*]`, `[outputs.*]`, `[grid]` (silently accepted), `[[node]]`, `[[resample]]`, `[cache]`, `[blocking]`, `[subset]`, `[annotations]` (legacy alias `[units]`). **Any other section is treated as a user module and must include `_import_path = "pkg.module"`** — there is no special "models" namespace; user models are just modules. Key types exported: `Config`, `ParsedConfig`, `IOSpec`, `ResampleSpec`, `NodeSpec`, `CacheSpec`, `BlockingSpec`, `SubsetSpec`. Fan-out helpers: `expand_node_entries` (`{var}`/`for_each` templating), `resample_to_node_entry` (the `[[resample]]` preset desugarer).

**`src/conduit/dag/driver.py`** — builds Hamilton `Driver` objects from a `ParsedConfig`. The `MODULES` dict maps the one built-in short name (`"node"`) to its path; every other module identifier is a dotted `_import_path` imported directly ([[resample]] desugars into `node` specs). `build_driver` also runs the build-time contract check (`check_dag_contracts`).

**`src/conduit/dag/contract_check.py`** — the flagship subsystem: lifts `xarray-annotated`'s per-function contract validation to the **whole DAG, before compute**, generic over every facet (units + dims/coords/dtype) via a facet registry. `check_dag_contracts` verifies every internal edge whose producer and consumer both declare a contract; `check_input_contracts` validates loaded inputs' metadata against declared consumers without executing a node (the basis of `run --dry-run`). Passthrough-tagged nodes (`conduit.dag.node.PASSTHROUGH_TAG`) propagate contracts generically. Units/policy machinery lives in the `xarray-annotated` dependency (`declare_units`/`declare_schema`, `[annotations]` policy), not in conduit.

**`src/conduit/dag/wiring_check.py`** — `check_wiring`: the wiring analogue of the contract check. Diffs the DAG's required external inputs against what `load_inputs` produced — **unbound** inputs raise, **unused** inputs warn — before any compute.

**`src/conduit/io.py`** — domain-agnostic I/O, outside the Hamilton DAG. Key public functions:
- `load_inputs(input_specs)` — reads NetCDF/Zarr/CSV/Parquet/JSON/TOML; returns a flat dict of named `DataArray`s. `IOSpec.vars` maps file variables to node names, either by list (`{var}{suffix}`, `dates_{label}`) or an explicit `{node_name: file_var}` alias (`io.var_mapping`).
- `get_outputs` / `save_outputs` — assemble/write per-section `Dataset`s; `save_outputs` can stamp config provenance into outputs.
- `get_final_vars(output_specs)` — the flat node-name list for `driver.execute(final_vars=...)`.

Core `io` is CRS/pixel-free: it delegates the gridded path to `conduit.gridded` lazily (only when CRS metadata or a `[subset]` is present), so importing conduit never pulls `rioxarray`/`pyproj`.

**`src/conduit/gridded/`** — optional geospatial + parallel-Zarr layer (behind the `geo` extra). `spatial.py` + `io.py`: CRS-aware `(y,x)`↔`pixel` stacking, `latitude`/`longitude` reprojection, `MisalignedGridError`, and the subset/Zarr-region parallel-write path (`create_output_store`, `save_zarr_region`, `merge_subset_outputs`). `cli.py`: the nested `conduit gridded` commands.

**`src/conduit/transforms.py`** — reusable annotation-preserving DAG transforms referenced from config (currently just `resample`); wired in as passthrough nodes by the `[[resample]]` preset. (A single module for now; promote to a package if a second transform needs its own file.)

**`src/conduit/dag/`** — other built-in DAG machinery:
- `node.py` — generates Hamilton modules from `[[node]]` entries via `exec()`: inline expressions or import-path + function, optional declared `units`/`dims`/`dtype`/`coords`, `for_each` fan-out, and passthrough tagging. The "user model in TOML" path.
- `caching.py` — content-based fingerprint for `xarray.DataArray` + `Builder.with_cache()` from a `CacheSpec`
- `blocking.py` — blocked driver execution over a partition dim (default `pixel`)

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
The built-in `node` module is addressable by its short name; `[[resample]]` is a
preset that desugars into `node` specs.

### CLI

The `typer`-based CLI (`src/conduit/cli/`) has commands: `run`, `graph`
(visualise DAG as PDF/PNG/DOT), `version`, and a nested `gridded` group
(`conduit gridded create-store` / `merge`, for parallel subset runs). All are
model-agnostic.

### Testing

Tests in `tests/` use session-scoped fixtures that generate synthetic netCDF data once (`tests/conftest.py`) via `tests/synthetic_data.py` — a small, plain-numpy/xarray helper (`write_synthetic_inputs`) that writes four gridded files (daily/weekly/monthly/static) on a lat/lon grid using a domain-neutral geophysical vocabulary with explicit per-variable value shapes (gaussian/positive/bounded/integer). It lives under `tests/` (not the shipped package) and reuses only `conduit.gridded.io.unstack_if_gridded` so the on-disk grid/CRS layout matches what `load_inputs` reads back. The session pipeline (`tests/test_config.toml`) is model-free: a single `[[node]]` derived variable stands in for a model. Coverage gate is 90% (`just test-cov`).

### Examples

`examples/` holds two marimo notebooks — `getting_started.py` (end-to-end pipeline) and
`unit_safe_pipelines.py` (the units feature) — each pinning `conduit==<version>` in its
inline `# /// script` block (update on a version bump, then `just export-all`). It also
holds `graphviz.toml`, a commented `conduit graph --style` template (a user-facing
reference, not loaded by any tooling).
