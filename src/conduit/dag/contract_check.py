r"""Build-time (static) and dry-run contract checks for the Hamilton DAG.

`xarray-annotated` validates a *single function's* declared contract when that
function runs. This module lifts that guarantee to the *whole graph*, and to a
point *before any compute*: `check_dag_contracts` verifies that every internal
edge whose producer and consumer both declare a contract is mutually consistent,
so a mismatch surfaces as soon as the driver is built rather than part way through
a run; `check_input_contracts` validates the metadata of the actually-loaded input
``DataArray``\\ s against the contracts declared by their consumers, without
executing any node (the basis of ``conduit run --dry-run``).

**Facets.** The checks are generic over every `xarray-annotated` facet, not just
units:

- **units** — pint/CF physical units (`xarray_annotated.units`);
- **dims**, **coords**, **dtype** — structural properties
  (`xarray_annotated.schema`);
- **freq** — the spacing (and phase) of the time axis
  (`xarray_annotated.temporal`).

Each facet is a `_Facet` descriptor pairing a way to pull that facet off a
`Declared` with a policy, a marker-vs-marker edge predicate (for the build-time
check), and a marker-vs-array runtime check (for the input check). All of these
come from `xarray-annotated`'s public API: the unified declaration reader
(`declarations_from_signature`), the runtime checks (`check_units`,
`check_schema`, `check_freq`), and the marker-vs-marker predicates (units
`units_compatible`/`units_equal`, schema `dims_compatible`/`dtype_compatible`,
temporal `freq_compatible`). conduit only assembles them per facet.

**Edge vs input.** ``coords`` declarations are lower bounds ("at least these coords
are present"), so two coord declarations on an edge can never be *proven*
inconsistent — coords therefore participates in the input check but not the
build-time edge check (``edge=None``). Units/dims/dtype/freq are exact enough to
compare at the edge. ``freq`` is the one facet inferred from coordinate *values*
rather than metadata, but reading a 1-D datetime coordinate still executes no node,
so it remains a legitimate ``--dry-run`` pre-flight.

**Provable-only.** A build-time edge is flagged only when the two declarations are
*provably* inconsistent (e.g. dimensionally incompatible units, disjoint dim sets,
different dtype kinds). Compatible-but-inexact declarations are flagged only when
the facet's policy demands it (units ``on_inexact="error"``). This preserves the
opt-in contract: partially-annotated pipelines never trigger false positives.

**Passthrough propagation.** A node with no statically declared producer contract
(fed by an external file, or a ``[[node]]`` that transforms its input) breaks the
edge chain. But a node tagged *passthrough* (`conduit.dag.node.PASSTHROUGH_TAG`,
e.g. a ``[[resample]]`` node) preserves its input's contract, so a declared unit is
propagated across it — forward for the DAG check, backward for the input check.
This is generic: any passthrough-tagged node participates, with no module
special-cased. Non-passthrough ``[[node]]`` modules can transform units arbitrarily
and so are not propagated; they fall back to the runtime check.

Propagation is *per facet* (`_Facet.passthrough_preserving`): a resample preserves
its input's units but is precisely the thing that *changes* its frequency, so
``freq`` is never propagated across a passthrough. A ``[[resample]]`` node instead
declares its own output frequency (its offset), making it an ordinary producer for
that one facet.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import combinations
from typing import TYPE_CHECKING, Any

import xarray as xr
from hamilton import graph_types
from xarray_annotated import declarations_from_signature
from xarray_annotated.schema import check_schema, dims_compatible, dtype_compatible
from xarray_annotated.schema import get_policy as schema_get_policy
from xarray_annotated.temporal import check_freq, freq_compatible
from xarray_annotated.temporal import get_policy as temporal_get_policy
from xarray_annotated.units import check_units, units_compatible, units_equal
from xarray_annotated.units import get_policy as units_get_policy

if TYPE_CHECKING:
    from hamilton import driver
    from xarray_annotated import Declared

# Facet map keys, in a stable order (units first so its messages/behaviour match
# the original units-only checker).
_FACET_NAMES = ("units", "dims", "coords", "dtype", "freq")


# ---------------------------------------------------------------------------
# Marker-vs-marker edge predicates
# ---------------------------------------------------------------------------
# Each returns a short "why" string when the two declarations are *provably*
# inconsistent, else None. `pol` is the facet's resolved policy.


def _units_edge(a: str, b: str, pol: Any) -> str | None:
    if not units_compatible(a, b):
        return "dimensionally incompatible"
    if pol.on_inexact == "error" and not units_equal(a, b):
        return "units differ; exact match required"
    return None


def _dims_edge(a: Any, b: Any, _pol: Any) -> str | None:
    return None if dims_compatible(a, b) else "dims incompatible"


def _dtype_edge(a: Any, b: Any, _pol: Any) -> str | None:
    return None if dtype_compatible(a, b) else "dtypes incompatible"


def _freq_edge(a: Any, b: Any, _pol: Any) -> str | None:
    return None if freq_compatible(a, b) else "frequencies incompatible"


# ---------------------------------------------------------------------------
# Runtime (input) checks — marker(s) vs a loaded DataArray
# ---------------------------------------------------------------------------


def _units_input_check(da: xr.DataArray, decls: list, name: str) -> None:
    for declared in sorted(decls):
        check_units(da, declared, name)


def _schema_input_check(da: xr.DataArray, decls: list, name: str) -> None:
    check_schema(da, list(decls), name)


def _freq_input_check(da: xr.DataArray, decls: list, name: str) -> None:
    check_freq(da, list(decls), name)


@dataclass(frozen=True)
class _Facet:
    """One annotation facet: how to read it, compare it, and check it at runtime."""

    name: str
    get_policy: Callable[[], Any]
    #: Pull this facet's stored value out of a `Declared`, or None if undeclared.
    #: Units yields the unit *string* (`.unit.unit`); schema facets yield the
    #: marker, so downstream maps keep the same value types as before the unified
    #: reader.
    from_declared: Callable[["Declared"], Any]
    #: Marker-vs-marker edge predicate, or None to skip the build-time edge check.
    edge: Callable[[Any, Any, Any], str | None] | None
    #: Marker(s)-vs-array runtime check for `check_input_contracts`.
    runtime_check: Callable[[xr.DataArray, list, str], None]
    #: Whether a passthrough node preserves this facet (so it can be propagated).
    passthrough_preserving: bool
    #: Apply `_check_dag`'s caller-supplied ``on_inexact`` override to this facet's
    #: policy. Only units has an ``on_inexact`` axis, so only units supplies one;
    #: for every other facet the override is simply not theirs to interpret.
    override_policy: Callable[[Any, str], Any] | None = None


def _units_override_policy(pol: Any, on_inexact: str) -> Any:
    return replace(pol, on_inexact=on_inexact)


_FACETS: tuple[_Facet, ...] = (
    _Facet(
        "units",
        units_get_policy,
        lambda d: d.unit.unit if d.unit is not None else None,
        _units_edge,
        _units_input_check,
        True,
        override_policy=_units_override_policy,
    ),
    _Facet(
        "dims",
        schema_get_policy,
        lambda d: d.dims,
        _dims_edge,
        _schema_input_check,
        False,
    ),
    _Facet(
        "coords",
        schema_get_policy,
        lambda d: d.coords,
        None,
        _schema_input_check,
        False,
    ),
    _Facet(
        "dtype",
        schema_get_policy,
        lambda d: d.dtype,
        _dtype_edge,
        _schema_input_check,
        False,
    ),
    _Facet(
        "freq",
        temporal_get_policy,
        lambda d: d.freq,
        _freq_edge,
        _freq_input_check,
        # A passthrough (e.g. [[resample]]) is exactly what *changes* a frequency,
        # so a source's declared freq is never propagated across one.
        False,
    ),
)
_UNITS_ONLY: tuple[_Facet, ...] = (_FACETS[0],)

# Per-facet map: node name -> (declaration, producer/consumer label).
_Produced = dict[str, tuple[Any, str]]
_Consumed = dict[str, list[tuple[Any, str]]]
_Maps = dict[str, tuple[_Produced, _Consumed]]


# ---------------------------------------------------------------------------
# Declaration collection off the built graph
# ---------------------------------------------------------------------------


def _originating_functions(hg: "graph_types.HamiltonGraph") -> list[Any]:
    """Return the unique originating functions across all nodes, first-seen order."""
    seen: set[int] = set()
    funcs: list[Any] = []
    for node in hg.nodes:
        for fn in node.originating_functions or ():
            if id(fn) not in seen:
                seen.add(id(fn))
                funcs.append(fn)
    return funcs


def _passthrough_edges(hg: "graph_types.HamiltonGraph") -> dict[str, str]:
    """Passthrough node name -> its single source name.

    A passthrough node (tagged ``conduit_passthrough``, e.g. a ``[[resample]]``
    node) preserves its input's declared contract, so the source's declaration is
    propagated across it. Any node so tagged with exactly one dependency qualifies —
    no module is special-cased.
    """
    from conduit.dag.node import PASSTHROUGH_TAG

    return {
        node.name: next(iter(node.required_dependencies))
        for node in hg.nodes
        if node.tags.get(PASSTHROUGH_TAG) == "true"
        and len(node.required_dependencies) == 1
    }


def _record(
    maps: _Maps, name: str, decl: "Declared", label: str, *, produced: bool
) -> None:
    """Route each declared facet of ``decl`` into its produced/consumed map."""
    for facet in _FACETS:
        value = facet.from_declared(decl)
        if value is None:
            continue
        prod_map, cons_map = maps[facet.name]
        if produced:
            prod_map[name] = (value, label)
        else:
            cons_map.setdefault(name, []).append((value, label))


def _collect_contract_maps(dr: "driver.Driver") -> tuple[_Maps, dict[str, str]]:
    """Read declared contracts off the built DAG's node signatures, per facet.

    Returns ``(maps, passthrough_edges)`` where ``maps[facet]`` is
    ``(produced, consumed)`` — the shared source for both the build-time
    (`check_dag_contracts`) and runtime (`check_input_contracts`) checks. Each
    node's contract is read once via `declarations_from_signature` and its facets
    routed by `_record`.
    """
    hg = graph_types.HamiltonGraph.from_graph(dr.graph)
    maps: _Maps = {name: ({}, {}) for name in _FACET_NAMES}
    for fn in _originating_functions(hg):
        fn_name = getattr(fn, "__name__", repr(fn))
        ins, out = declarations_from_signature(fn)
        if isinstance(out, dict):
            for name, decl in out.items():
                _record(maps, name, decl, fn_name, produced=True)
        elif out is not None:
            _record(maps, fn_name, out, fn_name, produced=True)
        for name, decl in ins.items():
            _record(maps, name, decl, fn_name, produced=False)
    return maps, _passthrough_edges(hg)


# ---------------------------------------------------------------------------
# Propagation across (unit-preserving) passthrough edges
# ---------------------------------------------------------------------------


def _propagate_forward(produced: _Produced, passthrough_edges: dict[str, str]) -> None:
    """Give each passthrough target its source's declaration (to a fixpoint)."""
    changed = True
    while changed:
        changed = False
        for target, source in passthrough_edges.items():
            if target not in produced and source in produced:
                produced[target] = (produced[source][0], f"passthrough of {source}")
                changed = True


