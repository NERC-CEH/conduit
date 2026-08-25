---
title: How it works
icon: lucide/lightbulb
---

# How it works

conduit rests on one structural choice: **the graph lives apart from the functions, and the functions carry their own contracts**.

A node is a plain xarray function.
It names its inputs by parameter name and its output by return type, and it says nothing about where its data comes from, what else consumes it, or how it will be executed.
The wiring lives in a TOML file instead.

Two properties follow, and they are the reason conduit exists.

## The whole graph exists before anything runs

Because the config names every node and every function declares its own signature, conduit can assemble the complete graph without computing a single array.
And because each function's annotations declare what it expects and produces, every edge in that graph carries a claim that can be checked against the claim at the other end.

```mermaid
graph LR
    A["temperature_climate<br/><small>degC</small>"] --> B["temperature_anomaly_climate<br/><small>degC</small>"]
    B --> C["anomaly_range_climate<br/><small>degC</small>"]
```

Checking one function's annotations against its own arguments is what [xarray-annotated](https://github.com/jmarshrossney/xarray-annotated) does on its own.
Checking every edge of a graph before the graph runs needs the annotations *and* the graph together, which is what conduit adds.
Neither library gives you that alone.

The check covers units, dimensions, coordinates, dtype and temporal frequency, and it covers the wiring as well: an input nothing produces is an error, an input nothing consumes is a warning.
See [Declaring contracts](guides/authoring/contracts.md) for the vocabulary and [Validate before running](guides/running/validate-before-running.md) for the pre-flight that uses it.

### What it cannot catch

The check proves the pipeline is *consistent*, not that it is *correct*.

A contract is a claim about the shape and units of data on an edge, so anything that leaves those unchanged passes.
Summing a rate where you meant to average it produces the same units and the same dimensions, and no check will save you — see [Resampling and units](guides/authoring/resampling-and-units.md), which exists for exactly this reason.
The same goes for a sign error, a wrong coefficient, or the right calculation on the wrong variable.

Contracts narrow the space of mistakes. They do not empty it.

## Execution is a separate decision

A node operates on xarray objects, which are backed by NumPy or dask arrays interchangeably.
Nothing in the function knows which, how much of the data is in flight at once, or how many processes are participating.
That makes all of it a config decision:

- Hand a node dask-backed inputs and it streams lazily and out-of-core, unchanged.
- Because conduit holds the whole graph as a value, it can slice the inputs, drive the graph over one partition, and recombine.
- Because a run is a pure function of its config and inputs, running disjoint spatial shards in separate processes is safe. There is no shared mutable state to contend over.

In a hand-written script the *how* — loop bounds, chunk sizes, parallelism — is tangled into the *what*.
Separating them is what makes scale a configuration concern.
The practical knobs are in [Scale up a pipeline](guides/scaling/scale-up.md).

None of those knobs changes the result or the contracts.
Same graph, same checks, same outputs, different execution strategy.
That invariance is what lets you develop against a tiny in-memory run and deploy the identical pipeline across a cluster.

## A run, stage by stage

1. **Parse.** Read the TOML into a validated `ParsedConfig`.
2. **Build.** Import the modules — the `[[node]]` built-in plus anything named by `_import_path` — inspect their signatures, connect input loaders, nodes and output savers into one graph, and run the build-time contract check.
3. **Execute.** Trace back from the requested outputs, run the required nodes in topological order, optionally cached or blocked, and save the results.
4. **Visualise.** At any point, `conduit graph config.toml --pdf` renders the graph without running it.

Only the nodes your requested outputs depend on ever execute.
Ask for one variable and unrelated branches never run.

`conduit run` also stamps the config text and its SHA-256 into every output, so a result file records the pipeline that produced it.

## Design principles

**DAG-first.**
The graph is the primary abstraction, not an implementation detail.
You declare what to compute; the engine works out how.

**Config-driven.**
A pipeline is described in TOML, not assembled imperatively in a script.
You can run and compose one without writing Python, and the config is easy to version, diff and review.

**Module independence.**
A node knows its own inputs and output and nothing about its neighbours.
So you add a computation without touching existing code, and test each module in isolation.
Your modules follow exactly the same conventions as the built-ins.

**Expose, don't wrap.**
conduit is an integration, not a framework that hides its parts.
Where you want the Hamilton driver or the raw xarray objects, they are reachable rather than wrapped.
The aim is that you never *have* to learn Hamilton or pint, not that you are prevented from using them.

**Domain-agnostic core.**
Nothing domain-specific is built in.
Forward models, land-cover classification and analysis pipelines are all expressed the same way.
Gridded geospatial Zarr is the primary target data type, but it lives in an optional layer (`conduit[geo]`), so importing conduit never pulls geospatial dependencies.

## Where next

- [Bring your own module](guides/authoring/bring-your-own-module.md) — the conventions a node function must follow.
- [Declaring contracts](guides/authoring/contracts.md) — units, dims, coords, dtype and frequency.
- [Pipeline 101](recipes/pipeline-101.md) — all of the above, running.
