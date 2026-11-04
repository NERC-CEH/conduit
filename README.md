# Catena

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev) for building configurable environmental data pipelines.

Working with Catena falls into four stages:

1. **Write the science code.** Ordinary Python functions that take and return `xarray.DataArray`s, with optional [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) declaring what each one requires and produces: units, dimensions, coordinates, dtype, temporal frequency.
2. **Write the config.** A TOML file names the input files, the nodes and the outputs. Assembling or adapting a pipeline from here needs no Python.
3. **Validate.** Catena assembles the whole graph before computing anything and checks every declared edge against the claim at the other end, via [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/). A unit mismatch fails at the terminal in a second rather than forty minutes into a run.
4. **Run.** In memory, out-of-core with dask, memory-bounded in blocks, or sharded across processes. The choice lives in the config, and none of it changes the science code.

> [!WARNING]
> **Alpha status.** `catena` is an early-stage project under active development. Things will change without warning.

Full user documentation at [nerc-ceh.github.io/catena](https://nerc-ceh.github.io/catena).

## Installation

Catena is not yet on PyPI so you need to install from GitHub.
It installs as `ukceh-catena` and imports as `catena`.
Installation via `uv` is recommended.

```sh
uv add "ukceh-catena[all] @ git+https://github.com/NERC-CEH/catena"
```

`pip` is also fine.

```sh
pip install "ukceh-catena[all] @ git+https://github.com/NERC-CEH/catena"
```

See the [installation guide](https://nerc-ceh.github.io/catena/guides/install.html) for more info.

## Usage

### From the command line

```sh
catena graph config.toml --pdf    # graphviz digraph as a pdf
catena run config.toml --dry-run  # validate contracts and wiring
catena run config.toml            # execute
```

### From a Python session

```python
import catena

digraph = catena.build_graph("config.toml")  # styled graphviz.Digraph
report = catena.dry_run("config.toml")  # validate contracts and wiring
datasets = catena.run("config.toml")  # execute and return outputs
```

## Contributing

Contributions welcome but be mindful that this is a very early-stage project, so novel feature ideas might end up further down the priority list than you might hope.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Acknowledgements

This work was funded by NC-International.
