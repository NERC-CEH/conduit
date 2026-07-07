# Contributing to conduit

Thanks for your interest in conduit! This guide covers setting up a development checkout and the conventions we follow.

## Prerequisites

- **Python 3.13**
- **[uv](https://docs.astral.sh/uv/)** for dependency management and packaging
  (see the [install guide](https://docs.astral.sh/uv/getting-started/installation/))

## Set up for development

```bash
git clone https://github.com/NERC-CEH/conduit.git
cd conduit
uv sync
source .venv/bin/activate    # on Windows: .venv\Scripts\activate
```

`uv sync` installs every optional extra (`geo`, `viz`) along with the development tooling, so you don't need to request them explicitly. (Or prefix all commands with `uv run` instead of activating the environment.)

## Pre-commit hooks

```bash
uv run pre-commit install
```

Pre-commit runs `uv-lock`, `pyright`, and `ruff` on every commit — not the full test suite. If a hook fails, the commit is aborted; fix the issues and try again. 

To run the hooks manually:

```bash
uv run pre-commit run --all-files
```

## Common tasks

You can use [`just`](https://github.com/casey/just) (installed by `uv sync`) for common tasks:

```bash
just lint          # ruff format + check (modifies files)
just lint-check    # read-only variant (used in CI)
just typecheck     # pyright static type check
just test          # pytest
just test-cov      # pytest with coverage (fails under 90%)
just docs          # build the docs with zensical
```

Run a single test file:

```bash
uv run pytest tests/test_config.py -v
```


## Documentation

The docs are built with [zensical](https://zensical.org/) and organised around the [Diátaxis](https://diataxis.fr/) framework (Get started / Guides / Reference / Concepts):

```bash
just docs      # then open site/index.html
```

When adding or changing documentation:

- Put each page in the quadrant that fits its purpose (a tutorial teaches, a guide solves a task, a reference describes, a concept explains).
- Follow the existing page structure; use admonitions (`/// admonition | Title\n    type: note`) for callouts.
- Link between pages with relative paths. Run `just docs` and confirm the build succeeds with no warnings.

## Pull requests

- Keep changes focused — one feature or fix per PR.
- Add tests for new functionality (coverage gate is 90%).
- Update documentation as needed.
- Run `just lint typecheck test` before submitting.
