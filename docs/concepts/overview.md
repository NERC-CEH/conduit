---
title: Overview
icon: lucide/lightbulb
---

# Overview

conduit is built around one choice: keep the graph separate from the functions, and let the functions carry their own contracts.

A node is a plain xarray function.
It names its inputs by parameter name and its output by function name, and knows nothing about where its data comes from, what consumes it, or how it will be executed.
The wiring lives in a TOML file.

```mermaid
graph LR
    A["temperature_climate<br/><small>degC</small>"] --> B["temperature_anomaly_climate<br/><small>degC</small>"]
    B --> C["anomaly_range_climate<br/><small>degC</small>"]
```

Everything else follows from that split.
The functions can be written and tested without a pipeline, the pipeline can be assembled and checked without running it, and how it runs is a separate decision again.
Hence the four stages of working with conduit.

## 1. Write the science code

Ordinary Python functions of `xarray.DataArray`s in an importable module, annotated with what they require and produce.
See [The pipeline model](pipeline-model.md) for how names become edges, then [Bring your own module](../guides/nodes/bring-your-own-module.md) and [Declaring contracts](../guides/nodes/contracts.md).

## 2. Write the config

A TOML file names the input files, the nodes, and the outputs you want.
This is where most time goes, and it needs no Python: adapting someone else's pipeline means changing paths, adding a variable, or asking for a different output.
Start at [Write a config](../guides/configs/write-a-config.md).

## 3. Validate

Because the config names every node and every function declares its signature, conduit can assemble the whole graph and check every edge without computing an array.
[Contracts and the whole-graph check](contracts.md) explains what that catches and what it misses; [Validate before running](../guides/validate/validate-before-running.md) is the practical guide.

## 4. Run

Execution strategy — in memory, out-of-core, blocked or sharded — is a config decision, so the same pipeline runs on a laptop and across a cluster.
[Execution and scaling](execution.md) helps you choose; [Scale up a pipeline](../guides/run/scale-up.md) has the settings.

[Pipeline 101](../recipes/pipeline-101.md) is all four stages in miniature.
