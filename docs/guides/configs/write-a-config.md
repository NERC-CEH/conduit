---
title: Write a config
icon: lucide/file-cog
---

# Write a config

A config is the pipeline.
It names the files to read, the computations to run, and the results to write, and it needs no Python at all unless you are adding a computation nobody has written yet.

This guide is about reading, writing and adapting one.
[Configuration reference](../../reference/configuration.md) has every key; this page has the shape.

## The anatomy

Here is a complete config — the one from [Pipeline 101](../../recipes/pipeline-101.md):

```toml
--8<-- "recipes/pipeline_101/config.toml"
```

Three kinds of section do the work, and every config is some arrangement of them:

`[inputs.<label>]`
:   Where data comes from. One section per file, `path` plus the `vars` you want.

`[[node]]`, `[[resample]]`, and your own module sections
:   What gets computed. An inline `[[node]]` holds a Python expression; a section with an `_import_path` pulls in a module of node functions.

`[outputs.<label>]`
:   What gets written. One section per output file, `path` plus the nodes to put in it.

Everything else is policy rather than structure: `[annotations]`, `[validation]`, `[cache]`, `[blocking]` and `[subset]` change how the pipeline is checked or executed, never what it computes.
None of them is required.

!!! warning "There are no optional sections you can misspell"

    conduit recognises a fixed set of section names, and treats **anything else** as one of your own modules.
    An unrecognised section must therefore carry `_import_path`, and a typo like `[anotations]` fails at parse time rather than being silently ignored.

## Names are what wire it together

There is one namespace of node names, and a config is connected when the names line up.
Three rules cover almost everything:

1. An `[inputs.<label>]` section with `vars = ["temperature"]` produces a node called `temperature_<label>`.
   The suffix is the section label, so `[inputs.daily]` gives `temperature_daily`.
2. A node's `inputs` are node names, written exactly, suffix included.
3. An `[outputs.<label>]` section's `vars` are node names too.

So the chain in the config above reads: `[inputs.climate]` produces `temperature_climate`; the imported function `temperature_anomaly_climate` consumes it by parameter name; the inline `[[node]]` consumes *that*; and `[outputs.climate]` asks for both computed nodes.

Two escape hatches are worth knowing.
Set `suffix = ""` on an input section for bare node names, which is what you want for a static file that feeds everything.
Use the mapping form of `vars` to alias a file variable to a different node name, `vars = {temperature_daily = "t2m"}`, which decouples the file's naming from the graph's.

If you are unsure whether the names line up, do not read the file harder.
Draw it: [`conduit graph config.toml --pdf`](../validate/visualise-the-graph.md) shows you exactly what connected to what.

## The edits you will actually make

Most work on a config is adapting one that already runs.

**Point it at different data.**
Change `path` in the `[inputs.*]` sections and in the `[outputs.*]` sections.
If the new files name their variables differently, use the mapping form of `vars` rather than renaming anything downstream.

**Add a variable from a file you already read.**
Add it to that section's `vars` list.
It becomes a node, and nothing else changes until something consumes it.
Loading a variable no node consumes is a warning, not an error, so this is safe to do speculatively.

**Add a derived quantity.**
If it fits in one expression, add a `[[node]]`.
If it needs several related functions, shared parameters, or unit annotations, write a module instead and add a section pointing at it.
[Inline nodes and fan-out](inline-nodes-and-fan-out.md) covers the first case, [Bring your own module](../nodes/bring-your-own-module.md) the second.

**Ask for different results.**
Edit `vars` in the `[outputs.*]` section.
Only the nodes your outputs depend on ever execute, so removing a variable makes the run smaller, and any node in the graph can be requested — including an intermediate you want to inspect.

**Change a parameter.**
A module's keyword-only arguments are set in that module's section body.
Remember that these share one flat namespace across every section, so `floor` set under `[aridity]` is the same `floor` everywhere.

**Turn the checks up.**
Add `[annotations]` with `mode = "strict"` to make a contract mismatch fail rather than warn, and `on_inexact = "warn"` to see every unit conversion the run performs.

## Before you run it

```sh
conduit run config.toml --dry-run
```

This parses the config, opens the inputs, builds the graph, checks the contracts and confirms the outputs are writable, without computing anything.
It is fast, and it catches the mistakes a config edit actually produces: a suffix that does not match, a renamed file variable, an output nobody produces.
See [Validate before running](../validate/validate-before-running.md).

## Where next

- [Inline nodes and fan-out](inline-nodes-and-fan-out.md) — `[[node]]`, `for_each` and `[[resample]]`.
- [Configuration reference](../../reference/configuration.md) — every section and key.
- [Data formats](../../reference/data-formats.md) — what `path` extensions are supported.
- [The pipeline model](../../concepts/pipeline-model.md) — why the names are the wiring.
