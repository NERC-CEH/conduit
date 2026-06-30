# `breadboard`

An opinionated [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) +
[xarray](https://xarray.dev) + [pint](https://pint.readthedocs.io) foundation for
building configurable, unit-aware data pipelines and forward models in geoscience
and environmental science.

This is a work in progress - expect **very** sharp edges.

For usage instructions see the [documentation](https://NERC-CEH.github.io/breadboard) (this is also WIP!)

## Developer instructions

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and packaging.

### Prerequisites

* Python 3.13
* `uv` installed (see [docs](https://docs.astral.sh/uv/getting-started/installation/))

### Setup for Development

1. **Clone the repository:**

```bash
git clone https://github.com/NERC-CEH/breadboard.git
cd breadboard
```


2. **Create a virtual environment and install dependencies:**

```bash
uv sync
```


3. **Activate the environment:**

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

(Or prefix all commands with `uv run`.)


### Pre-commit hooks

This project uses [pre-commit](https://pre-commit.com/) to run linting and tests automatically before each commit.

**First-time setup:**

```bash
uv run pre-commit install
```

After this, `just lint` and `just test` will run automatically before every `git commit`. If either fails, the commit is aborted — fix the issues and try again.

To run hooks manually without committing:

```bash
uv run pre-commit run --all-files
```

### Building the docs

Build the docs with 

```bash
zensical build
```

Next, open `site/index.html` in your browser.

See [zensical.org](https://zensical.org/) for more details.


### Useful short-cuts

The awesome [`just`](https://github.com/casey/just) is a development dependency that will be installed when you run `uv sync`.

You can run the following commands anywhere in the repository:

```bash
just test        # run the test suite (pytest)
just lint        # format and lint code with ruff, check examples with marimo
just docs        # build the docs (zensical)
just export <x>  # export a notebook example to docs (e.g. just export getting_started)
just export-all  # export all example notebooks
```

## CLI use

Installing `breadboard` will install the `breadboard` command.
You can explore the documentation using the `-h` or `--help` flags, e.g.

```bash
breadboard -h  # help for the base command
breadboard graph -h  # help for the 'graph' subcommand
```

### Generate a visualisation of the DAG

```bash
breadboard graph config.toml --pdf  # or --png
```

> [!NOTE]
> This requires graphviz to be installed. E.g. `sudo apt install graphviz` (Ubuntu) or `brew install graphviz` (MacOS).

### Run

```bash
mkdir outputs
breadboard run config.toml
```

This will produce three netcdf files in `outputs/`, for daily, weekly and monthly output data.

