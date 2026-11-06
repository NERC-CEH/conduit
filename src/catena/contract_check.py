r"""Build-time (static) and dry-run contract checks for the Hamilton DAG.

`xarray-annotated` validates a *single function's* declared contract when that
function runs. This module lifts that guarantee to the *whole graph*, and to a
point *before any compute*: `check_dag_contracts` verifies that every internal
edge whose producer and consumer both declare a contract is mutually consistent,
so a mismatch surfaces as soon as the driver is built rather than part way through
a run; `check_input_contracts` validates the metadata of the actually-loaded input
``DataArray``\\ s against the contracts declared by their consumers, without
executing any node (the basis of ``catena run --dry-run``).

**Facets.** The checks cover every `xarray-annotated` facet — **units** (pint/CF),
**dims** / **coords** / **dtype** (schema), and **freq** (the spacing and phase of
the time axis) — and apply the rules `xarray_annotated.enforce` applies at run time,
through `xarray_annotated.declaration_conflicts` for edges and
`xarray_annotated.declaration_violations` for inputs. A malformed declaration, on a
function no `xarray_annotated.enforce` has validated, raises `CatenaValueError`.

**Switching off.** Both checks do nothing when `xarray-annotated` is switched off,
with ``XARRAY_ANNOTATED_ENABLED=false`` or inside ``xarray_annotated.enabled(False)``.

Two distinctions apply:

- **Edge vs input.** ``coords`` declarations are lower bounds ("at least these"), so
  two of them can never be shown inconsistent; coords participates in the input
  check only. ``freq`` is inferred from coordinate *values*, but reading a 1-D
  datetime coordinate executes no node, so it stays a legitimate ``--dry-run``
  pre-flight.
- **Provable-only.** An edge is flagged only when the two declarations are *provably*
  inconsistent (different units, disjoint dim sets, different dtypes). An edge with a
  declaration missing at either end is not flagged, which lets a partially-annotated
  pipeline adopt the check without a wave of false positives. Units that could be
  converted still count as different, since nothing converts them between nodes.
  An edge that passes is not proven safe: ``Freq("D", gaps_ok=True)`` is compatible
  with ``Freq("D")``, which still raises on an axis with holes when the data arrives.

**Passthrough propagation.** A node with no declared producer contract breaks the
edge chain. A node tagged *passthrough* (`catena.nodegen.PASSTHROUGH_TAG`)
preserves its input's units, so a declared unit is propagated across it — forward
for the DAG check, backward for the input check. A non-passthrough ``[[node]]`` may
transform its input arbitrarily, so nothing is propagated and it falls back to the
runtime check.

Only units are propagated: a resample preserves its input's units but is precisely
the thing that *changes* its frequency, so a ``[[resample]]`` node declares its own
output frequency instead, making it an ordinary producer for that one facet.
"""

from collections.abc import Iterable
from dataclasses import replace
from itertools import combinations
from typing import Any

import xarray as xr
from hamilton import driver, graph_types
from xarray_annotated import (
    Declared,
    Unit,
    assert_valid_declaration,
    declaration_conflicts,
    declaration_violations,
    declarations_from_signature,
    resolve_enabled,
)

from .errors import CatenaValueError

# Node name -> (declaration, producer label).
_Produced = dict[str, tuple[Declared, str]]
# Node name -> a (declaration, consumer label) per consumer.
_Consumed = dict[str, list[tuple[Declared, str]]]


# ---------------------------------------------------------------------------
# Declaration collection off the built graph
# ---------------------------------------------------------------------------


def _originating_functions(hg: graph_types.HamiltonGraph) -> list[Any]:
    """Return the unique originating functions across all nodes, first-seen order."""
    seen: set[int] = set()
    funcs: list[Any] = []
    for node in hg.nodes:
        for fn in node.originating_functions or ():
            if id(fn) not in seen:
                seen.add(id(fn))
                funcs.append(fn)
    return funcs


def _passthrough_edges(hg: graph_types.HamiltonGraph) -> dict[str, str]:
    """Passthrough node name -> its single source name.

    A passthrough node (tagged ``catena_passthrough``, e.g. a ``[[resample]]``
    node) preserves its input's declared contract, so the source's declaration is
    propagated across it. Any node so tagged with exactly one dependency qualifies —
    no module is special-cased.
    """
    from .nodegen import PASSTHROUGH_TAG

    return {
        node.name: next(iter(node.required_dependencies))
        for node in hg.nodes
        if node.tags.get(PASSTHROUGH_TAG) == "true"
        and len(node.required_dependencies) == 1
    }


def _collect_declarations(
    dr: driver.Driver,
) -> tuple[_Produced, _Consumed, dict[str, str]]:
    """Read declared contracts off the built DAG's node signatures.

    Returns ``(produced, consumed, passthrough_edges)``, the shared source for both
    the build-time (`check_dag_contracts`) and runtime (`check_input_contracts`)
    checks. Each node's contract is read once via `declarations_from_signature`.
    """
    hg = graph_types.HamiltonGraph.from_graph(dr.graph)
    produced: _Produced = {}
    consumed: _Consumed = {}
    for fn in _originating_functions(hg):
        fn_name = getattr(fn, "__name__", repr(fn))
        ins, out = declarations_from_signature(fn)
        if isinstance(out, dict):
            for name, decl in out.items():
                produced[name] = (decl, fn_name)
        elif out is not None:
            produced[fn_name] = (out, fn_name)
        for name, decl in ins.items():
            consumed.setdefault(name, []).append((decl, fn_name))
    return produced, consumed, _passthrough_edges(hg)


# ---------------------------------------------------------------------------
# Propagation of units across passthrough edges
# ---------------------------------------------------------------------------


