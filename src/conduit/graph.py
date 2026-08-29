"""Build a styled Graphviz visualisation of a configured pipeline.

`build_graph` returns a ``graphviz.Digraph``, which renders inline in a notebook.
Write it with ``digraph.source`` or render it with ``digraph.pipe(format=...)``.

**Everything shown is read off the built DAG's contracts.**
Section labels in a config are inert, so node fills, edge colours and the
frequency clusters all come from declared `xarray_annotated.temporal.Freq`
contracts via `_node_maps`, and node labels carry each node's declared unit in
place of the near-universal ``DataArray`` type text. A pipeline whose resample
targets are called ``raw``/``smoothed`` is therefore grouped exactly as well as
one using ``daily``/``weekly``.

Styling defaults live in `conduit.graph_style`; a ``--style`` TOML file is
deep-merged over them, and may name its own ``style_function`` to replace the
built-in one entirely.
"""

import html
import importlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from hamilton import graph_types
from hamilton.driver import Driver
from xarray_annotated import declarations_from_signature

from .build import build_driver
from .errors import ConduitValueError
from .graph_style import FREQ_COLOR_CYCLE, GraphvizSpec, load_graphviz_spec
from .io import get_final_vars
from .pipeline import ConfigSource, prepare_config

if TYPE_CHECKING:
    # graphviz ships in the optional `viz` extra, and `conduit.build_graph` is
    # re-exported from the package root, so importing it here would make
    # `import conduit` fail for anyone who did not install that extra.
    import graphviz

__all__ = ["build_graph"]

StyleFunction = Callable[..., tuple[dict, str | None, str | None]]


def make_style_function(
    spec: GraphvizSpec,
    output_vars: set[str],
    freq_map: dict[str, str],
    freq_colors: dict[str, str],
) -> StyleFunction:
    """Build the default ``custom_style_function`` for ``display_all_functions``.

    Nodes are filled by their **declared frequency** (``freq_map``, read off the DAG's
    contracts — not guessed from name suffixes), and nodes corresponding to requested
    outputs additionally get a thick coloured border so the pipeline's end products
    stand out.  Units are *not* handled here (the style hook cannot set a node's
    label); they are injected later by :func:`relabel_with_units`.
    """
    palette = spec.palette

    def custom_style(
        *, node: graph_types.HamiltonNode, node_class: str
    ) -> tuple[dict, str | None, str | None]:
        freq = freq_map.get(node.name)

        style: dict = {}
        if freq is not None:
            style["fillcolor"] = freq_colors[freq]

        if node.name in output_vars:
            style["color"] = palette["output"]
            style["penwidth"] = "2.5"
            return style, node_class, "output"

        return style, node_class, freq

    return custom_style


