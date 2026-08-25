---
title: Validate before running
icon: lucide/shield-check
---

# Validate before running

Loading inputs and building the DAG is cheap.
Computing the pipeline may not be.

`--dry-run` does everything a real run does up to the point of executing a node, so a transposed axis, a hPa-for-Pa slip or a renamed input fails at the terminal in a second rather than forty minutes into a run.
Run it in CI and config drift never reaches a cluster.

## The `--dry-run` pre-flight

`--dry-run` runs everything a real run depends on, but executes no node and writes no
output:

```sh
conduit run config.toml --dry-run
```

It validates, in order, and prints a per-stage summary:

1. **Config** — the TOML parses into a valid pipeline.
2. **Inputs** — every input file exists and opens. Files are opened lazily, so this
   reads metadata (headers) only, not the full arrays.
3. **Input checks** — any [`[validation]` checks](#input-compatibility-checks) you
   declared pass (compatible grids, aligned time axes, matching coordinates). Skipped if
   you declared none, or under `[subset]`.
4. **DAG** — the driver builds, and the build-time contract check passes (every internal
   edge where both ends declare a contract is checked for consistency).
5. **Execution plan** — every variable in `[outputs.*]` is reachable from the inputs.
6. **Wiring** — required inputs are all bound; unused inputs are reported (see below).
7. **Input contracts** — each loaded input's metadata (units, dims, coords, dtype) is
   checked against what its consuming node declares. This is the one contract check a
   normal run defers to run time, so a dry run surfaces a file delivered in the wrong
   units — or missing a `units` attribute — without running the pipeline.
8. **Output paths** — every destination would accept a write (supported extension,
   writable parent directory, and — for subset runs — a pre-created Zarr store).

A clean pre-flight exits `0`. A genuine problem with the config, inputs, DAG plan,
wiring or output paths always fails. Contract problems honour the active policy: in
`warn` mode they are reported but the dry run still passes; in `strict` mode they fail
with a non-zero exit (see [`[annotations]`](../../reference/configuration.md#annotations)).

## Input compatibility checks

Contracts and wiring validate what the DAG *declares*. Some expectations are about the
input files themselves, and nothing in the DAG records them: "the climate and land-cover
inputs must sit on the same grid", say, or "these two records must share a time axis".
Declare those in a [`[validation]`](../../reference/configuration.md#validation) block:

```toml
[validation]
checks = [
  { check = "spatial_grid_equal", inputs = ["*"] },
  { check = "time_equal",         inputs = ["climate", "land"] },
]
```

Each entry runs a named check (`time_equal`, `time_subset`, `spatial_grid_equal`,
`crs_equal`, `coords_equal`) over the listed `[inputs.*]` sections; `["*"]` means all of
them. A failure aborts the run before any node executes, with a single message listing
every check that failed and why. The checks run automatically on every `conduit run` and
are reported as a stage under `--dry-run`.

They are **opt-in.** Different time axes across inputs are perfectly normal — a daily
forcing and a monthly boundary condition — so the `[validation]` block is where you state
which relationships must hold. (The full check list and keyword arguments are in the
[configuration reference](../../reference/configuration.md#validation); the predicates
themselves are documented in [`conduit.checks`](../../reference/modules/conduit.checks.md).)

## The wiring check

Contracts ask whether the units and dims are right. The wiring check asks a separate
question: does every node get fed? Before compute, conduit diffs the DAG's required
external inputs against what `load_inputs` actually produced:

- **Unbound input → raises.** A node needs `temperature_daily` but nothing produces it.
  Usually this is a rename that did not propagate across file, config and function
  signature, or a missing `[inputs.*]` entry. conduit fails with a message naming the
  missing node.
- **Unused input → warns.** You loaded a variable no node consumes. Harmless, but often
  a typo or a leftover — so conduit warns.

The wiring check runs automatically on every `conduit run` and is reported as its own
stage under `--dry-run`.

## Reading a contract failure

When the build-time check rejects an edge, the message names the two nodes, the facet
(units / dims / coords / dtype), and the conflicting declarations. For example, a node
declaring it needs pressure in `Pa` fed by a producer declaring `m`:

```
Error: contract declaration mismatch(es) in DAG:
  'sat_gpp': output of sat_gpp declares 'umol m-2 s-1' but input of
  compare_with_satellite declares 'g m-2 d-1' (dimensionally incompatible)
```

That is the [flux recipe's `broken.toml`](../../recipes/flux-pipeline.md), which is there to produce this failure on demand.

To fix one, correct whichever annotation is wrong so the two agree.
Where the units are different but compatible, `hPa` against `Pa` say, conduit converts them for you and there is nothing to fix; leave `on_inexact = "convert"`.

## Where next

- [Declaring contracts](../authoring/contracts.md) — writing the declarations these checks compare.
- [Test your pipeline](../authoring/test-your-pipeline.md) — calling `dry_run` from a test.
- [`[annotations]` reference](../../reference/configuration.md#annotations) — every policy key.
- [Troubleshooting](../troubleshooting.md) — specific error messages and their causes.
