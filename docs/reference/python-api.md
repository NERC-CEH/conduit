---
title: Python API
icon: lucide/square-function
---

# Python API

The CLI is an optional wrapper over the library, so everything `conduit run` does is available from Python with nothing extra installed.

## What most pipelines need

`conduit.run` takes a path to a TOML config, or a `ParsedConfig` you have adjusted in Python, and does the lot:

```python
import conduit

report = conduit.run("config.toml")
```

Taking the steps yourself lets you inspect individual nodes, override values between runs, or skip writing to disk.
[Drive conduit from Python](../guides/run/drive-from-python.md) walks through them in order; these are the names it uses.

| Name | Step |
| --- | --- |
| [`Config`](modules/conduit.config.md#conduit.config.Config) | A config as a Python dict, or loaded from a file. `.parse()` validates it. |
| [`load_config`](modules/conduit.config.md#conduit.config.load_config) | Load and parse a TOML file in one call. |
| [`ParsedConfig`](modules/conduit.specs.md#conduit.specs.ParsedConfig) | What you get back: one spec per config section. |
| [`build_driver`](modules/conduit.build.md#conduit.build.build_driver) | Build the Hamilton driver, and run the contract check. |
| [`load_inputs`](modules/conduit.io.md#conduit.io.load_inputs) | Open the input files, keyed by node name. |
| [`get_final_vars`](modules/conduit.io.md#conduit.io.get_final_vars) | The node names to ask `dr.execute` for. |
| [`get_outputs`](modules/conduit.io.md#conduit.io.get_outputs) | Merge the executed nodes into per-section datasets. |
| [`save_outputs`](modules/conduit.io.md#conduit.io.save_outputs) | Write those datasets where the config says. |
| [`run`](modules/conduit.pipeline.md#conduit.pipeline.run) | All of the above, returning a [`RunReport`](modules/conduit.pipeline.md#conduit.pipeline.RunReport). |
| [`dry_run`](modules/conduit.pipeline.md#conduit.pipeline.dry_run) | The same validation with nothing computed or written. |
| [`build_graph`](modules/conduit.graph.md#conduit.graph.build_graph) | The styled `graphviz.Digraph` that `conduit graph` writes. |

Contracts are declared with decorators and markers from [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), which you import from there.
See [its API reference](https://jmarshrossney.github.io/xarray-annotated/api/package.html) for the signatures, and [Declaring contracts](../guides/nodes/contracts.md) for how conduit uses them.

## Everything else

Each module's docstring, rendered in full, along with the signatures of everything public in it.
Read here when you are building on conduit rather than with it — writing a check, driving Hamilton yourself, adding a file format, or working out what a spec holds.

### Config and data

| Module | Contents |
| --- | --- |
| [`conduit.errors`](modules/conduit.errors.md) | The exceptions conduit raises on purpose, each keeping the stdlib type a caller would catch. |
| [`conduit.config`](modules/conduit.config.md) | TOML file to `ParsedConfig`: section dispatch, fan-out expansion, path resolution. |
| [`conduit.specs`](modules/conduit.specs.md) | One dataclass per config section, each validating itself. |
| [`conduit.importing`](modules/conduit.importing.md) | Resolving an `_import_path` to a module: dotted names, and `.py` files relative to the config. |
| [`conduit.io`](modules/conduit.io.md) | Loading inputs and saving outputs, outside the DAG. |
| [`conduit.formats`](modules/conduit.formats.md) | The file-format registry: which reader, which writer, what a format supports. |

### The DAG

Everything that touches a Hamilton `Driver` or graph object.

| Module | Contents |
| --- | --- |
| [`conduit.build`](modules/conduit.build.md) | Building Hamilton drivers from configured module lists. |
| [`conduit.nodegen`](modules/conduit.nodegen.md) | Generating Hamilton modules from `[[node]]` entries. |
| [`conduit.transforms`](modules/conduit.transforms.md) | Functions that `[[node]]` and preset config can apply to a node's inputs. |
| [`conduit.caching`](modules/conduit.caching.md) | Content-based cache keys for `xarray` objects. |
| [`conduit.blocking`](modules/conduit.blocking.md) | Executing the driver one block of a dimension at a time. |

### Validation

| Module | Contents |
| --- | --- |
| [`conduit.contract_check`](modules/conduit.contract_check.md) | The whole-DAG, before-compute contract check. |
| [`conduit.wiring_check`](modules/conduit.wiring_check.md) | Checking the required inputs against the ones the config loads. |
| [`conduit.input_checks`](modules/conduit.input_checks.md) | Input-compatibility predicates, the `CHECKS` registry, and the runner. |

### Running and visualising

| Module | Contents |
| --- | --- |
| [`conduit.pipeline`](modules/conduit.pipeline.md) | `run` and `dry_run`, and the reports they return. |
| [`conduit.graph`](modules/conduit.graph.md) | `build_graph`, and the frequency clustering and colouring it applies. |
| [`conduit.graph_style`](modules/conduit.graph_style.md) | The `GraphvizSpec` defaults, and the TOML override `conduit graph --style` reads. |

### Gridded

Optional, installed with the `geo` extra and imported lazily.
Nothing in the core assumes a CRS or a pixel axis; it all lives here.

| Module | Contents |
| --- | --- |
| [`conduit.gridded.io`](modules/conduit.gridded/io.md) | CRS-aware stacking, parallel Zarr stores, subset merges. |
| [`conduit.gridded.spatial`](modules/conduit.gridded/spatial.md) | Stacking a `(y, x)` grid into a 1-D `pixel` dimension. |
| [`conduit.gridded.cli`](modules/conduit.gridded/cli.md) | The `conduit gridded` subcommands. |
