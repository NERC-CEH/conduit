# `conduit`

An opinionated integration of [Apache Hamilton](https://github.com/DAGWorks-Inc/hamilton), [xarray](https://xarray.dev) and [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), driven by a plain [TOML](https://toml.io) file.
You write ordinary annotated xarray functions and describe how they wire together in config.
conduit builds the graph, proves it consistent before running it, and executes it at whatever scale the config asks for.

The premise is that the graph lives apart from the functions, and the functions carry their own contracts in their type annotations.
What follows from that:

- **Validate the whole graph before any compute runs.** Units, dimensions, coordinates, dtypes, frequency and the wiring itself, all checked from the annotations.
- **The config is the pipeline.** One file describes the inputs, the nodes, the fan-out and the outputs, and it is stamped into every result.
- **Scale by changing config, not code.** The same functions run in memory, cached, blocked, or across parallel processes writing to one Zarr store.
- **The wiring is declared, not implied.** Reading the config tells you what depends on what.

> [!WARNING]
> **Alpha.** conduit has no users outside the core team.
> The config schema, the Python API and the CLI all change without deprecation warnings.

## Install

```bash
pip install "conduit[all] @ git+https://github.com/NERC-CEH/conduit"
```

The base install is the library. `cli` adds the `conduit` command, `viz` adds DAG rendering, `geo` adds CRS-aware gridded I/O.
See the [installation guide](https://NERC-CEH.github.io/conduit/guides/install.html) for the extras individually.

## Use

```python
import conduit

datasets = conduit.run("config.toml")         # execute, write each [outputs.*], return them
report = conduit.dry_run("config.toml")       # validate contracts and wiring, no compute
digraph = conduit.build_graph("config.toml")  # styled graphviz.Digraph, renders in a notebook
```

Each takes a path to a TOML config or a `ParsedConfig` you have already adjusted in Python.
The `conduit` command is a thin wrapper over these three.

## Documentation

<https://NERC-CEH.github.io/conduit>

- [How it works](https://NERC-CEH.github.io/conduit/how-it-works.html) — the design, and what the contract check can and cannot catch.
- [Pipeline 101](https://NERC-CEH.github.io/conduit/recipes/pipeline-101.html) — the whole workflow in miniature.
- [Bring your own module](https://NERC-CEH.github.io/conduit/guides/authoring/bring-your-own-module.html) — start here if you are adding your own science code.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the development setup, the `just` tasks, and how to add a recipe.

## Licence

MIT. See [`LICENSE`](LICENSE).
