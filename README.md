# `conduit`

Turn a working research script into a **contract-checked, reproducible, scalable** pipeline
— without a rewrite. You keep writing plain, typed [xarray](https://xarray.dev) functions;
conduit adds three things that are hard to get any other way:

- **Look before you leap.** The *entire* DAG is proven consistent *before any compute runs*,
  straight from your type annotations — not just units, but dimensions, coordinates, dtypes,
  **and the wiring itself**. Catch a hPa-vs-Pa mistake, a transposed axis, or a renamed input
  at build time, not 40 minutes into a run. `--dry-run` validates your files' headers against
  what each node expects without executing a single node.
- **Config *is* the DAG.** Describe — and compose, parameterise and fan out — a whole pipeline
  in a plain [TOML](https://toml.io) file. Import your own modules or define glue nodes inline;
  the config doubles as a complete, reproducible provenance record of the run.
- **Scale-up as a config knob, not a rewrite.** The same functions run in-memory, out-of-core
  ([dask](https://www.dask.org/)), or across parallel processes over Zarr — you change the
  config, not the code.

Under the hood it composes [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton)
(the DAG), xarray (labelled N-D arrays), and
[xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) /
[pint](https://pint.readthedocs.io) / [cf-xarray](https://cf-xarray.readthedocs.io)
(the contract layer) — but the point is to let you *not* have to learn them: you write
ordinary annotated functions and describe how they wire together, and conduit handles the
rest. The core is fully domain-agnostic; gridded/geospatial Zarr — the primary target data
type — is a first-class **optional** layer (`conduit[geo]`), not baked into the core.

This is a work in progress - expect **very** sharp edges.

For usage instructions see the [documentation](https://NERC-CEH.github.io/conduit) (this is also WIP!)

## Developer instructions

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and packaging.

### Prerequisites

* Python 3.13
* `uv` installed (see [docs](https://docs.astral.sh/uv/getting-started/installation/))

### Setup for Development

1. **Clone the repository:**

```bash
git clone https://github.com/NERC-CEH/conduit.git
cd conduit
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

Installing `conduit` will install the `conduit` command.
You can explore the documentation using the `-h` or `--help` flags, e.g.

```bash
conduit -h          # help for the base command
conduit graph -h    # help for the 'graph' subcommand
conduit gridded -h  # help for the optional gridded (parallel Zarr) commands
```

### Generate a visualisation of the DAG

```bash
conduit graph config.toml --pdf  # or --png
```

> [!NOTE]
> This requires graphviz to be installed. E.g. `sudo apt install graphviz` (Ubuntu) or `brew install graphviz` (MacOS).

### Run

```bash
conduit run config.toml            # execute the pipeline
conduit run config.toml --dry-run  # validate contracts + wiring against file headers, no compute
```

`run` writes one output file per `[outputs.*]` section defined in the config.

### Parallel Zarr over a subset (optional, `conduit[geo]`)

For gridded data you can split a run across processes, each writing a disjoint pixel
subset into one shared Zarr store:

```bash
conduit gridded create-store config.toml   # pre-create the empty store(s)
conduit run config.toml                     # (per subset, e.g. via a job array)
conduit gridded merge config.toml           # stitch subsets back into one file per output
```

