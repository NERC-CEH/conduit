"""Before-compute validation of the file<->node wiring.

The contract check (`conduit.dag.contract_check`) proves the *declared* contracts
are consistent; this proves the *wiring* is complete. It compares the external
inputs the built DAG requires (to produce the requested ``final_vars``) against the
inputs actually loaded from the config, and reports the two failure modes that
otherwise only surface part way through a run:

- **unbound** — a node requires an external input that nothing loaded (an error:
  the run cannot proceed);
- **unused** — a loaded input that no node consumes (a warning: usually a
  suffix/alias typo, e.g. loading ``temperature_daily`` for a node that wants
  ``temperature_weekly``).

This is the wiring analogue of the dry-run contract check, and — like it — needs no
compute: it reads the graph structure only.
"""

import warnings
from typing import TYPE_CHECKING, Any

from hamilton import graph_types

if TYPE_CHECKING:
    from hamilton import driver


class WiringWarning(UserWarning):
    """Warning that a loaded input is not consumed by any node."""


def _required_external_inputs(
    dr: "driver.Driver", final_vars: list[str]
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
    dr: "driver.Driver",
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
        The node names to be computed (as from `conduit.io.get_final_vars`).
    inputs
        The loaded input dict (as from `conduit.io.load_inputs`).
    exempt
        Loaded input names to exclude from the *unused* check — auto-derived
        inputs (date indices, lat/lon) that ``load_inputs`` always emits but no
        node is required to consume. See `conduit.io.auxiliary_input_names`.

    Raises
    ------
    ValueError
        If a required external input has no loaded value (unbound).

    Warns
    -----
    WiringWarning
        If a loaded input is consumed by no node (unused).
    """
    required_external, all_external = _required_external_inputs(dr, final_vars)
    loaded = set(inputs)

    unbound = required_external - loaded
    if unbound:
        raise ValueError(
            f"unbound pipeline input(s): {sorted(unbound)}. These are required by "
            f"the DAG but no input was loaded for them. Check for a naming mismatch "
            f"between [inputs.*] vars/suffix and the consuming function's parameter "
            f"names."
        )

    unused = loaded - all_external - set(exempt)
    if unused:
        warnings.warn(
            f"loaded input(s) consumed by no node: {sorted(unused)}. They will be "
            f"ignored — check for a suffix/alias mismatch if this is unexpected.",
            WiringWarning,
            stacklevel=2,
        )
