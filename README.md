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

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and
packaging. To get started:

```bash
git clone https://github.com/NERC-CEH/conduit.git
cd conduit
uv sync
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full development guide — pre-commit
hooks, `just` tasks, building the docs, and PR conventions.

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

