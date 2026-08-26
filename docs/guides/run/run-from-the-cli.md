---
title: Run from the CLI
icon: lucide/terminal
---

# Run from the CLI

The `conduit` command runs pipelines from the terminal. The usual workflow is:

```
write a config.toml  →  conduit graph  →  conduit run --dry-run  →  conduit run
```

For a full reference of every command and flag, see the
[CLI reference](../../reference/cli.md).

## Run the pipeline

```sh
conduit run config.toml
```

conduit reads the config, builds the DAG, executes the nodes needed for your
`[outputs.*]` sections in dependency order, and writes the output files. Each output is
stamped with the config used to produce it, so the file records how it was made.

Only the nodes your requested outputs depend on ever run. Trim `[outputs.*]` to one
variable and unrelated branches are never touched.

### Pre-flight without running

Before committing to a long run, validate everything with `--dry-run`. It checks the
config, inputs, DAG, wiring and contracts without executing a node:

```sh
conduit run config.toml --dry-run
```

See [Validate before running](../validate/validate-before-running.md) for what each stage
checks, and [Visualise the graph](../validate/visualise-the-graph.md) for the picture.

### Overriding config from the CLI

A few flags override the config per invocation, without editing the file:

| Flag | Effect |
|------|--------|
| `--cache` / `--no-cache` | Force result caching on or off (overrides `[cache]`). |
| `--cache-dir <path>` | Directory for the cache store (implies `--cache`). |
| `--allow-overrides` | Permit a later module to override an earlier one's node. |

Caching, memory-bounded execution and parallel runs are covered in
[Scale up a pipeline](scale-up.md).

## Inspecting results

Output files are NetCDF (or whatever the extension implies). Load them in Python:

```python
import xarray as xr

ds = xr.open_dataset("results/anomaly.nc")
print(ds)
```

## Getting help

Every command supports `-h` / `--help`:

```sh
conduit -h
conduit run -h
conduit graph -h
conduit gridded -h   # parallel-Zarr commands (needs the geo extra)
```

## Where next

- [CLI reference](../../reference/cli.md) — every command and flag.
- [Validate before running](../validate/validate-before-running.md) — what `--dry-run` checks.
- [Drive conduit from Python](drive-from-python.md) — the same steps, without the CLI.
- [Scale up a pipeline](scale-up.md) — caching, blocking and parallel runs.
