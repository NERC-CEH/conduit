r"""Build-time (static) unit-consistency check for the Hamilton DAG.

The runtime check (``declare_units`` \u2192 ``check_units``) only fires when a node
executes. `check_dag_units` adds the complementary guarantee at *build*
time: every internal edge whose producer and consumer both declare a unit is
verified for consistency, so a mismatch surfaces as soon as the driver is built
rather than part way through a run.

Declarations are read from each node's public function signature via
`xarray_annotated.units.units_from_signature` \u2014 the same single source the
runtime check uses. Hamilton unifies nodes by name, so a node name that is both
*produced* with a declared unit (a ``TypedDict`` field or bare ``Annotated``
return) and *consumed* with a declared unit (an ``Annotated`` parameter) is a
genuine edge in the built graph; no edge walking is required.

**Limitation.** Edges routed through resample/node modules, or fed by external
files, have no statically declared producer unit (resample preserves the source
``units`` attribute at runtime; node modules are generated; file inputs are
validated against the file's own ``units``). Those edges are not checked here and
fall back to the runtime check.

The complementary `check_input_units` performs the *runtime* leg of that
fallback for **external file inputs**: it validates the ``units`` attribute of the
actually-loaded input ``DataArray``\\ s against the units declared by the nodes that
consume them. This is the only data-dependent part of unit validation (every
internal edge's unit is fixed by declarations/stamping), so it can run without
executing any node \u2014 the basis of ``conduit run --dry-run``. Inputs routed through
a unit-preserving ``resample`` node before reaching a declaring consumer are covered
via backward propagation; inputs routed through a ``[[node]]`` module are *not*,
since a node can transform units arbitrarily and would have to actually run.
"""

from typing import TYPE_CHECKING

import xarray as xr
from hamilton import graph_types
from xarray_annotated.units import check_units, get_policy, units_from_signature
from xarray_annotated.units._check import units_compatible, units_equal

if TYPE_CHECKING:
    from typing import Any

    from hamilton import driver


def _collect_unit_maps(
    dr: "driver.Driver",
) -> tuple[
    dict[str, tuple[str, str]], dict[str, list[tuple[str, str]]], dict[str, str]
]:
    """Read declared units off the built DAG's node signatures.

    Returns three maps, the shared source for both the build-time
    (`check_dag_units`) and runtime (`check_input_units`) checks:

    - ``produced``: node name -> ``(declared_unit, producer_label)``;
    - ``consumed``: node name -> ``[(declared_unit, consumer_label), ...]``;
    - ``resample_edges``: resample target name -> its single source name (resampling
      is unit-preserving, so target and source share a unit).
    """
    hg = graph_types.HamiltonGraph.from_graph(dr.graph)

    seen: set[int] = set()
    funcs = []
    for node in hg.nodes:
        for fn in node.originating_functions or ():
            if id(fn) not in seen:
                seen.add(id(fn))
                funcs.append(fn)

    produced: dict[str, tuple[str, str]] = {}
    consumed: dict[str, list[tuple[str, str]]] = {}

    for fn in funcs:
        fn_name = getattr(fn, "__name__", repr(fn))
        in_units, out_units = units_from_signature(fn)
        if isinstance(out_units, dict):
            for name, unit in out_units.items():
                produced[name] = (unit, fn_name)
        elif isinstance(out_units, str):
            produced[fn_name] = (out_units, fn_name)
        for name, unit in in_units.items():
            consumed.setdefault(name, []).append((unit, fn_name))

    resample_edges = {
        node.name: next(iter(node.required_dependencies))
        for node in hg.nodes
        if node.tags.get("module") == "conduit.dag.resample"
        and len(node.required_dependencies) == 1
    }

    return produced, consumed, resample_edges


def check_dag_units(
    dr: "driver.Driver",
    *,
    on_inexact: str | None = None,
) -> None:
    """Verify declared units are consistent across the built DAG's edges.

    For every node name that is both produced and consumed with a declared unit
    (and for external inputs shared by multiple consumers), the declared units
    are compared:

    - dimensionally **incompatible** units (e.g. a mass where a pressure is
      declared) are always reported;
    - dimensionally compatible but **non-identical** strings (e.g. ``"Pa"`` vs
      ``"hPa"``) are reported only when ``on_inexact`` resolves to ``"error"``.

    DAG-level unit mismatches always raise `ValueError` (they represent
    genuine pipeline definition errors). Skips when
    `xarray_annotated.units.get_policy().enabled` is ``False``.

    ``on_inexact`` defaults from the active policy when ``None``.
    """
    pol = get_policy()
    if not pol.enabled:
        return
    if on_inexact is None:
        on_inexact = pol.on_inexact

    produced, consumed, resample_edges = _collect_unit_maps(dr)

    changed = True
    while changed:
        changed = False
        for target, source in resample_edges.items():
            if target not in produced and source in produced:
                produced[target] = (produced[source][0], f"resample of {source}")
                changed = True

    findings: list[str] = []
    for name, consumers in consumed.items():
        candidates: list[tuple[str, str]] = []
        if name in produced:
            unit, who = produced[name]
            candidates.append((unit, f"output of {who}"))
        candidates.extend((unit, f"input of {who}") for unit, who in consumers)
        if len(candidates) < 2:
            continue

        base_unit, base_src = candidates[0]
        for unit, src in candidates[1:]:
            if not units_compatible(base_unit, unit):
                findings.append(
                    f"  {name!r}: {base_src} declares {base_unit!r} but {src} "
                    f"declares {unit!r} (dimensionally incompatible)"
                )
            elif on_inexact == "error" and not units_equal(base_unit, unit):
                findings.append(
                    f"  {name!r}: {base_src} declares {base_unit!r} but {src} "
                    f"declares {unit!r} (units differ; exact match required)"
                )

    if not findings:
        return
    raise ValueError("unit declaration mismatch(es) in DAG:\n" + "\n".join(findings))


def check_input_units(
    dr: "driver.Driver",
    inputs: "dict[str, Any]",
) -> None:
    """Validate loaded input data's ``units`` against the units declared for them.

    This is the *runtime* leg of unit validation that cannot be done statically: it
    reads the ``units`` attribute of each actually-loaded input ``DataArray`` and
    checks it against the unit declared by the node(s) that consume it, via
    `check_units` which follows the active `Policy`. No node is executed, which
    makes this suitable as a ``run --dry-run`` pre-flight.

    An input that feeds a unit-preserving ``resample`` node before reaching a
    declaring consumer is validated against that consumer's unit (the declared unit
    is propagated *backward* through resample edges to a fixpoint). An input routed
    through a ``[[node]]`` module first is *not* validated here \u2014 a node can
    transform units arbitrarily, so its consumer's declared unit says nothing
    about the raw input and only a real run could check it.
    """
    pol = get_policy()
    if not pol.enabled:
        return

    _, consumed, resample_edges = _collect_unit_maps(dr)

    expected: dict[str, set[str]] = {}
    for name, consumers in consumed.items():
        expected.setdefault(name, set()).update(unit for unit, _ in consumers)

    changed = True
    while changed:
        changed = False
        for target, source in resample_edges.items():
            if target in expected:
                before = len(expected.get(source, set()))
                expected.setdefault(source, set()).update(expected[target])
                if len(expected[source]) != before:
                    changed = True

    for name, value in inputs.items():
        declared_units = expected.get(name)
        if not declared_units or not isinstance(value, xr.DataArray):
            continue
        for declared in sorted(declared_units):
            check_units(value, declared, name)
