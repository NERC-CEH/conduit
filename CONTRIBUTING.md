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

The docs are built with [zensical](https://zensical.org/):

```bash
just docs      # exports the recipe notebooks, then builds into site/
```

`just docs` depends on `just docs-recipes`, which runs each recipe's marimo notebook through `marimo-md-export`. That executes the pipelines, so a docs build is also a check that the recipes still work.

The structure is five tabs, and each topic has exactly one owner page:

| Tab | Holds |
| --- | --- |
| Home | the pitch and one worked example |
| How it works | the design, and the limits of the contract check |
| Guides | how to do things, split into Authoring / Running / Scaling |
| Recipes | complete worked pipelines |
| Reference | config schema, data formats, Python API, CLI, module docstrings |

When adding or changing documentation:

- Find the page that owns the topic and edit that one. If you need to mention it elsewhere, link. The reorganisation that produced this structure existed to remove the same explanation from five places.
- One sentence per line in Markdown files. It keeps diffs readable; rendering is unaffected.
- Link between pages with relative paths, and run `just docs` to confirm the build is clean. `pymdownx.snippets` runs with `check_paths = true`, so a stale `--8<--` path fails the build.

### Adding a recipe

A recipe is a complete worked pipeline in `recipes/<name>/`, containing:

- `nodes.py` — the node functions
- `config.toml` — the pipeline
- `make_data.py` — a deterministic generator for synthetic inputs, exposing `write_inputs(data_dir)`
- `demo.py` — a marimo notebook that runs it, with a PEP 723 header so `uvx marimo edit --sandbox` works without a checkout
- a page in `docs/recipes/`, plus a `docs-recipes` line in the `justfile` exporting the notebook

Add it to `tests/test_recipes.py` as well. Every recipe is executed by the test suite and again by the docs build, so nothing can drift silently.

## Pull requests

- Keep changes focused — one feature or fix per PR.
- Add tests for new functionality (coverage gate is 90%).
- Update documentation as needed.
- Run `just lint typecheck test` before submitting.
