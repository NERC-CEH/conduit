---
title: Python API
icon: lucide/code-2
---

# Python API

The CLI is an optional wrapper over the library, so everything `conduit run` does is available from Python with nothing extra installed.

This page indexes the public API: the names you can import straight from `conduit`, grouped by what you would use them for.
Each links to its entry in the [module reference](modules/index.md), where the signature and docstring live.
For a walkthrough rather than an index, see [Drive conduit from Python](../guides/run/drive-from-python.md).

## Running a pipeline

```python
import conduit

report = conduit.run("config.toml")
```

`run` and `dry_run` take either a path to a TOML file or a `ParsedConfig`.
Passing a path stamps the config text and its SHA-256 into the outputs.
Passing a `ParsedConfig` stamps nothing.

| Name | What it does |
| --- | --- |
| [`run`](modules/conduit.pipeline.md#conduit.pipeline.run) | Execute everything a config describes and write the outputs. |
| [`dry_run`](modules/conduit.pipeline.md#conduit.pipeline.dry_run) | Do the same setup and validation, compute nothing, write nothing. |
| [`RunReport`](modules/conduit.pipeline.md#conduit.pipeline.RunReport) | What `run` returns: the datasets, the files written, the timings. |
| [`WrittenOutput`](modules/conduit.pipeline.md#conduit.pipeline.WrittenOutput) | One output file in a `RunReport`. |
| [`DryRunReport`](modules/conduit.pipeline.md#conduit.pipeline.DryRunReport) | What `dry_run` returns: the outcome of each validation stage. |
| [`Stage`](modules/conduit.pipeline.md#conduit.pipeline.Stage) | One stage in a `DryRunReport`. |

## Building the pieces yourself

Use these to inspect the graph, execute a subset of nodes, override values between runs, or keep results in memory instead of writing them.

| Name | What it does |
| --- | --- |
| [`load_config`](modules/conduit.config.md#conduit.config.load_config) | Parse a TOML file into a `ParsedConfig`. |
| [`build_driver`](modules/conduit.dag.driver.md#conduit.dag.driver.build_driver) | Build the Hamilton driver from a parsed config. |
| [`build_graph`](modules/conduit.graph.md#conduit.graph.build_graph) | Render the DAG as a styled `graphviz.Digraph`. |
| [`load_inputs`](modules/conduit.io.md#conduit.io.load_inputs) | Open the input files a config names, as Hamilton inputs. |
| [`get_final_vars`](modules/conduit.io.md#conduit.io.get_final_vars) | The node names a config asks for as outputs. |
| [`get_outputs`](modules/conduit.io.md#conduit.io.get_outputs) | Execute the driver and return the output datasets. |
| [`save_outputs`](modules/conduit.io.md#conduit.io.save_outputs) | Write those datasets to the paths the config names. |

## Declaring contracts

The contract decorators and markers come from [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated), and you import them from there.

- `declare_units`, `declare_freq`, `declare_schema` — the decorators, documented in [its API reference](https://jmarshrossney.github.io/xarray-annotated/api/package.html).
- `Freq`, `Dims`, `Coords`, `Dtype` — the annotation markers.
- `UnitsWarning`, `SchemaWarning` — what a non-fatal mismatch raises.

`declare_units` must be the outermost decorator — see [Declaring contracts](../guides/nodes/contracts.md) for how conduit uses all of this.

## Config objects

The parsed form of each TOML section.
You rarely construct these by hand, but they are what `load_config` returns and what `run` accepts in place of a path.
All are documented in [`conduit.specs`](modules/conduit.specs.md).

| Name | Section it parses |
| --- | --- |
| [`ParsedConfig`](modules/conduit.specs.md#conduit.specs.ParsedConfig) | The whole file. |
| [`IOSpec`](modules/conduit.specs.md#conduit.specs.IOSpec) | One `[inputs.*]` or `[outputs.*]` section. |
| [`NodeSpec`](modules/conduit.specs.md#conduit.specs.NodeSpec) | `[[node]]`. |
| [`ResampleSpec`](modules/conduit.specs.md#conduit.specs.ResampleSpec) | `[[resample]]`. |
| [`CacheSpec`](modules/conduit.specs.md#conduit.specs.CacheSpec) | `[cache]`. |
| [`BlockingSpec`](modules/conduit.specs.md#conduit.specs.BlockingSpec) | `[blocking]`. |
| [`SubsetSpec`](modules/conduit.specs.md#conduit.specs.SubsetSpec) | `[subset]`. |
| [`CheckSpec`](modules/conduit.specs.md#conduit.specs.CheckSpec) | One entry in `[validation].checks`. |
| [`AnnotationPolicySpec`](modules/conduit.specs.md#conduit.specs.AnnotationPolicySpec) | `[annotations]`. |
