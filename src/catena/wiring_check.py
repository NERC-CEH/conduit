"""Before-compute validation of the file<->node wiring.

The contract check (`catena.contract_check`) covers the *declared* contracts;
this covers the *wiring*. It compares the external inputs the built DAG requires (to
produce the requested ``final_vars``) against the inputs actually loaded from the
config, and reports the two failure modes that otherwise only surface part way
through a run:

- **unbound** — a node requires an external input that was neither loaded nor set
  in the config (an error: the run cannot proceed);
- **unused** — a loaded input that no node consumes (a warning: usually a
  suffix/alias typo, e.g. loading ``temperature_daily`` for a node that wants
  ``temperature_weekly``).

It reads the graph structure only, so it needs no compute.
"""

import warnings
from typing import Any

from hamilton import driver, graph_types

from .errors import CatenaValueError


class WiringWarning(UserWarning):
    """Warning that a loaded input is not consumed by any node."""


def _required_external_inputs(
    dr: driver.Driver, final_vars: list[str]
) -> tuple[set[str], set[str]]:
    """Return ``(required_external, all_external)`` names upstream of ``final_vars``.

    ``all_external`` is every external input reachable from ``final_vars``;
    ``required_external`` is the subset that appears as a *required* (non-optional)
    dependency of some upstream node, so an external input with a default value is
    not mistaken for a missing one.
    """
    upstream = dr.what_is_upstream_of(*final_vars)
    upstream_names = {v.name for v in upstream}
    all_external = {v.name for v in upstream if v.is_external_input}

    hg = graph_types.HamiltonGraph.from_graph(dr.graph)
    required: set[str] = set()
    for node in hg.nodes:
        if node.name in upstream_names:
            required |= set(node.required_dependencies)
    return all_external & required, all_external


def check_wiring(
    dr: driver.Driver,
    final_vars: list[str],
    inputs: dict[str, Any],
    *,
    exempt: "frozenset[str] | set[str]" = frozenset(),
) -> None:
    """Validate that loaded inputs satisfy (and match) the DAG's external inputs.

    Parameters
    ----------
    dr
        A built Hamilton driver.
    final_vars
        The node names to be computed (as from `catena.io.get_final_vars`).
    inputs
        The loaded input dict (as from `catena.io.load_inputs`).
    exempt
        Loaded input names to exclude from the *unused* check — auto-derived
        inputs (date indices, lat/lon) that ``load_inputs`` always emits but no
        node is required to consume. See `catena.io.auxiliary_input_names`.

    Raises
    ------
    ValueError
        If a required external input has no loaded or config value (unbound).

    Warns
    -----
    WiringWarning
        If a loaded input is consumed by no node (unused).
    """
    required_external, all_external = _required_external_inputs(dr, final_vars)
    loaded = set(inputs)

    unbound = required_external - loaded - set(dr.graph.config)
    if unbound:
        raise CatenaValueError(
            f"unbound pipeline input(s): {sorted(unbound)}. These are required by "
            f"the DAG but were neither loaded nor set in the config. Check for a "
            f"naming mismatch between [inputs.*] vars/suffix and the consuming "
            f"function's parameter names."
        )

    unused = loaded - all_external - set(exempt)
    if unused:
        warnings.warn(
            f"loaded input(s) consumed by no node: {sorted(unused)}. They will be "
            f"ignored — check for a suffix/alias mismatch if this is unexpected.",
            WiringWarning,
            stacklevel=2,
        )