def _propagate_backward(
    expected: dict[str, list], passthrough_edges: dict[str, str]
) -> None:
    """Push each passthrough target's expected declarations onto its source."""
    changed = True
    while changed:
        changed = False
        for target, source in passthrough_edges.items():
            if target not in expected:
                continue
            dst = expected.setdefault(source, [])
            before = len(dst)
            for decl in expected[target]:
                if decl not in dst:
                    dst.append(decl)
            if len(dst) != before:
                changed = True


# ---------------------------------------------------------------------------
# The two checks (facet-parametric)
# ---------------------------------------------------------------------------


def _check_dag(
    dr: "driver.Driver",
    facets: tuple[_Facet, ...],
    on_inexact: str | None,
) -> None:
    maps, passthrough_edges = _collect_contract_maps(dr)
    findings: list[str] = []
    for facet in facets:
        pol = facet.get_policy()
        if not pol.enabled or facet.edge is None:
            continue
        if on_inexact is not None and facet.override_policy is not None:
            pol = facet.override_policy(pol, on_inexact)
        produced, consumed = maps[facet.name]
        if facet.passthrough_preserving:
            _propagate_forward(produced, passthrough_edges)
        for name, consumers in consumed.items():
            candidates: list[tuple[Any, str]] = []
            if name in produced:
                decl, who = produced[name]
                candidates.append((decl, f"output of {who}"))
            candidates.extend((decl, f"input of {who}") for decl, who in consumers)
            if len(candidates) < 2:
                continue
            # All pairs, not star-wise against candidates[0]: three of the four edge
            # predicates are *non-transitive*, because a loose declaration is
            # compatible with everything. Dims("x","y") is compatible with both
            # Dims("x","y", ordered=True) and Dims("y","x", ordered=True), which
            # provably conflict with each other — a star check anchored on the loose
            # one would pass. (dtype `exact` and freq anchors have the same shape;
            # units alone is transitive, being an equivalence relation.) Candidates
            # are producer-first, so combinations() still leads with "output of ...".
            for (a_decl, a_src), (b_decl, b_src) in combinations(candidates, 2):
                why = facet.edge(a_decl, b_decl, pol)
                if why is not None:
                    findings.append(
                        f"  {name!r}: {a_src} declares {a_decl!r} but {b_src} "
                        f"declares {b_decl!r} ({why})"
                    )
    if findings:
        raise ValueError(
            "contract declaration mismatch(es) in DAG:\n" + "\n".join(findings)
        )


