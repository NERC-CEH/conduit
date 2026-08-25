---
title: CLI
icon: lucide/square-terminal
---

The `conduit` command ships in the `cli` extra (`pip install conduit[cli]`). Every
subcommand wraps a function from the Python API — [`conduit.run`](modules/conduit.pipeline.md),
[`conduit.dry_run`](modules/conduit.pipeline.md) and
[`conduit.build_graph`](modules/conduit.graph.md) — so anything below can be done from
Python instead, with no extra installed.

## `conduit run`

::: mkdocs-typer2
    :module: conduit.cli.app
    :name: conduit
    :command: run
    :termynal: true
    :width: 80
    :prompt: ❯

## `conduit graph`

::: mkdocs-typer2
    :module: conduit.cli.app
    :name: conduit
    :command: graph
    :termynal: true
    :width: 80
    :prompt: ❯

## `conduit gridded`

Parallel-Zarr commands for gridded pipelines, needing the `geo` extra. They bracket a set
of independent `[subset]` runs: create the shared store once, run the subsets
concurrently, then stitch the parts back together. See
[Scale up](../guides/scaling/scale-up.md) for the whole workflow.

### `conduit gridded create-store`

::: mkdocs-typer2
    :module: conduit.cli.app
    :name: conduit
    :command: gridded create-store
    :termynal: true
    :width: 80
    :prompt: ❯

### `conduit gridded merge`

::: mkdocs-typer2
    :module: conduit.cli.app
    :name: conduit
    :command: gridded merge
    :termynal: true
    :width: 80
    :prompt: ❯
