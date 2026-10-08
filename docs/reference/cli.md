---
title: CLI
icon: lucide/square-terminal
---

The `conduit` command ships in the `cli` extra.
Each subcommand wraps a [Python API](python-api.md) function, so anything below can also be done from Python.

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

Commands that bracket a set of parallel `[subset]` runs (needs the `geo` extra): create the shared store, then merge the parts.
See [Scale up](../guides/run/scale-up.md#parallel-subset-runs) for the workflow.

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
