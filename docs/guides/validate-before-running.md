---
title: Validate before running
icon: lucide/shield-check
---

# Validate before running

conduit can prove your pipeline is wired and typed correctly *before* it computes
anything. This guide shows how to use that guarantee: the `--dry-run` pre-flight, the
wiring check, and how to read a contract failure.

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
3. **DAG** — the driver builds, and the build-time contract check passes (every internal
   edge where both ends declare a contract is proven consistent).
4. **Execution plan** — every variable in `[outputs.*]` is reachable from the inputs.
5. **Wiring** — required inputs are all bound; unused inputs are reported (see below).
6. **Input contracts** — each loaded input's metadata (units, dims, coords, dtype) is
   checked against what its consuming node declares. This is the one contract check a
   normal run defers to run time, so a dry run surfaces a file delivered in the wrong
   units — or missing a `units` attribute — without running the pipeline.
7. **Output paths** — every destination would accept a write (supported extension,
   writable parent directory, and — for subset runs — a pre-created Zarr store).

A clean pre-flight exits `0`. A genuine problem with the config, inputs, DAG plan,
wiring or output paths always fails. Contract problems honour the active policy: in
`warn` mode they are reported but the dry run still passes; in `strict` mode they fail
with a non-zero exit (see [`[annotations]`](../reference/configuration.md#annotations)).

## The wiring check

Separately from *contracts* (are the units/dims right?), conduit checks the *plumbing*
(does every node get fed?). Before compute it diffs the DAG's required external inputs
against what `load_inputs` actually produced:

- **Unbound input → raises.** A node needs `temperature_daily` but nothing produces it
  — usually a rename drift across file ↔ config ↔ function signature, or a missing
  `[inputs.*]` entry. conduit fails with a clear message naming the missing node.
- **Unused input → warns.** You loaded a variable no node consumes. Harmless, but often
  a typo or a leftover — so conduit warns.

The wiring check runs automatically on every `conduit run` and is reported as its own
stage under `--dry-run`.

## Reading a contract failure

When the build-time check rejects an edge, the message names the two nodes, the facet
(units / dims / coords / dtype), and the conflicting declarations. For example, a node
declaring it needs pressure in `Pa` fed by a producer declaring `m`:

```
Contract mismatch on edge 'pressure_climate' -> 'pressure_anomaly_climate':
  units 'm' is not convertible to 'Pa'
```

To fix it, make the declarations agree — correct whichever annotation is wrong, or (if
the units are merely different but compatible, like `hPa` vs `Pa`) let conduit convert
by leaving `exact = false`. See [Add unit contracts](../get-started/units-and-contracts.md)
for a worked example and [Contracts before compute](../concepts/contracts.md) for how
the check generalises across facets.

## Why pre-flight at all?

Loading inputs and building the DAG is cheap; computing the pipeline may not be. A
dry run turns a class of mistakes that would otherwise surface 40 minutes into a run —
a transposed axis, a hPa/Pa slip, a renamed input — into a one-second failure at the
terminal. Wire it into CI to catch config drift before it reaches a cluster.
