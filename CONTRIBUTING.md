# Contributing to conduit

This guide covers setting up a development checkout and the conventions we follow.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Set up for development

```bash
git clone https://github.com/NERC-CEH/conduit.git
cd conduit
uv sync
```

either `source .venv/bin/activate` or prefix all commands with `uv run`.
(Or use `direnv`!)


## Pre-commit hooks

```bash
pre-commit install
```

Pre-commit runs `uv-lock`, `pyright`, and `ruff` on every commit.
If a hook fails, the commit is aborted; fix the issues and try again. 

To run the hooks manually:

```bash
pre-commit run --all-files
```

## Common tasks

You can use [`just`](https://github.com/casey/just) (installed by `uv sync`) for common tasks, e.g.

```bash
just lint          # ruff format + check (modifies files)
just typecheck     # pyright static type check
just test          # pytest
just docs          # build the docs with zensical
```

Run `just -l` to list all available commands.


## Documentation

The docs are built with [zensical](https://zensical.org/).

`just docs` depends on `just docs-recipes`, which runs each recipe's marimo notebook through `marimo-md-export`.
That executes the pipelines, so a docs build is also a check that the recipes still work.
It takes a while though.

The docs are structured under five tabs:

| Tab | Holds |
| --- | --- |
| Home | the pitch and one worked example |
| How it works | the design, and the limits of the contract check |
| Guides | how to do things, split into Authoring / Running / Scaling |
| Recipes | complete worked pipelines |
| Reference | config schema, data formats, Python API, CLI, module docstrings |


House style is **one sentence per line in Markdown files.**
It keeps diffs readable; rendering is unaffected.

### Adding a recipe

A recipe is a complete worked pipeline in `recipes/<name>/`, containing:

- `nodes.py` — the node functions
- `config.toml` — the pipeline
- `make_data.py` — a deterministic generator for synthetic inputs, exposing `write_inputs(data_dir)`
- `demo.py` — a marimo notebook that runs it, with a PEP 723 header so `uvx marimo edit --sandbox` works without a checkout
- a page in `docs/recipes/`, plus a `docs-recipes` line in the `justfile` exporting the notebook

Add it to `tests/test_recipes.py` as well.

## Pull requests

- Keep changes focused — one feature or fix per PR.
- Add tests for new functionality (coverage gate is 90% --- run `just test-cov`).
- Update documentation as needed.
- Run `just lint typecheck test` or the pre-commit hooks before submitting.
