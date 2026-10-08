---
title: Run from the CLI
icon: lucide/terminal
---

# Run from the CLI

The `conduit` command (the `cli` extra) runs pipelines from the terminal.
The usual workflow is:

```
write a config.toml  →  conduit graph  →  conduit run --dry-run  →  conduit run
```

## Run the pipeline

```sh
conduit run config.toml
```

conduit builds the DAG, executes the nodes your `[outputs.*]` sections need, and writes the output files, each [stamped with the config](../../reference/data-formats.md#output-provenance) that produced it.
It reports each stage as it goes, then one line per file written, with its variable count and size, and the elapsed time.

Only the nodes your requested outputs depend on run, so trimming `[outputs.*]` to one variable skips unrelated branches.

Before a long run, check everything with `conduit run config.toml --dry-run`; see [Validate before running](../validate/validate-before-running.md).

## Overriding the config

A few flags override the config for one invocation:

| Flag | Effect |
|------|--------|
| `--cache` / `--no-cache` | Force result caching on or off (overrides `[cache]`). |
| `--cache-dir <path>` | Directory for the cache store (implies `--cache`). |
| `--allow-overrides` | Permit a later module to override an earlier one's node. |

Caching, memory-bounded execution and parallel runs are covered in [Scale up a pipeline](scale-up.md).

## Inspecting results

Outputs are ordinary files in the format their extension names, so open them with xarray:

```python
import xarray as xr

ds = xr.open_dataset("results/anomaly.nc")
```

Every command takes `-h`/`--help`, and the [CLI reference](../../reference/cli.md) lists every flag.
