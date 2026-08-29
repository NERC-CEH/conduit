---
title: The pipeline model
icon: lucide/workflow
---

# The pipeline model

A pipeline is a directed acyclic graph of named nodes.
Nothing in it is written down twice: the config names the nodes, the functions declare their own signatures, and the edges fall out of the two agreeing on names.

## Names are the wiring

conduit builds the DAG with [Hamilton](https://github.com/dagworks-inc/hamilton), which derives the graph from names rather than from an explicit edge list.
A function called `soil_moisture_daily` produces a node called `soil_moisture_daily`, and its parameter `temperature_daily` binds to whatever produces `temperature_daily`.
No registration step, no wiring code, no import of the upstream function.

The consequence worth caring about is that adding a computation touches no existing code.
Write a function whose parameters name nodes that already exist, add it to the config, and it is in the graph.
Nothing that was already there needs to know.

[Bring your own module](../guides/nodes/bring-your-own-module.md) has the conventions this implies for your functions.

## Three kinds of node, one namespace

The graph holds input loaders, computed nodes and output savers, and they all live in the same flat namespace.

An `[inputs.*]` section contributes one node per variable, named `{var}{suffix}` where the suffix is the section label.
A `[[node]]` or `[[resample]]` entry contributes computed nodes.
An `[outputs.*]` section names nodes it wants written.
Because there is one namespace, an output can request any node in the graph, not only a designated final one, and a node can consume an input file and a computed value without distinguishing them.

Keyword-only parameters share that namespace too.
Every `*`-suffixed argument across every config section resolves against one flat pool of configuration values, so two sections declaring the same parameter name is a parse-time error naming both.
Choose parameter names accordingly.

## Section labels are inert

`daily`, `weekly` and `static` are node-name suffixes and nothing else.
conduit infers no frequency, no ordering and no semantics from them, and a pipeline whose sections are called `raw` and `smoothed` behaves identically to one using `daily` and `weekly`.

Where frequency genuinely matters, it comes from a declared `Freq` contract.
That is what `conduit graph` clusters on, and what the contract check compares.
A `[[resample]]` therefore takes both a label pair and a `freq`: the labels say which nodes to read from and write to, and `freq` says what the time axis actually becomes.

The point of the separation is that a name can be wrong without being dangerous.
Mislabel a section and you get confusing node names; mis-declare a `Freq` and the check fails.

## The graph is a value

Because the graph is assembled from the config and the signatures alone, it exists as an object before any array is touched.
That is what makes several otherwise-awkward things ordinary.

The graph can be rendered, so `conduit graph config.toml --pdf` draws the pipeline without running it.
It can be checked, which is what [the whole-graph contract check](contracts.md) does.
It can be driven repeatedly over slices of its own inputs, which is what [blocking and sharding](execution.md) do.
And it can be traversed backwards from the outputs you asked for, so only the nodes those outputs depend on ever execute.
Ask for one variable and unrelated branches never run.

## Where next

- [Contracts and the whole-graph check](contracts.md) — what the edges carry.
- [Execution and scaling](execution.md) — what happens once the graph is built.
- [Write a config](../guides/configs/write-a-config.md) — the sections named above, in practice.
- [Configuration reference](../reference/configuration.md) — every key.
