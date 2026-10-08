---
title: The pipeline model
icon: lucide/workflow
---

# The pipeline model

A pipeline is a directed acyclic graph of named nodes.
Nothing in it is written down twice: the config names the nodes, the functions declare their own signatures, and the edges follow from the names agreeing.

## Names are the wiring

conduit builds the DAG with [Hamilton](https://github.com/dagworks-inc/hamilton), which derives the graph from names rather than from an explicit edge list.
A function called `soil_moisture_daily` produces a node called `soil_moisture_daily`, and its parameter `temperature_daily` binds to whatever produces `temperature_daily`.
There is no registration step, no wiring code, and no import of the upstream function.

So adding a computation touches no existing code.
Write a function whose parameters name existing nodes, add its module to the config, and it is in the graph.
[Bring your own module](../guides/nodes/bring-your-own-module.md) has the conventions this implies for your functions.

## One namespace

The graph holds input loaders, computed nodes and output savers, all in one flat namespace.

- An `[inputs.*]` section contributes one node per variable, named `{var}{suffix}`, where the suffix comes from the section label.
- A module section, `[[node]]` or `[[resample]]` contributes computed nodes.
- An `[outputs.*]` section names the nodes it wants written.

An output can therefore request any node, not only a designated final one, and a node consumes an input file and a computed value in the same way.
Keyword-only parameters share a single flat namespace too, so [their names must be unique across the config](../guides/nodes/bring-your-own-module.md#parameter-names-share-one-namespace).

## Section labels are inert

`daily`, `weekly` and `static` are node-name suffixes and nothing else.
conduit infers no frequency, ordering or meaning from them: a pipeline whose sections are called `raw` and `smoothed` behaves exactly like one using `daily` and `weekly`.

Where frequency matters, it comes from a declared `Freq` contract.
That is what the contract check compares and what `conduit graph` clusters on.
So a `[[resample]]` takes both a label pair and a `freq`: the labels say which nodes to read and write, and `freq` says what the time axis becomes.
A mislabelled section gives confusing node names; a mis-declared `Freq` fails the check.

## The graph is a value

The graph is assembled from the config and the signatures alone, so it exists as an object before any array is touched.
It can be:

- rendered, with `conduit graph config.toml --pdf`;
- checked, by [the whole-graph contract check](contracts.md);
- driven repeatedly over slices of its inputs, by [blocking and sharding](execution.md);
- traversed backwards from the requested outputs, so only the nodes they depend on ever execute.
