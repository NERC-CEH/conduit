# Conduit

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton) and [xarray](https://xarray.dev), serves as a highly flexible and robust substrate for environmental data science applications.

The process for building on top of Conduit is simple:

1. You write ordinary Python functions that receive and return `xarray.DataArray`s, and optionally add [annotations](https://docs.python.org/3/library/typing.html#typing.Annotated) that declare the expected properties of these arrays (coordinates, physical units etc).
2. Users can then use these functions to define data pipelines, by simply writing/editing TOML configuration files.
3. Conduit builds the graph (via Hamilton), checks the annotation contracts _before_ execution (via [`xarray-annotated`](https://github.com/jmarshrossney/xarray-annotated) and [pint](https://pint.readthedocs.io/en/stable/)), and finally runs the pipeline with one of several swappable backend execution models (serial, multiprocessing, dask, jax.vmap...).

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
conduit run config.toml --dry-run  # validate contracts and wiring, no compute
conduit run config.toml            # execute
```

### From a Python session

```python
import conduit

digraph = conduit.build_graph("config.toml")  # styled graphviz.Digraph, renders in a notebook
report = conduit.dry_run("config.toml")       # validate contracts and wiring, no compute
datasets = conduit.run("config.toml")         # execute and return outputs
```

## Contributing

Contributions welcome but be mindful that this is a very early-stage project, so novel feature ideas might end up further down the priority list than you might hope.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Acknowledgements

This work was funded by NC-International.
