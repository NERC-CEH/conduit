---
title: Visualise the graph
icon: lucide/git-fork
---

# Visualise the graph

`conduit graph` renders the DAG without running it, which is the quickest way to check that a config wired up the way you meant.

```sh
conduit graph config.toml --pdf
```

This writes `pipeline.pdf` (and the `.dot` source).
Each node shows its declared unit, and requested outputs are highlighted.
Nodes are coloured and clustered by their declared `freq` contract, never by section label; a node with no declared frequency joins its neighbours' cluster when they all agree.

Pass `--png` for PNG, and `-o/--output` to change the base filename.
`conduit graph` needs the `viz` extra **and** the [Graphviz system binary](../install.md#graphviz).

## What to look for

Structural mistakes that a config file hides are obvious in the graph:

- A node with no downstream consumer: nothing you asked for uses it.
- Two chains that should have met but did not, usually because a name differs by a suffix.
- A node in the wrong cluster: a `freq` contract says something you did not intend.

`conduit graph` builds the driver, so it also runs the contract check: if the config draws, its declared edges agree.

## Customising the styling

Pass a style file with `-s`/`--style` to override colours, layout, the legend, or the style function, and reuse it across pipelines:

```sh
conduit graph config.toml --style recipes/graphviz.toml --pdf
```

The commented [`recipes/graphviz.toml`](https://github.com/NERC-CEH/conduit/blob/main/recipes/graphviz.toml) template lists every key.

## From Python

`conduit.build_graph` returns the same styled `graphviz.Digraph`, which renders inline in a notebook:

```python
import conduit

conduit.build_graph("config.toml")
```
