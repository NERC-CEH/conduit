---
title: Contributing
icon: lucide/code
---

# Contributing

## Design Philosophy

breadboard is built around a few core principles that shape every design decision.

### DAG-first

Every pipeline is a Directed Acyclic Graph. This isn't an implementation detail — it's the primary abstraction. You declare **what** you want computed (the output variables) and the DAG engine figures out **how** to compute it. This gives you:

- **Automatic dependency resolution** — no need to manually order model calls
- **Lazy execution** — only the nodes required for your requested outputs are run
- **Reproducibility** — every output is a pure function of its inputs
- **Composability** — models are independent modules that can be mixed and matched

### Config-driven

Pipelines are described by TOML configuration files, not Python scripts. This keeps the barrier to entry low — you don't need to know Python to run a pipeline. The config is the single source of truth for what the pipeline does, making it easy to version, share, and review.

### Model independence

Each model (SPLASH, P-Model, SGAM, RothC) is a self-contained Python module. Models declare their inputs by their function parameter names and their outputs by their return values. They don't know about each other — the DAG connects them. This means:

- Adding a new model doesn't require changing existing code
- Models can be tested in isolation
- Custom models follow the same conventions as built-in ones

### Hamilton as the engine

breadboard is built on [Hamilton](https://github.com/dagworks-inc/hamilton), a DAG-based dataflow framework. Rather than reinventing the wheel, breadboard focuses on domain-specific concerns (terrestrial carbon modelling, climate data handling) while delegating graph construction and execution to a mature library.

## Development Setup

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Clone and install

```bash
git clone https://github.com/NERC-CEH/breadboard.git
cd breadboard
uv sync
source .venv/bin/activate
```

(Or prefix all commands with `uv run`.)

### Pre-commit hooks

```bash
uv run pre-commit install
```

After this, linting and tests run automatically before every commit.

### Useful commands

The project uses [just](https://github.com/casey/just) for shortcuts:

```bash
just test        # run the test suite (pytest)
just lint        # format and lint code with ruff, check examples with marimo
just docs        # build the docs (zensical)
just export <x>  # export a notebook example to docs
just export-all  # export all example notebooks
```

## Adding modules and nodes

breadboard is domain-agnostic — it ships no built-in models. You add functionality from
*outside* the package by writing your own Hamilton-compatible module and referencing it
from a config section via `_import_path`. See [Custom modules](../usage/custom-modules.md)
for the conventions (function name = node name, parameters = upstream node names,
`Annotated[DataArray, "<unit>"]` for unit declarations).

The only modules that live inside the package are the generic built-ins (`node`,
`resample`) registered in the `MODULES` dict in `src/breadboard/dag/driver.py`.

## Documentation

The docs are built with [zensical](https://zensical.org/):

```bash
just docs
```

Then open `site/index.html` in your browser.

When adding or changing documentation:

- Follow the existing page structure and conventions
- Use admonitions (`/// admonition | Title\n    type: note`) for callouts
- Link to related pages using relative paths
- Run `just docs` to verify the build succeeds with no warnings

## Pull Requests

- Keep changes focused — one feature or fix per PR
- Add tests for new functionality
- Update documentation as needed
- Run `just test` before submitting to ensure linting and tests pass