def _propagate_units_forward(
    produced: _Produced, passthrough_edges: dict[str, str]
) -> None:
    """Give each passthrough target its source's declared unit (to a fixpoint)."""
    changed = True
    while changed:
        changed = False
        for target, source in passthrough_edges.items():
            source_unit = produced[source][0].unit if source in produced else None
            if source_unit is None:
                continue
            if target not in produced:
                produced[target] = (
                    Declared(unit=source_unit),
                    f"passthrough of {source}",
                )
                changed = True
            elif produced[target][0].unit is None:
                decl, who = produced[target]
                produced[target] = (
                    replace(decl, unit=source_unit),
                    f"{who} (units from {source})",
                )
                changed = True


def _propagate_units_backward(
    expected: dict[str, list[Unit]], passthrough_edges: dict[str, str]
) -> None:
    """Push each passthrough target's expected units onto its source."""
    changed = True
    while changed:
        changed = False
        for target, source in passthrough_edges.items():
            if target not in expected:
                continue
            dst = expected.setdefault(source, [])
            before = len(dst)
            for unit in expected[target]:
                if unit not in dst:
                    dst.append(unit)
            if len(dst) != before:
                changed = True


# ---------------------------------------------------------------------------
# The two checks
# ---------------------------------------------------------------------------


def _distinct[T](markers: Iterable[T | None]) -> list[T]:
    """Return the declared markers, without repeats, in first-seen order."""
    seen: list[T] = []
    for marker in markers:
        if marker is not None and marker not in seen:
            seen.append(marker)
    return seen


def check_dag_contracts(dr: driver.Driver) -> None:
    """Verify declared contracts are consistent across every built-DAG edge.

    Runs the build-time edge check for all facets (units, dims, dtype, freq; coords
    is skipped — its declarations are lower bounds). A provable mismatch raises
    `CatenaValueError` naming every offending edge. This is a no-op when
    `xarray-annotated` is switched off.
    """
    if not resolve_enabled():
        return
    produced, consumed, passthrough_edges = _collect_declarations(dr)
    _propagate_units_forward(produced, passthrough_edges)
    findings: list[str] = []
    for name, consumers in consumed.items():
        candidates: list[tuple[Declared, str]] = []
        if name in produced:
            decl, who = produced[name]
            candidates.append((decl, f"output of {who}"))
        candidates.extend((decl, f"input of {who}") for decl, who in consumers)
        for decl, source in candidates:
            try:
                assert_valid_declaration(decl, f"{name!r}, {source}")
            except ValueError as exc:
                raise CatenaValueError(
                    f"malformed contract declaration: {exc}"
                ) from exc
        # All pairs, not star-wise against candidates[0]: three of the four facets are
        # *non-transitive*, because a loose declaration is compatible with everything.
        # Dims("x","y") is compatible with both Dims("x","y", ordered=True) and
        # Dims("y","x", ordered=True), which provably conflict with each other — a star
        # check anchored on the loose one would pass. (dtype widths and freq anchors
        # have the same shape; units alone is transitive, being an equivalence
        # relation.) Candidates are producer-first, so combinations() still leads with
        # "output of ...".
        for (a_decl, a_src), (b_decl, b_src) in combinations(candidates, 2):
            findings.extend(
                f"  {name!r}: {a_src} and {b_src} conflict on {conflict}"
                for conflict in declaration_conflicts(a_decl, b_decl)
            )
    if findings:
        raise CatenaValueError(
            "contract declaration mismatch(es) in DAG:\n" + "\n".join(findings)
        )


def check_input_contracts(dr: driver.Driver, inputs: dict[str, Any]) -> None:
    """Validate loaded inputs' metadata against the contracts declared for them.

    The runtime leg that cannot be done statically, run for every facet: an input's
    ``units`` attribute (units), its dims / coords / dtype (schema), and the inferred
    frequency of its time axis (temporal), are checked against the contract declared
    by its consumer(s). Dims/coords/dtype live in the file header and a frequency
    needs only the 1-D datetime coordinate, so — like units — this executes no node
    and is suitable as a ``run --dry-run`` pre-flight. Units are propagated backward
    through unit-preserving passthrough edges to a fixpoint. A declared input that is
    not a ``DataArray`` fails unless its hint allows the value, as ``| None`` allows
    ``None``.

    Every failing input is reported in one `CatenaValueError`, with every failing
    facet of a ``DataArray``. A malformed declaration raises `CatenaValueError` too.
    This is a no-op when `xarray-annotated` is switched off.
    """
    if not resolve_enabled():
        return
    _, consumed, passthrough_edges = _collect_declarations(dr)
    expected_units = {
        name: _distinct(decl.unit for decl, _ in consumers)
        for name, consumers in consumed.items()
    }
    _propagate_units_backward(expected_units, passthrough_edges)
    findings: list[str] = []
    for name, value in inputs.items():
        decls = [decl for decl, _ in consumed.get(name, ())]
        # A unit-only declaration has no `others`, so it would refuse a `| None`.
        if isinstance(value, xr.DataArray):
            units = sorted(expected_units.get(name, []), key=lambda u: u.unit)
            decls += [Declared(unit=unit) for unit in units]
        try:
            found = [v for d in decls for v in declaration_violations(value, d, name)]
        except ValueError as exc:
            raise CatenaValueError(f"malformed contract declaration: {exc}") from exc
        # By message, as `Declared` equality ignores `others`: `| None` on one consumer
        # does not excuse a None for another.
        findings.extend(f"  {violation}" for violation in dict.fromkeys(found))
    if findings:
        raise CatenaValueError("input contract mismatch(es):\n" + "\n".join(findings))
