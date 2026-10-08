---
title: Validate before running
icon: lucide/shield-check
---

# Validate before running

Loading inputs and building the DAG is cheap; computing the pipeline may not be.
`--dry-run` does everything a real run does short of executing a node or writing an output, so a transposed axis, a hPa-for-Pa slip or a renamed input fails in a second rather than forty minutes into a run.

## The `--dry-run` pre-flight

```sh
conduit run config.toml --dry-run
```

It checks, in order, and prints a summary per stage:

1. **Config** — the TOML parses into a valid pipeline.
2. **Inputs** — every input file exists and opens.
   Only headers are read, not arrays.
3. **Input checks** — any [`[validation]` checks](#input-compatibility-checks) you declared pass (compatible grids, aligned time axes, matching coordinates).
   Skipped if you declared none, or under `[subset]`.
4. **DAG** — the driver builds, and the contract check passes on every edge with a contract at both ends.
5. **Execution plan** — every variable in `[outputs.*]` is reachable from the inputs.
6. **Wiring** — required inputs are all bound; unused inputs are reported ([below](#the-wiring-check)).
7. **Input contracts** — each loaded input's metadata (units, dims, coords, dtype) is checked against what its consuming node declares.
   A normal run defers this to when the node is called, so this stage is how you catch a file with wrong or missing `units` without running the pipeline.
8. **Output paths** — every destination would accept a write (supported extension, writable parent directory, and — for subset runs — a pre-created Zarr store).

A clean pre-flight exits `0`.
A problem with the config, inputs, DAG plan, wiring or output paths always fails.
Contract problems follow the [`[annotations]`](../../reference/configuration.md#annotations) policy: reported under `warn`, a non-zero exit under `strict`.

## Input compatibility checks

Some expectations concern the input files themselves, which nothing in the DAG records: "the climate and land-cover inputs must sit on the same grid", say, or "these two records must share a time axis".
Declare those in a [`[validation]`](../../reference/configuration.md#validation) block:

```toml
[validation]
checks = [
  { check = "spatial_grid_equal", inputs = ["*"] },
  { check = "time_equal",         inputs = ["climate", "land"] },
]
```

Each entry runs a named check over the listed `[inputs.*]` sections; `["*"]` means all of them.
The checks run on every `conduit run`, and a failure aborts before any node executes, listing every check that failed and why.
They are opt-in because differing inputs are normal — a daily forcing beside a monthly boundary condition — so only you know which relationships must hold.
The available checks and their arguments are in the [configuration reference](../../reference/configuration.md#validation).

## The wiring check

The wiring check asks whether every node gets fed.
On every run, before compute, conduit compares the inputs the DAG requires with the ones the config loaded:

- **Unbound input → error.** A node needs `temperature_daily` but nothing produces it.
  Usually a rename that did not propagate across file, config and function signature, or a missing `[inputs.*]` entry.
- **Unused input → warning.** You loaded a variable no node consumes, often a typo or a leftover.

## Reading a contract failure

When the contract check rejects an edge, the message names the two nodes, the facet, and the conflicting declarations.

The [flux recipe](../../recipes/flux-pipeline.md) keeps a `broken.toml` beside its working config: the same pipeline with one mistake in it.

```toml
--8<-- "recipes/flux_pipeline/broken.toml"
```

A stand-in for the satellite retrieval is built from the modelled weekly GPP, but declared in `umol m-2 s-1`, the units of the molar flux several nodes upstream, rather than the `g m-2 d-1` that `compare_with_satellite` consumes.
Each declaration looks fine on its own; they are only inconsistent with each other.

```bash exec="true"
python recipes/flux_pipeline/make_data.py > /dev/null
```

```bash exec="true" source="block" result="text" returncode="1"
conduit run --dry-run recipes/flux_pipeline/broken.toml
```

The failure names both ends of the edge, and comes during DAG construction, before any input is read.

To fix it, correct whichever annotation is wrong.
Had the units merely differed in scale, `umol m-2 s-1` against `nmol m-2 s-1` say, conduit would have converted them and there would be nothing to fix.
The check flags an edge only when the two declarations cannot be reconciled, so a partly annotated pipeline can adopt it without a wave of false positives.

To run this from a test or CI, see [Test your pipeline](test-your-pipeline.md); for specific error messages, see [Troubleshooting](../troubleshooting.md).