def _import_style_function(path: str) -> StyleFunction:
    """Import a ``"module:function"`` style function reference."""
    module_name, _, attr = path.partition(":")
    if not module_name or not attr:
        raise ConduitValueError(
            f"style_function must be of the form 'module:function', got {path!r}."
        )
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _node_maps(dr: Driver) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(name -> unit, name -> frequency)`` maps for the DAG's nodes.

    Both are read off node *signatures* via
    :func:`xarray_annotated.declarations_from_signature` — the same single source the
    contract checks use — because ``@extract_fields`` model outputs (e.g.
    ``gpp_weekly``) carry a bare ``DataArray`` node type whose declaration lives in
    the parent ``TypedDict``.  A node's *produced* declaration takes precedence over a
    *consumed* one (an input parameter's), so pure input nodes are covered too.

    The frequency map comes from **declared** `xarray_annotated.temporal.Freq`
    contracts (``"7D"``, ``"1ME"``), not from name suffixes. Section labels are inert
    (`conduit.io.load_inputs`), so a pipeline whose resample targets are called
    ``raw``/``smoothed`` is grouped exactly as well as one using ``daily``/``weekly``
    — the information now lives in the DAG, so read it from there.
    """
    hg = graph_types.HamiltonGraph.from_graph(dr.graph)

    produced_units: dict[str, str] = {}
    consumed_units: dict[str, str] = {}
    produced_freq: dict[str, str] = {}
    consumed_freq: dict[str, str] = {}
    seen: set[int] = set()
    for node in hg.nodes:
        for fn in node.originating_functions or ():
            if id(fn) in seen:
                continue
            seen.add(id(fn))
            ins, out = declarations_from_signature(fn)
            fn_name = getattr(fn, "__name__", "")
            outs = out if isinstance(out, dict) else {fn_name: out} if out else {}
            for name, decl in outs.items():
                if decl.unit is not None:
                    produced_units[name] = decl.unit.unit
                if decl.freq is not None:
                    produced_freq[name] = decl.freq.freq
            for name, decl in ins.items():
                if decl.unit is not None:
                    consumed_units.setdefault(name, decl.unit.unit)
                if decl.freq is not None:
                    consumed_freq.setdefault(name, decl.freq.freq)

    return (
        {**consumed_units, **produced_units},
        {**consumed_freq, **produced_freq},
    )


def assign_freq_colors(
    freq_map: dict[str, str], palette: dict[str, str]
) -> dict[str, str]:
    """Map each distinct declared frequency to a colour.

    Frequencies are arbitrary offset aliases, not a fixed vocabulary, so colours are
    drawn from a qualitative **cycle** in first-seen order rather than looked up in a
    fixed ``daily``/``weekly``/``monthly`` table. A ``[palette]`` entry naming a
    frequency (``"7D" = "#ff7f00"``) pins that one, for users who want stable colours
    across renders.
    """
    colors: dict[str, str] = {}
    taken = 0
    for freq in dict.fromkeys(freq_map.values()):  # distinct, first-seen order
        if freq in palette:
            colors[freq] = palette[freq]
        else:
            colors[freq] = FREQ_COLOR_CYCLE[taken % len(FREQ_COLOR_CYCLE)]
            taken += 1
    return colors


# A single ``<td>name</td><td>DataArray</td>`` cell pair inside an input table.
_INPUT_ROW_RE = re.compile(r"<td>(?P<name>[^<]+)</td><td>DataArray</td>")


def relabel_with_units(digraph: "graphviz.Digraph", unit_map: dict[str, str]) -> None:
    """Rewrite node labels in-place so the unit replaces the ``DataArray`` type.

    Hamilton renders every function node's label as ``name`` over the type string
    ``DataArray`` (it strips the ``Annotated`` wrapper), and groups inputs into
    tables of ``name``/``DataArray`` rows.  Since virtually every node is a
    ``DataArray``, that type text is noise; here we swap it for the declared unit
    in both places.  Nodes with no declared unit keep their original
    (informative) type.
    """

    def _row(match: "re.Match[str]") -> str:
        unit = unit_map.get(match.group("name"))
        if unit is None:
            return match.group(0)
        return f"<td>{match.group('name')}</td><td>{html.escape(unit)}</td>"

    for i, line in enumerate(digraph.body):
        if "[label=<" not in line:
            continue
        name = line.split("[label=", 1)[0].strip().strip('"')
        unit = unit_map.get(name)
        if unit:
            line = line.replace("<i>DataArray</i>", f"<i>{html.escape(unit)}</i>", 1)
        if "<table" in line:
            line = _INPUT_ROW_RE.sub(_row, line)
        digraph.body[i] = line


def color_edges_by_frequency(
    digraph: "graphviz.Digraph", freq_map: dict[str, str], freq_colors: dict[str, str]
) -> None:
    """Colour each edge in-place by the declared frequency of its source node."""
    for i, line in enumerate(digraph.body):
        if " -> " not in line:
            continue
        src = line.split(" -> ", 1)[0].strip().strip('"')
        freq = freq_map.get(src)
        if freq is None:
            continue
        color = freq_colors[freq]
        if "[" in line:
            digraph.body[i] = line.replace("[", f'[color="{color}" ', 1)
        else:
            digraph.body[i] = line.rstrip("\n") + f' [color="{color}"]\n'


def _edges(digraph: "graphviz.Digraph") -> list[tuple[str, str]]:
    """Return ``(source, target)`` id pairs for every edge in the digraph body."""
    pairs: list[tuple[str, str]] = []
    for line in digraph.body:
        if " -> " not in line:
            continue
        src, _, dst = line.strip().partition(" -> ")
        src = src.strip().strip('"')
        dst = dst.split(None, 1)[0].strip().strip('"')
        pairs.append((src, dst))
    return pairs


def infer_frequencies(
    digraph: "graphviz.Digraph", freq_map: dict[str, str]
) -> dict[str, str]:
    """Extend ``freq_map`` to undeclared nodes by neighbour consensus.

    Only nodes that *declare* a `Freq` contract start out with a frequency, so
    multi-output model nodes, undeclared derived outputs and the input tables have
    none — yet they sit *between* same-frequency nodes and, left ungrouped, would
    straddle the cluster boundaries and break the left-to-right flow.

    Here a node inherits a frequency when *every* one of its already-resolved
    neighbours (predecessors and successors) agrees on a single one, iterated to
    a fixpoint.  A node bridging two frequencies has conflicting neighbours and
    stays unresolved, so a frequency never spreads across a genuine boundary.
    The returned map is a superset of ``freq_map`` (the input is not mutated).
    """
    preds: dict[str, set[str]] = {}
    succs: dict[str, set[str]] = {}
    for src, dst in _edges(digraph):
        succs.setdefault(src, set()).add(dst)
        preds.setdefault(dst, set()).add(src)

    freq = dict(freq_map)
    changed = True
    while changed:
        changed = False
        for node in set(preds) | set(succs):
            if node in freq:
                continue
            neighbours = preds.get(node, set()) | succs.get(node, set())
            resolved = {freq[m] for m in neighbours if m in freq}
            if len(resolved) == 1:
                freq[node] = next(iter(resolved))
                changed = True
    return freq


def cluster_nodes_by_frequency(
    digraph: "graphviz.Digraph", freq_map: dict[str, str], freq_colors: dict[str, str]
) -> None:
    """Box nodes into one subgraph cluster per declared frequency, in-place.

    Graphviz draws a labelled, coloured boundary around each ``subgraph cluster_*``
    and tries to lay its members out together, giving the frequency bands a clear
    spatial grouping on top of the existing colour coding.  The clusters are the
    frequencies actually declared in this DAG (``freq_colors``' keys), in first-seen
    order — there is no fixed vocabulary.  Nodes whose frequency is unknown (config
    params, static inputs) are left ungrouped; pass a ``freq_map`` widened by
    :func:`infer_frequencies` so the model-bundle nodes that sit between
    same-frequency nodes are enclosed too.  Input tables (``_<fn>_inputs``) join the
    cluster of the node they feed.

    """
    legend: list[str] = []
    rest: list[str] = []
    in_legend = False
    for line in digraph.body:
        if "subgraph cluster__legend" in line:
            in_legend = True
        if in_legend:
            legend.append(line)
            if line.strip() == "}":
                in_legend = False
            continue
        rest.append(line)

    node_defs: dict[str, str] = {}
    edges: list[str] = []
    other: list[str] = []
    for line in rest:
        if " -> " in line:
            edges.append(line)
        elif "[label=" in line:
            node_id = line.split("[label=", 1)[0].strip().strip('"')
            node_defs[node_id] = line
        else:
            other.append(line)

    # Map each input table to the node it feeds so it can share its cluster.
    input_target: dict[str, str] = {}
    for line in edges:
        src, _, dst = line.strip().partition(" -> ")
        src = src.strip().strip('"')
        dst = dst.split(None, 1)[0].strip().strip('"')
        if src.startswith("_") and src.endswith("_inputs"):
            input_target[src] = dst

    groups: dict[str, list[str]] = {freq: [] for freq in freq_colors}
    ungrouped: list[str] = []
    for node_id, line in node_defs.items():
        freq = freq_map.get(node_id)
        if freq is None and node_id in input_target:
            freq = freq_map.get(input_target[node_id])
        if freq in groups:
            groups[freq].append(line)
        else:
            ungrouped.append(line)

    # Every node definition (clustered or not) must precede every edge: an edge
    # naming a node not yet defined implicitly creates it at the top level, before
    # the cluster can claim it. That is the usual Graphviz clustering pitfall, and
    # it is why ``edges`` is appended only once all groups have been emitted.
    new_body: list[str] = list(other)
    for freq, lines in groups.items():
        if not lines:
            continue
        # An offset alias may contain characters Graphviz will not accept in a bare
        # ID (``W-SUN``), so the cluster id is sanitised and the label quoted.
        cluster_id = re.sub(r"\W", "_", freq)
        new_body.append(f"\tsubgraph cluster_{cluster_id} {{\n")
        new_body.append(
            f'\t\tgraph [label="{freq}" labeljust=l style=dashed '
            f'color="{freq_colors[freq]}" fontname=Helvetica penwidth=2]\n'
        )
        new_body.extend(lines)
        new_body.append("\t}\n")
    new_body.extend(ungrouped)
    new_body.extend(edges)
    new_body.extend(legend)
    digraph.body[:] = new_body


def build_graph(
    config: ConfigSource,
    *,
    style: str | Path | None = None,
    allow_overrides: bool = False,
) -> "graphviz.Digraph":
    """Build a styled visualisation of the DAG a config describes.

    Each node shows its declared unit, requested outputs are highlighted, and
    edges are coloured (and optionally clustered) by declared temporal frequency.

    Parameters
    ----------
    config
        Path to a TOML config file, or a `ParsedConfig` to visualise directly.
    style
        Optional TOML file overriding the default styling. See
        `conduit.graph_style`.
    allow_overrides
        Allow a later module to override a node defined by an earlier one.

    Returns
    -------
    graphviz.Digraph
        The styled graph. Write it with ``digraph.source`` (DOT) or render it
        with ``digraph.pipe(format=...)``.

    Attention
    ---------
    This requires the ``viz`` extra (``pip install conduit[viz]``).
    """
    parsed, _ = prepare_config(config)
    spec = load_graphviz_spec(Path(style) if style is not None else None)

    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        node_specs=parsed.node_specs,
        allow_module_overrides=allow_overrides,
        base=parsed.base,
    )

    # The contracts must be read off the built DAG before styling: the node fills are
    # driven by each node's *declared* frequency, not by its name.
    unit_map, freq_map = _node_maps(dr)
    freq_colors = assign_freq_colors(freq_map, spec.palette)

    if spec.style_function is not None:
        style_function = _import_style_function(spec.style_function)
    else:
        output_vars = set(get_final_vars(parsed.output_specs))
        style_function = make_style_function(spec, output_vars, freq_map, freq_colors)

    # Render without an output path so the graphviz object is returned for
    # post-processing rather than written straight to disk.
    digraph = dr.display_all_functions(
        graphviz_kwargs=spec.graphviz_kwargs,
        custom_style_function=style_function,
        show_legend=spec.show_legend,
    )
    if digraph is None:
        raise ConduitValueError(
            "Failed to build the graph visualisation. Is graphviz installed? "
            "Install the visualisation extra with `pip install conduit[viz]`."
        )

    freq_map = infer_frequencies(digraph, freq_map)
    relabel_with_units(digraph, unit_map)
    color_edges_by_frequency(digraph, freq_map, freq_colors)
    if spec.cluster_by_frequency:
        cluster_nodes_by_frequency(digraph, freq_map, freq_colors)

    return digraph
