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

A **code-review remediation pass** (`notes/CODE_REVIEW_2026-07-13.md` and its
plan) then fixed the correctness gaps that survived, and removed the shims this
file says shouldn't exist. Notable results a returning reader should know:
`conduit.specs` (the data model) is now separate from `conduit.config` (the
parser), which breaks the old import cycle; `conduit.formats` is the single
file-format registry; `[subset]` takes `dim`/`start`/`stop` (not
`pixel_start`/`pixel_end`) and, like `[blocking]`, partitions any dimension; the
`[units]` alias, `[grid]` and `[graphviz]` sections are gone (unknown sections are
now an error, not silently ignored); and `conduit graph` derives its frequency
grouping from declared `Freq` contracts rather than name suffixes.

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
just lint            # ruff format + check --fix (modifies files)
just lint-check      # same as lint but read-only (used in CI)
just typecheck       # pyright static type check
just test            # pytest only (no lint)
just test-cov        # pytest with coverage report (fails under 90%)
just docs            # build docs with zensical
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

Each module's own docstring is the canonical explanation of its design; these are
one-line pointers, deliberately not restatements. When a design changes, the module
docstring is what must be right.

| Module | What it is |
|---|---|
| **`specs.py`** | The parsed data model: one dataclass per config section (`IOSpec`, `NodeSpec`, `SubsetSpec`, `AnnotationPolicySpec`, `ParsedConfig`, …), each self-validating in `from_config`. A **leaf** — imports nothing from conduit, which is what keeps `config`/`io`/`checks` acyclic. |
| **`config.py`** | TOML → `ParsedConfig`. Section dispatch, `{var}`/`for_each` fan-out (`expand_node_entries`), the `[[resample]]` desugarer (`resample_to_node_entry`), path resolution. **Any section not recognised is a user module and must carry `_import_path`** — there is no "models" namespace, and unknown sections are an error, not ignored. |
| **`formats.py`** | The single file-format registry. Every extension-based decision (which reader, which writer, subset-capable?, needs a store?) is one `Format` entry and a `format_for()` lookup. Adding a format means adding one row. |
| **`io.py`** | Domain-agnostic I/O, outside the DAG: `load_inputs` / `get_outputs` / `save_outputs` / `get_final_vars`, plus `time_dims` / `sole_time_dim` (the single time-axis detector — `time` is never assumed). CRS/pixel-free. |
| **`dag/contract_check.py`** | **The flagship.** Lifts `xarray-annotated`'s per-function contracts to the whole DAG, before compute, generic over every facet via a facet registry. Its module docstring is the canonical essay on facets and passthrough propagation. |
| **`dag/wiring_check.py`** | The wiring analogue: unbound inputs raise, unused inputs warn, before any compute. |
| **`dag/driver.py`** | `ParsedConfig` → Hamilton `Driver`. `"node"` is the one built-in short name (generated from `node_specs`); every other identifier is a dotted `_import_path`. Runs the build-time contract check. |
| **`dag/node.py`** | Generates Hamilton modules from `[[node]]` entries via `exec()` — the "user model in TOML" path. Node names/inputs are validated as identifiers at parse time. |
| **`dag/caching.py`** | Content-based `DataArray` fingerprint (values, name, dims, coords **and attrs**) + `Builder.with_cache()`. |
| **`dag/blocking.py`** | Blocked execution over a partition dim (default `pixel`). |
| **`transforms.py`** | Annotation-preserving transforms referenced from config (currently just `resample`), wired in as passthrough nodes. |
| **`gridded/`** | Optional geospatial + parallel-Zarr layer (the `geo` extra). Its `__init__` docstring states the lazy-import policy once. |
| **`checks.py`** | Input-compatibility checks declared under `[validation]`, run before compute. |

Two things worth knowing that are *not* obvious from any one module:

- **Section labels are inert.** `daily` / `weekly` / `static` name nodes via a suffix and
  mean nothing else — no frequency, no semantics, is inferred from them. A pipeline may
  label sections `raw`/`smoothed` and everything (including `graph`'s clustering) works
  identically. Frequency comes from *declared* `Freq` contracts, never from a name.
- **`create_output_store` probes the DAG over a single pixel** to derive each output's
  non-`pixel` axes, so the store's layout is by construction what subset runs write —
  including axes no input file has (a `[[resample]]`'s time axis).

### Hamilton DAG conventions (for user-defined modules)

Each module contains plain functions that become DAG nodes. The conventions a user
model follows:

- **Public node function name = the output node name** (single-output), or use `@extract_fields()` (from `hamilton.function_modifiers`) with a `TypedDict` return to split into multiple named outputs.
- `@declare_units` (innermost) reads `Annotated[DataArray, "<unit>"]` from the signature/return and validates/stamps units.
- **Parameter names = input node names** (following io.py's `{var}{suffix}` / bare-static / `latitude` conventions).
- **Keyword-only args (after `*`) = config parameters**, populated from the module's own config section. These share one flat namespace across all sections (that is how Hamilton resolves them by name), so a collision is a parse-time error naming both sections.

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

`examples/` holds `graphviz.toml`, a commented `conduit graph --style` template (a
user-facing reference, not loaded by any tooling). The hands-on tutorials live in the docs
(`docs/get-started/`, `docs/guides/`) as prose pages rather than exported marimo notebooks;
`notes/DOCS_DRIFT_GUARDS.md` tracks the deferred plan to make those pages executable again.