def _check_inputs(
    dr: "driver.Driver", inputs: dict[str, Any], facets: tuple[_Facet, ...]
) -> None:
    maps, passthrough_edges = _collect_contract_maps(dr)
    for facet in facets:
        if not facet.get_policy().enabled:
            continue
        _, consumed = maps[facet.name]
        expected: dict[str, list] = {}
        for name, consumers in consumed.items():
            dst = expected.setdefault(name, [])
            for decl, _ in consumers:
                if decl not in dst:
                    dst.append(decl)
        if facet.passthrough_preserving:
            _propagate_backward(expected, passthrough_edges)
        for name, value in inputs.items():
            decls = expected.get(name)
            if not decls or not isinstance(value, xr.DataArray):
                continue
            facet.runtime_check(value, decls, name)


def check_dag_contracts(dr: "driver.Driver") -> None:
    """Verify declared contracts are consistent across every built-DAG edge.

    Runs the build-time edge check for all facets (units, dims, dtype, freq; coords
    is skipped — its declarations are lower bounds). A provable mismatch always raises
    `ValueError` (it is a genuine pipeline-definition error). Each facet is skipped
    when its policy is disabled (the conftest default), so this is a no-op for
    pipelines that opt out of contract handling.
    """
    _check_dag(dr, _FACETS, on_inexact=None)


