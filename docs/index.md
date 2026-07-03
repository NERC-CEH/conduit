---
title: Home
icon: lucide/house
---

# conduit

**Turn a working research script into a contract-checked, reproducible, scalable pipeline —
without a rewrite.**

You keep writing plain, typed [xarray](https://xarray.dev) functions. conduit adds
three things that are hard to get any other way:

- **Look before you leap.** The *entire* DAG is proven consistent *before any compute runs*,
  straight from your type annotations — not just units, but dimensions, coordinates, dtypes,
  **and the wiring itself**. A hPa-vs-Pa slip, a transposed axis, or a renamed input is caught
  at build time, not part-way through a run. `--dry-run` validates your files' headers against
  what each node declares without executing a single node; runtime unit conversion comes along
  for free.
- **Config *is* the DAG.** Describe — and compose, parameterise and fan out — a whole pipeline
  in a plain [TOML](https://toml.io) file. The config doubles as a complete, reproducible
  provenance record of the run.
- **Scale-up as a config knob, not a rewrite.** The *same* functions run in-memory,
  out-of-core ([dask](https://www.dask.org/)), or across parallel processes writing to a
  shared Zarr store — driven by config, not by rewriting your code.

Under the hood conduit composes [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton)
(the DAG engine), xarray (labelled N-D arrays), and
[xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) /
[pint](https://pint.readthedocs.io) / [cf-xarray](https://cf-xarray.readthedocs.io) (the
contract layer). The value is not the parts but where they *compose*: whole-graph contract
checking is only possible when the annotations and the graph are both present, and scale is
only free when the graph is separate from the functions. The aim is to let you get that value
**without** having to learn Hamilton or pint — you write ordinary annotated functions and
describe how they wire together. When you *do* want the underlying machinery, conduit
exposes the Hamilton driver and xarray objects rather than hiding them.

The core is fully domain-agnostic: forward models, land-cover classification, and analysis
pipelines are all expressed the same way — nothing carbon-specific is baked in. Gridded,
geospatial Zarr — the primary target data type — is a first-class **optional** layer
(`conduit[geo]`) rather than a core assumption.

## Installation

See the [Installation guide](getting_started/installation.md).

## Quick start

Get a pipeline running in a few minutes — see the [Quickstart](getting_started/quickstart.md).

## Key features

- **Whole-DAG contract checking before compute** — declare a node's expectations with a
  simple `Annotated[DataArray, ...]` convention and conduit proves the *entire graph*
  consistent **before** any compute runs. Generic over every facet: units (convert
  compatible inputs, reject incompatible), dimensions, coordinates and dtypes. This is the
  flagship feature.
- **Wiring validation** — the same before-compute guarantee for the plumbing: unbound inputs
  (a file/config/signature rename drift) raise, unused inputs warn, so typos surface at build
  time rather than mid-run.
- **`--dry-run`** — validate loaded files' headers against every declared consumer contract
  *and* the wiring, without executing a single node.
- **Config-as-DAG** — describe how your functions wire together in a plain
  [TOML](https://toml.io) file: import your own modules (`_import_path`) or define glue nodes
  inline (`[[node]]`), with `for_each` fan-out and `{var}` templating to generate many nodes
  from one spec. Explicit, aliasable file↔node mapping (`{node_name: file_var}`) with
  collision detection; the config is stamped into outputs as a reproducible provenance record.
- **Scale without a rewrite** — the same functions run in-memory, out-of-core (dask), with
  content-addressed result caching, memory-bounded blocked execution, or parallel subset
  runs over a shared Zarr store — all driven by config, not code changes.
- **Reusable transforms & presets** — annotation-preserving transforms (e.g. `resample`)
  wired in as passthrough nodes; `[[resample]]` is a thin preset over the general fan-out
  engine.
- **Domain-agnostic core, optional gridded layer** — works with whatever dimensions your data
  has; CRS-aware `(y,x)`↔`pixel` stacking, reprojection and parallel Zarr I/O live in the
  optional `conduit.gridded` subpackage (`conduit[geo]`) behind a nested `conduit gridded` CLI.
- **CLI and Python API** — run from the terminal (`conduit run`) or embed in a notebook;
  conduit exposes the Hamilton driver and xarray objects rather than hiding them.

## Learn more

- [Quickstart](getting_started/quickstart.md) — run your first pipeline
- [Concepts](getting_started/concepts.md) — how the DAG and config fit together
- [Configuration](usage/config.md) — TOML config reference
- [Custom modules](usage/custom-modules.md) — bring your own nodes
- [Examples](examples/getting_started.md) — annotated, runnable notebooks

## Acknowledgements

conduit builds on the following open-source projects:

- [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) — DAG-based dataflow framework
- [xarray](https://docs.xarray.dev/) — N-D labelled arrays and datasets
- [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) — per-function unit/dim/dtype/coord contracts
- [pint](https://pint.readthedocs.io) & [cf-xarray](https://cf-xarray.readthedocs.io) — units
- [dask](https://www.dask.org/) — parallel and out-of-core computation
- [Typer](https://typer.tiangolo.com/) — CLI framework
