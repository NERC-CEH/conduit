---
title: Write a config
icon: lucide/file-cog
---

# Write a config

A config is the pipeline.
It names the files to read, the computations to run, and the results to write.
It needs no Python unless you are adding a computation nobody has written yet.

This page covers the shape of a config; the [configuration reference](../../reference/configuration.md) has every key.

## The anatomy

Here is a complete config — the one from [Pipeline 101](../../recipes/pipeline-101.md):

```toml
--8<-- "recipes/pipeline_101/config.toml"
```

Three kinds of section do the work:

`[inputs.<label>]`
:   Where data comes from. One section per file, `path` plus the `vars` you want. The format follows the [file extension](../../reference/data-formats.md).

`[[node]]`, `[[resample]]`, and your own module sections
:   What gets computed. An inline `[[node]]` holds a Python expression; a section with an `_import_path` pulls in a module of node functions.

`[outputs.<label>]`
:   What gets written. One section per output file, `path` plus the nodes to put in it.

The optional sections `[annotations]`, `[validation]`, `[cache]`, `[blocking]` and `[subset]` change how the pipeline is checked or executed, never what it computes.

Any other section is treated as one of your modules and must carry an `_import_path`, so a typo like `[anotations]` fails at parse time instead of being silently ignored.

## Names are what wire it together

A config is connected when node names line up ([why](../../concepts/pipeline-model.md#names-are-the-wiring)).
Three rules cover almost everything:

1. An `[inputs.<label>]` section with `vars = ["temperature"]` produces a node called `temperature_<label>`.
   The suffix is the section label, so `[inputs.daily]` gives `temperature_daily`.
2. A node's `inputs` are node names, written exactly, suffix included.
3. An `[outputs.<label>]` section's `vars` are node names too.

So the chain in the config above reads: `[inputs.climate]` produces `temperature_climate`; the imported function `temperature_anomaly_climate` consumes it by parameter name; the inline `[[node]]` consumes *that*; and `[outputs.climate]` asks for both computed nodes.

Two escape hatches:

- `suffix = ""` on an input section gives bare node names, useful for a static file that feeds everything.
- The mapping form of `vars`, `vars = {temperature_daily = "t2m"}`, gives a file variable a different node name.

To see what actually connected to what, draw it with [`conduit graph config.toml --pdf`](../validate/visualise-the-graph.md).

## The edits you will actually make

Most work on a config is adapting one that already runs.

**Point it at different data.**
Change `path` in the `[inputs.*]` sections and in the `[outputs.*]` sections.
If the new files name their variables differently, use the mapping form of `vars` rather than renaming anything downstream.

**Add a variable from a file you already read.**
Add it to that section's `vars` list.
It becomes a node; until something consumes it, conduit only warns that it is unused.

**Add a derived quantity.**
If it fits in one expression, add an [inline `[[node]]`](inline-nodes-and-fan-out.md).
Otherwise [write a module](../nodes/bring-your-own-module.md) and add a section pointing at it.

**Ask for different results.**
Edit `vars` in the `[outputs.*]` section.
Only the nodes your outputs depend on are executed, so removing a variable makes the run smaller.
Any node can be requested, including an intermediate you want to inspect.

**Change a parameter.**
A module's keyword-only arguments are set in that module's section.
They [share one namespace](../nodes/bring-your-own-module.md#parameter-names-share-one-namespace) across every section, so `floor` set under `[aridity]` is the same `floor` everywhere.

**Turn the checks up.**
Add `[annotations]` with `mode = "strict"` to make a contract mismatch fail rather than warn, and `on_inexact = "warn"` to see every unit conversion the run performs.

## Before you run it

```sh
conduit run config.toml --dry-run
```

This checks everything short of computing: it catches a suffix that does not match, a renamed file variable, or an output nothing produces.
See [Validate before running](../validate/validate-before-running.md).
