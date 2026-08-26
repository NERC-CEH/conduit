---
title: Visualise the graph
icon: lucide/git-fork
---

# Visualise the graph

`conduit graph` renders the DAG without running it, which is the quickest way to check
that a config wired up the way you meant.

```sh
conduit graph config.toml --pdf
```

This writes `pipeline.pdf` showing every node and its dependencies. Each node displays
its declared **unit** (read from the `Annotated[DataArray, "<unit>"]` type) in place of
the generic `DataArray` type, and requested output nodes are highlighted.

Nodes are coloured and clustered by their declared **frequency**, meaning the `freq`
contract on a `[[node]]` or `[[resample]]` (`"7D"`, `"1ME"`). This comes from the DAG, so
a pipeline whose resample targets are called `raw` and `smoothed` groups just as well as
one using `daily` and `weekly`. Nodes with no declared frequency inherit one when all
their neighbours agree, and are otherwise left ungrouped.

Pass `--png` for PNG instead, and `-o/--output` to change the base filename (default
`pipeline`). The `.dot` source is always written.

!!! note "Requires Graphviz"

    `conduit graph` needs the `viz` extra **and** the Graphviz system binary — see
    [Installation](../install.md).

## What to look for

The graph is where structural mistakes are obvious that a config file hides:

- A node floating with no downstream consumer, which means nothing you asked for uses it.
- Two chains that should have met and did not, usually a name that differs by a suffix.
- A cluster in the wrong place, which means a `freq` contract says something you did not
  intend.

`conduit graph` builds the driver, so it also runs the build-time contract check on the
way past. A config that draws is a config whose declared edges agree.

## Customising the styling

Pass a styling file with `-s`/`--style` to override colours, layout, the legend, or a
custom style function. Keeping style in its own file means one look can be reused across
several pipelines:

```sh
conduit graph config.toml --style recipes/graphviz.toml --pdf
```

See the commented
[`recipes/graphviz.toml`](https://github.com/NERC-CEH/conduit/blob/main/recipes/graphviz.toml)
template for the full set of keys (`palette`, `graph_attr`/`node_attr`/`edge_attr`,
`show_legend`, `cluster_by_frequency`, `style_function`).

## From Python

`conduit.build_graph` returns the same styled `graphviz.Digraph` that `conduit graph`
writes to disk, which renders inline in a notebook:

```python
import conduit

conduit.build_graph("config.toml")
```

## Where next

- [Validate before running](validate-before-running.md) — the rest of the pre-flight.
- [The pipeline model](../../concepts/pipeline-model.md) — why the graph exists before
  anything runs.
- [CLI reference](../../reference/cli.md) — every `conduit graph` flag.
