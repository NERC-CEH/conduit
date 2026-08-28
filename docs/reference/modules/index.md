---
title: Module reference
icon: lucide/library
---

# Module reference

Every module's docstring, rendered in full, along with the signatures of everything public in it.

Most pipelines need none of this: the names you import to write and run a pipeline are indexed on the [Python API](../python-api.md) page, which links into these modules for the details.
Read here when you are building on conduit rather than with it — writing a check, driving Hamilton yourself, adding a file format, or working out what a spec actually holds.

## Core

| Module | Contents |
| --- | --- |
| [`conduit.pipeline`](conduit.pipeline.md) | `run` and `dry_run`, and the reports they return. |
| [`conduit.config`](conduit.config.md) | TOML file to `ParsedConfig`: section dispatch, fan-out expansion, path resolution. |
| [`conduit.specs`](conduit.specs.md) | One dataclass per config section, each validating itself. |
| [`conduit.io`](conduit.io.md) | Loading inputs and saving outputs, outside the DAG. |
| [`conduit.formats`](conduit.formats.md) | The file-format registry: which reader, which writer, what a format supports. |
| [`conduit.checks`](conduit.checks.md) | Input-compatibility predicates, the `CHECKS` registry, and the runner. |
| [`conduit.transforms`](conduit.transforms.md) | Functions that `[[node]]` and preset config can apply to a node's inputs. |

## Graph

| Module | Contents |
| --- | --- |
| [`conduit.graph`](conduit.graph.md) | `build_graph`, and the frequency clustering and colouring it applies. |
| [`conduit.graph_style`](conduit.graph_style.md) | The `GraphvizSpec` defaults, and the TOML override `conduit graph --style` reads. |

## DAG

| Module | Contents |
| --- | --- |
| [`conduit.dag.driver`](conduit.dag.driver.md) | Building Hamilton drivers from configured module lists. |
| [`conduit.dag.node`](conduit.dag/node.md) | Generating Hamilton modules from `[[node]]` entries. |
| [`conduit.dag.contract_check`](conduit.dag/contract_check.md) | The whole-DAG, before-compute contract check. |
| [`conduit.dag.wiring_check`](conduit.dag/wiring_check.md) | Checking the required inputs against the ones the config loads. |
| [`conduit.dag.caching`](conduit.dag/caching.md) | Content-based cache keys for `xarray` objects. |
| [`conduit.dag.blocking`](conduit.dag/blocking.md) | Executing the driver one block of a dimension at a time. |

## Gridded

Optional, installed with the `geo` extra and imported lazily.
Nothing in the core assumes a CRS or a pixel axis; it all lives here.

| Module | Contents |
| --- | --- |
| [`conduit.gridded.io`](conduit.gridded/io.md) | CRS-aware stacking, parallel Zarr stores, subset merges. |
| [`conduit.gridded.spatial`](conduit.gridded/spatial.md) | Stacking a `(y, x)` grid into a 1-D `pixel` dimension. |
| [`conduit.gridded.cli`](conduit.gridded/cli.md) | The `conduit gridded` subcommands. |
