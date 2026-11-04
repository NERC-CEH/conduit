---
title: Python API
icon: lucide/square-function
---

# Python API

## What most pipelines need

These are the names used in [Drive catena from Python](../guides/run/drive-from-python.md), in the order a run uses them.

| Name | Step |
| --- | --- |
| [`Config`](modules/catena.config.md#catena.config.Config) | A config as a Python dict, or loaded from a file. `.parse()` validates it. |
| [`load_config`](modules/catena.config.md#catena.config.load_config) | Load and parse a TOML file in one call. |
| [`ParsedConfig`](modules/catena.specs.md#catena.specs.ParsedConfig) | What you get back: one spec per config section. |
| [`build_driver`](modules/catena.build.md#catena.build.build_driver) | Build the Hamilton driver, and run the contract check. |
| [`load_inputs`](modules/catena.io.md#catena.io.load_inputs) | Open the input files, keyed by node name. |
| [`get_final_vars`](modules/catena.io.md#catena.io.get_final_vars) | The node names to ask `dr.execute` for. |
| [`get_outputs`](modules/catena.io.md#catena.io.get_outputs) | Merge the executed nodes into per-section datasets. |
| [`save_outputs`](modules/catena.io.md#catena.io.save_outputs) | Write those datasets where the config says. |
| [`run`](modules/catena.pipeline.md#catena.pipeline.run) | All of the above, returning a [`RunReport`](modules/catena.pipeline.md#catena.pipeline.RunReport). |
| [`dry_run`](modules/catena.pipeline.md#catena.pipeline.dry_run) | The same validation with nothing computed or written. |
| [`build_graph`](modules/catena.graph.md#catena.graph.build_graph) | The styled `graphviz.Digraph` that `catena graph` writes. |

Contracts are declared with decorators and markers from [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), which you import from there.
See [its API reference](https://jmarshrossney.github.io/xarray-annotated/api/package.html) for the signatures, and [Declaring contracts](../guides/nodes/contracts.md) for how catena uses them.

## Everything else

Each module's page renders its docstring and the signatures of everything public in it.

### Config and data

| Module | Contents |
| --- | --- |
| [`catena.errors`](modules/catena.errors.md) | The exceptions catena raises on purpose, each keeping the stdlib type a caller would catch. |
| [`catena.config`](modules/catena.config.md) | TOML file to `ParsedConfig`: section dispatch, fan-out expansion, path resolution. |
| [`catena.specs`](modules/catena.specs.md) | One dataclass per config section, each validating itself. |
| [`catena.importing`](modules/catena.importing.md) | Resolving an `_import_path` to a module: dotted names, and `.py` files relative to the config. |
| [`catena.io`](modules/catena.io.md) | Loading inputs and saving outputs, outside the DAG. |
| [`catena.formats`](modules/catena.formats.md) | The file-format registry: which reader, which writer, what a format supports. |

### The DAG

Everything that touches a Hamilton `Driver` or graph object.

| Module | Contents |
| --- | --- |
| [`catena.build`](modules/catena.build.md) | Building Hamilton drivers from configured module lists. |
| [`catena.nodegen`](modules/catena.nodegen.md) | Generating Hamilton modules from `[[node]]` entries. |
| [`catena.transforms`](modules/catena.transforms.md) | Functions that `[[node]]` and preset config can apply to a node's inputs. |
| [`catena.caching`](modules/catena.caching.md) | Content-based cache keys for `xarray` objects. |
| [`catena.blocking`](modules/catena.blocking.md) | Executing the driver one block of a dimension at a time. |

### Validation

| Module | Contents |
| --- | --- |
| [`catena.contract_check`](modules/catena.contract_check.md) | The whole-DAG, before-compute contract check. |
| [`catena.wiring_check`](modules/catena.wiring_check.md) | Checking the required inputs against the ones the config loads. |
| [`catena.input_checks`](modules/catena.input_checks.md) | Input-compatibility predicates, the `CHECKS` registry, and the runner. |

### Running and visualising

| Module | Contents |
| --- | --- |
| [`catena.pipeline`](modules/catena.pipeline.md) | `run` and `dry_run`, and the reports they return. |
| [`catena.graph`](modules/catena.graph.md) | `build_graph`, and the frequency clustering and colouring it applies. |
| [`catena.graph_style`](modules/catena.graph_style.md) | The `GraphvizSpec` defaults, and the TOML override `catena graph --style` reads. |

### Gridded

Installed with the `geo` extra, and imported only when needed.

| Module | Contents |
| --- | --- |
| [`catena.gridded.io`](modules/catena.gridded/io.md) | CRS-aware stacking, parallel Zarr stores, subset merges. |
| [`catena.gridded.spatial`](modules/catena.gridded/spatial.md) | Stacking a `(y, x)` grid into a 1-D `pixel` dimension. |
| [`catena.gridded.cli`](modules/catena.gridded/cli.md) | The `catena gridded` subcommands. |
