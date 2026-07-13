---
title: Inline nodes & fan-out
icon: lucide/braces
---

# Inline nodes & fan-out

The `[[node]]` section defines DAG nodes directly in the config — no separate Python
module needed. It is ideal for glue (renames, arithmetic, simple derivations) and, with
`for_each`, for generating many similar nodes from one spec. This guide covers the two
node forms, declaring contracts, fan-out templating, and the `[[resample]]` preset.

## Inline expressions

The simplest node is a Python `expression`, evaluated with the listed `inputs` in
scope. The `xr` (xarray) module is available in the expression namespace.

```toml
[[node]]
name = "temperature_range_daily"
inputs = ["tmax_daily", "tmin_daily"]
expression = "tmax_daily - tmin_daily"
```

Input names must match the node names they refer to (including any frequency/section
suffix). `name` is the node this entry produces, which downstream nodes and
`[outputs.*]` can reference.

## Calling an external function

For anything beyond a one-liner, point at a function in an importable module with
`_import_path` + `function` instead of `expression`:

```toml
[[node]]
name = "custom_index_daily"
inputs = ["temperature_daily", "precipitation_daily"]
_import_path = "mypackage.indices"
function = "compute_custom_index"
```

The function must accept keyword arguments matching `inputs` and return an
`xarray.DataArray`. Each entry uses **either** `expression` **or**
(`_import_path` + `function`) — never both.

/// admonition | When to reach for a module instead
    type: tip

`[[node]]` calling a function is fine for a single derivation. When you have several
related functions, shared parameters, or want unit annotations on a signature, write a
[proper module](bring-your-own-module.md) — it is easier to test and reuse.
///

## Declaring contracts on a node

A node transforms its inputs, so conduit cannot infer its output contract. Declare any
of `units`, `dims`, `dtype`, `coords` to make the node a *typed producer* — its output
is stamped and validated at run time, and the [build-time contract
check](../concepts/contracts.md) can verify downstream consumers against it.

```toml
[[node]]
name = "aridity_index_daily"
inputs = ["precipitation_daily", "evapotranspiration_daily"]
expression = "precipitation_daily / evapotranspiration_daily"
units = "1"                 # dimensionless ratio
dims = ["time", "pixel"]    # optional dimension contract
```

`units` must be a valid UDUNITS/pint string and `dtype` a valid dtype; both are checked
when the config is parsed. Omit them and the node is a contract-unknown pass-through
(no static coverage for its output).

## Fan-out with `for_each`

`for_each` generates one node per value, substituting `{var}` into the string fields
(`name`, `inputs`, `expression`). It is the config-level equivalent of Hamilton's
`@parameterize`.

```toml
[[node]]
for_each = ["temperature", "precipitation", "humidity"]
name = "{var}_anomaly_daily"
inputs = ["{var}_daily"]
expression = "{var}_daily - {var}_daily.mean('time')"
```

This expands to three nodes — `temperature_anomaly_daily`, `precipitation_anomaly_daily`
and `humidity_anomaly_daily` — each wired to its own input. One spec, many nodes.

## The `[[resample]]` preset

`[[resample]]` is a thin preset over the fan-out engine: it desugars to one
annotation-preserving passthrough node per variable that applies
`conduit.transforms.resample`. Use it to aggregate one temporal frequency to a coarser
one.

```toml
[[resample]]
vars = ["temperature", "precipitation"]
from = "daily"
to = "weekly"
freq = "7D"
aggfunc = "mean"          # mean | sum | max | min | first | last (default: mean)
```

This produces `temperature_weekly` and `precipitation_weekly` from their daily
counterparts. Because resampling preserves units and dims, the contract check
propagates each source's declared contract across the resample edge — and because it
does *not* preserve frequency, the node declares `freq` as its own output contract.

`from` and `to` are only the node-name suffixes to read from and write to; the pandas
offset alias in `freq` is what sets the frequency. Nothing is inferred from the labels,
so any pair works:

```toml
[[resample]]
vars = ["temperature"]
from = "hourly"
to = "daily"
freq = "1D"
aggfunc = "max"
```

## See also

- [Bring your own module](bring-your-own-module.md) — for logic that outgrows an inline
  node.
- [Configuration reference](../reference/configuration.md) — the full `[[node]]` and
  `[[resample]]` key list.
