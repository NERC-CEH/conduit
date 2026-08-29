# Conduit

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev) for building configurable environmental data pipelines.

Working with Conduit falls into four stages:

1. **Write the science code.** Ordinary Python functions that take and return `xarray.DataArray`s, with optional [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) declaring what each one requires and produces: units, dimensions, coordinates, dtype, temporal frequency.
2. **Write the config.** A TOML file names the input files, the nodes and the outputs. Assembling or adapting a pipeline from here needs no Python.
3. **Validate.** Conduit assembles the whole graph before computing anything and checks every declared edge against the claim at the other end, via [`xarray-annotated`](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/). A unit mismatch fails at the terminal in a second rather than forty minutes into a run.
4. **Run.** In memory, out-of-core with dask, memory-bounded in blocks, or sharded across processes. The choice lives in the config, and none of it changes the science code.

> [!WARNING]
> **Alpha status.** `conduit` is an early-stage project under active development. Things will change without warning.

Full user documentation at [nerc-ceh.github.io/conduit](https://nerc-ceh.github.io/conduit).

## Installation

Conduit is not yet on PyPI so you need to install from GitHub.
Installation via `uv` is recommended.

```sh
uv add "conduit[all] @ git+https://github.com/NERC-CEH/conduit"
```

`pip` is also fine.

```sh
pip install "conduit[all] @ git+https://github.com/NERC-CEH/conduit"
```

See the [installation guide](https://nerc-ceh.github.io/conduit/guides/install.html) for more info.

## Usage

### From the command line

```sh
conduit graph config.toml --pdf    # graphviz digraph as a pdf
conduit run config.toml --dry-run  # validate contracts and wiring
conduit run config.toml            # execute
```

### From a Python session

```python
import conduit

digraph = conduit.build_graph("config.toml")  # styled graphviz.Digraph
report = conduit.dry_run("config.toml")  # validate contracts and wiring
datasets = conduit.run("config.toml")  # execute and return outputs
```

## Contributing

Contributions welcome but be mindful that this is a very early-stage project, so novel feature ideas might end up further down the priority list than you might hope.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Acknowledgements

This work was funded by NC-International.
