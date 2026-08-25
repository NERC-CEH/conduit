---
title: Python API
icon: lucide/code-2
---

# Python API

The CLI is an optional wrapper over the library, so everything `conduit run` does is available from Python with nothing extra installed.
This page lists the public API: what you need in order to write science code on top of conduit, and nothing else.

The internals — the checkers, the specs, the Hamilton module generator — are under [Modules](modules/conduit.pipeline.md), where each module's docstring is the design document for that part of the system.
For a walkthrough rather than signatures, see [Drive conduit from Python](../guides/running/drive-from-python.md).

## Running a pipeline

`run` and `dry_run` take either a path to a TOML file or a `ParsedConfig`.
Passing a path stamps the config text and its SHA-256 into the outputs. Passing a `ParsedConfig` stamps nothing.

::: conduit.pipeline
    options:
      members:
        - run
        - dry_run
        - DryRunReport
        - Stage

## Building the pieces yourself

Use these when you want to inspect the graph, execute a subset of nodes, override values between runs, or keep the results in memory instead of writing them.

::: conduit
    options:
      members:
        - load_config
        - build_driver
        - build_graph
        - load_inputs
        - get_final_vars
        - get_outputs
        - save_outputs

## Declaring contracts

These are re-exported from [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) so that a node module needs one import.
`declare_units` must be the outermost decorator — see [Declaring contracts](../guides/authoring/contracts.md).

::: conduit
    options:
      members:
        - declare_units
        - declare_freq
        - declare_schema
        - Freq
        - Dims
        - Coords
        - Dtype
        - UnitsWarning
        - SchemaWarning

## Config objects

The parsed forms of each TOML section.
You rarely construct these by hand, but they are what `load_config` returns and what `run` accepts in place of a path.

::: conduit
    options:
      members:
        - ParsedConfig
        - IOSpec
        - NodeSpec
        - ResampleSpec
        - CacheSpec
        - BlockingSpec
        - SubsetSpec
        - CheckSpec
        - AnnotationPolicySpec