def check_dag_units(dr: "driver.Driver", *, on_inexact: str | None = None) -> None:
    """Units-only build-time edge check (with optional ``on_inexact`` override).

    A thin wrapper over `check_dag_contracts` restricted to the units facet;
    ``on_inexact`` defaults from the active units policy when ``None``.
    """
    _check_dag(dr, _UNITS_ONLY, on_inexact=on_inexact)


def check_input_contracts(dr: "driver.Driver", inputs: dict[str, Any]) -> None:
    """Validate loaded inputs' metadata against the contracts declared for them.

    The runtime leg that cannot be done statically, run for every facet: an input's
    ``units`` attribute (units), its dims / coords / dtype (schema), and the inferred
    frequency of its time axis (temporal), are checked against the contract declared
    by its consumer(s). Dims/coords/dtype live in the file header and a frequency
    needs only the 1-D datetime coordinate, so — like units — this executes no node
    and is suitable as a ``run --dry-run`` pre-flight. Contracts are propagated
    backward through unit-preserving passthrough edges to a fixpoint.
    """
    _check_inputs(dr, inputs, _FACETS)


def check_input_units(dr: "driver.Driver", inputs: dict[str, Any]) -> None:
    """Units-only input check (see `check_input_contracts`)."""
    _check_inputs(dr, inputs, _UNITS_ONLY)
