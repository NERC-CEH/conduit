---
title: Why conduit?
icon: lucide/lightbulb
---

# Why conduit?

conduit turns a working research script into a **contract-checked, reproducible,
scalable** pipeline — without a rewrite. You keep writing plain, typed xarray functions;
conduit adds three things that are hard to get any other way.

## The three things

- **Look before you leap.** The *entire* DAG is proven consistent *before any compute
  runs*, straight from your type annotations — not just units, but dimensions,
  coordinates, dtypes, **and the wiring itself**. A hPa-vs-Pa slip, a transposed axis or
  a renamed input is caught at build time, not part-way through a run. See
  [Contracts before compute](contracts.md).
- **Config *is* the DAG.** A whole pipeline — including dynamically generated nodes — is
  described, composed and parameterised in a plain [TOML](https://toml.io) file. The
  config doubles as a complete, reproducible provenance record. See
  [The DAG model](dag-model.md).
- **Scale-up as a config knob, not a rewrite.** The *same* functions run in-memory,
  out-of-core, or across parallel processes writing to a shared Zarr store — driven by
  config, not by rewriting code. See [Scaling model](scaling.md).

## The value is the composition

conduit composes [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) (the DAG
engine), [xarray](https://xarray.dev) (labelled N-D arrays), and
[xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) /
[pint](https://pint.readthedocs.io) / [cf-xarray](https://cf-xarray.readthedocs.io) (the
contract layer). The value is not the parts but *where they compose*:

- Whole-graph contract checking is only possible when the annotations **and** the graph
  are both present.
- Scale is only free when the graph is **separate** from the functions.

Neither property is available from any single one of those libraries. conduit's job is
to make them fall out of writing ordinary annotated functions and describing how they
wire together — **without** requiring you to learn Hamilton or pint. When you *do* want
the underlying machinery, conduit exposes the Hamilton driver and xarray objects rather
than hiding them.

## Design principles

These principles shape every design decision.

### DAG-first

Every pipeline is a Directed Acyclic Graph — not an implementation detail but the
primary abstraction. You declare *what* to compute (the outputs); the engine works out
*how*. This is what enables dependency resolution, lazy execution, reproducibility and
before-compute checking.

### Config-driven

Pipelines are described by TOML, not Python scripts. This keeps the barrier to entry
low — you can run and compose a pipeline without writing Python — and makes the pipeline
easy to version, share and review. The config is the single source of truth.

### Module independence

A node knows only its own inputs (by parameter name) and output (by return); it knows
nothing of its neighbours. The DAG connects them. So you add a computation without
touching existing code, test each module in isolation, and mix and match freely. Custom
modules follow exactly the same conventions as the built-ins.

### Expose, don't wrap

conduit is an *opinionated integration*, not an opaque framework. Its job is to make the
Hamilton + xarray + contract stack compose; where you need the underlying machinery, it
is exposed rather than hidden. Favour reaching for Hamilton and xarray directly over
adding a wrapper.

### Domain-agnostic core

Nothing domain-specific is baked in — forward models, land-cover classification and
analysis pipelines are all expressed the same way. Gridded, geospatial Zarr — the
primary target data type — is a first-class **optional** layer (`conduit[geo]`), not a
core assumption, so importing conduit never pulls geospatial dependencies.

## See also

- [The DAG model](dag-model.md) — the abstraction in detail.
- [Contracts before compute](contracts.md) — the flagship feature.
- [Scaling model](scaling.md) — why the same functions scale for free.
