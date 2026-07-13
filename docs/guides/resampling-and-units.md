---
title: Resampling & units
icon: lucide/timer
---

# Resampling & units: choosing `aggfunc`

Resampling reduces along the time axis. That reduction is **dimensionally homogeneous**:
both `mean` and `sum` leave the units unchanged, so conduit copies the input's attributes
(including CF `units`) straight through to the result. This matches `pint-xarray`, which
also does not multiply by the timestep on a sum.

The consequence is important, and it is the reason this page exists:

/// admonition | Unit validation cannot catch a wrong `aggfunc`
    type: warning

Because the units are the same either way, **no contract check will save you here**. A
wrong `aggfunc` produces a result that is dimensionally consistent and physically
meaningless. Choosing it correctly is on you.
///

## Match `aggfunc` to the *kind* of quantity

| Kind of quantity | Example units | Use | Result |
|---|---|---|---|
| **Rate** (intensive) | `g C m-2 day-1`, `mm hr-1`, `W m-2` | `mean` | the mean rate over the window, same units |
| **Amount per period** (extensive) | `g C m-2` accumulated that day, `mm` fallen that day | `sum` | the window total, same units |

## The footgun

Summing a **rate** to get a window total.

The correct operation for that is an integral — Σ rateᵢ · Δt — which cancels the time
dimension in the units (`g C m-2 day-1` × `day` → `g C m-2`). But xarray's `.sum()` omits
the Δt factor, so you get:

```
7 × (g C m-2 day-1)  ->  still labelled "g C m-2 day-1"
```

a number seven times too large, wearing the units of a rate. It is dimensionally
consistent — which is exactly why the units check passes — and it is wrong.

```toml
# WRONG: gpp is a rate (g C m-2 day-1); summing it does not integrate it.
[[resample]]
vars = ["gpp"]
from = "daily"
to = "weekly"
freq = "7D"
aggfunc = "sum"

# RIGHT: the weekly mean daily rate, same units.
[[resample]]
vars = ["gpp"]
from = "daily"
to = "weekly"
freq = "7D"
aggfunc = "mean"
```

If you genuinely want the weekly *amount* from a daily *rate*, do the multiplication
explicitly — resample with `mean`, then scale by the window length in a `[[node]]`, and
declare the resulting units:

```toml
[[node]]
name = "gpp_weekly_total"
inputs = ["gpp_weekly"]
expression = "gpp_weekly * 7.0"
units = "g C m-2"
```

Now the declared units say what the number is, and the contract check has something to
verify.

## See also

- [Configuration › Resample](../reference/configuration.md#resample) — the `[[resample]]` keys.
- [Contracts](../concepts/contracts.md) — what the checks can and cannot catch.
