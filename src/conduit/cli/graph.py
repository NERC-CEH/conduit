"""Visualise a pipeline defined in a configuration file."""

import html
import importlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import xarray as xr
from hamilton import graph_types
from xarray_annotated import declarations_from_signature, unwrap_annotated

from ..config import load_config
from ..dag.driver import build_driver
from ..io import get_final_vars
from .graph_style import GraphvizSpec, load_graphviz_spec

if TYPE_CHECKING:
    import graphviz
    from hamilton.driver import Driver

app = typer.Typer(help="Visualise a pipeline defined in a configuration file.")

StyleFunction = Callable[..., tuple[dict, str | None, str | None]]

_FREQUENCIES = ("daily", "weekly", "monthly")


def _frequency(name: str) -> str | None:
    """Return the temporal frequency a node name carries, e.g. ``"weekly"``."""
    for freq in _FREQUENCIES:
        if name.endswith(f"_{freq}"):
            return freq
    return None


def make_style_function(spec: GraphvizSpec, output_vars: set[str]) -> StyleFunction:
    """Build the default ``custom_style_function`` for ``display_all_functions``.

    Nodes are filled by category (static input / daily / weekly / monthly), and
    nodes corresponding to requested outputs additionally get a thick coloured
    border so the pipeline's end products stand out.  Colours come from
    ``spec.palette``.  Units are *not* handled here (the style hook cannot set a
    node's label); they are injected later by :func:`relabel_with_units`.
    """
    palette = spec.palette

    def custom_style(
        *, node: graph_types.HamiltonNode, node_class: str
    ) -> tuple[dict, str | None, str | None]:
        # Signature-native unit declarations make some node types
        # ``Annotated[DataArray, "<unit>"]``; unwrap before comparing.
        node_type = unwrap_annotated(node.type)
        freq = _frequency(node.name) if node_type is xr.DataArray else None

        fill: str | None = None
        legend: str | None = None
        if node.tags.get("module") == "conduit.inputs.static":
            fill, legend = palette["static"], "static input"
        elif freq is not None:
            fill, legend = palette[freq], freq

        style: dict = {}
        if fill is not None:
            style["fillcolor"] = fill

        if node.name in output_vars:
            style["color"] = palette["output"]
            style["penwidth"] = "2.5"
            return style, node_class, "output"

        return style, node_class, legend

    return custom_style


def _import_style_function(path: str) -> StyleFunction:
    """Import a ``"module:function"`` style function reference."""
    module_name, _, attr = path.partition(":")
    if not module_name or not attr:
        raise ValueError(
            f"style_function must be of the form 'module:function', got {path!r}."
        )
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _node_maps(dr: "Driver") -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(name -> unit, name -> frequency)`` maps for the DAG's nodes.

    Units are read off node *signatures* via
    :func:`xarray_annotated.declarations_from_signature` — the same single source
    the unit checks use — because ``@extract_fields`` model outputs (e.g.
    ``gpp_weekly``) carry a bare ``DataArray`` node type whose unit lives in the
    parent ``TypedDict``.  A node's *produced* unit (a declared output) takes
    precedence over a *consumed* one (an input parameter unit), so pure input nodes
    are also covered.  The frequency map covers ``DataArray`` nodes whose name
    carries a frequency suffix.
    """
    hg = graph_types.HamiltonGraph.from_graph(dr.graph)

    produced: dict[str, str] = {}
    consumed: dict[str, str] = {}
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
                    produced[name] = decl.unit.unit
            for name, decl in ins.items():
                if decl.unit is not None:
                    consumed.setdefault(name, decl.unit.unit)
    unit_map = {**consumed, **produced}

    freq_map: dict[str, str] = {}
    for var in dr.list_available_variables():
        freq = _frequency(var.name)
        if freq is not None and unwrap_annotated(var.type) is xr.DataArray:
            freq_map[var.name] = freq
    return unit_map, freq_map


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
    digraph: "graphviz.Digraph", freq_map: dict[str, str], palette: dict[str, str]
) -> None:
    """Colour each edge in-place by the frequency of its source node."""
    for i, line in enumerate(digraph.body):
        if " -> " not in line:
            continue
        src = line.split(" -> ", 1)[0].strip().strip('"')
        freq = freq_map.get(src)
        if freq is None:
            continue
        color = palette[freq]
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
    """Extend ``freq_map`` to unsuffixed nodes by neighbour consensus.

    Only ``DataArray`` nodes carry a ``_daily``/``_weekly``/``_monthly`` suffix,
    so multi-output model nodes, suffix-less derive outputs and the input tables
    start out without a frequency — yet they sit *between* same-frequency nodes
    and, left ungrouped,
    would straddle the cluster boundaries and break the left-to-right flow.

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
    digraph: "graphviz.Digraph", freq_map: dict[str, str], palette: dict[str, str]
) -> None:
    """Box nodes into ``daily``/``weekly``/``monthly`` subgraph clusters in-place.

    Graphviz draws a labelled, coloured boundary around each ``subgraph
    cluster_*`` and tries to lay its members out together, giving the frequency
    bands a clear spatial grouping on top of the existing colour coding.  Nodes
    whose frequency is unknown (config params, static inputs) are left
    ungrouped; pass a ``freq_map`` widened by :func:`infer_frequencies` so the
    model-bundle nodes that sit between same-frequency nodes are enclosed too.
    Input tables (``_<fn>_inputs``) join the cluster of the node they feed.

    The rebuilt body lists every node definition (clustered or not) *before* any
    edge, so an edge never implicitly creates one of its endpoints at the top
    level before the cluster claims it — the usual Graphviz clustering pitfall.
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

    groups: dict[str, list[str]] = {freq: [] for freq in _FREQUENCIES}
    ungrouped: list[str] = []
    for node_id, line in node_defs.items():
        freq = freq_map.get(node_id)
        if freq is None and node_id in input_target:
            freq = freq_map.get(input_target[node_id])
        if freq in groups:
            groups[freq].append(line)
        else:
            ungrouped.append(line)

    new_body: list[str] = list(other)
    for freq in _FREQUENCIES:
        lines = groups[freq]
        if not lines:
            continue
        new_body.append(f"\tsubgraph cluster_{freq} {{\n")
        new_body.append(
            f"\t\tgraph [label={freq} labeljust=l style=dashed "
            f'color="{palette[freq]}" fontname=Helvetica penwidth=2]\n'
        )
        new_body.extend(lines)
        new_body.append("\t}\n")
    new_body.extend(ungrouped)
    new_body.extend(edges)
    new_body.extend(legend)
    digraph.body[:] = new_body


@app.command()
def graph(
    config_file: Annotated[
        Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)
    ],
    output: Annotated[
        str, typer.Option("-o", "--output", help="Name of output file")
    ] = "pipeline",
    style: Annotated[
        Path | None,
        typer.Option(
            "-s",
            "--style",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Optional TOML file customising the DAG styling.",
        ),
    ] = None,
    allow_overrides: Annotated[
        bool,
        typer.Option(
            "--allow-overrides",
            help="Allow later modules to override earlier ones.",
        ),
    ] = False,
    png: Annotated[bool, typer.Option(help="Convert to PNG format")] = False,
    pdf: Annotated[bool, typer.Option(help="Convert to PDF format")] = False,
) -> None:
    """Visualise a pipeline defined in a configuration file.

    Each node shows its declared unit; requested outputs are highlighted and
    edges are coloured by temporal frequency.  Pass ``--style`` to override the
    default styling (see ``conduit.cli.graph_style``).

    Attention
    ---------
    This requires graphviz to be installed.
    """
    parsed = load_config(config_file)
    spec = load_graphviz_spec(style)

    if spec.style_function is not None:
        style_function = _import_style_function(spec.style_function)
    else:
        output_vars = set(get_final_vars(parsed.output_specs))
        style_function = make_style_function(spec, output_vars)

    dr = build_driver(
        modules=parsed.modules,
        config=parsed.driver_config,
        allow_module_overrides=allow_overrides,
    )

    # Render without an output path so the graphviz object is returned for
    # post-processing rather than written straight to disk.
    digraph = dr.display_all_functions(
        graphviz_kwargs=spec.graphviz_kwargs,
        custom_style_function=style_function,
        show_legend=spec.show_legend,
    )
    if digraph is None:
        raise RuntimeError(
            "Failed to build the graph visualisation; is graphviz installed?"
        )

    unit_map, freq_map = _node_maps(dr)
    freq_map = infer_frequencies(digraph, freq_map)
    relabel_with_units(digraph, unit_map)
    color_edges_by_frequency(digraph, freq_map, spec.palette)
    if spec.cluster_by_frequency:
        cluster_nodes_by_frequency(digraph, freq_map, spec.palette)

    output_path = Path(output).with_suffix(".dot")
    output_path.write_text(digraph.source)

    # TODO: is there a better way than this?
    if png:
        subprocess.run(
            [
                "dot",
                "-Tpng",
                str(output_path),
                "-o",
                str(output_path.with_suffix(".png")),
            ]
        )
    if pdf:
        subprocess.run(
            [
                "dot",
                "-Tpdf",
                str(output_path),
                "-o",
                str(output_path.with_suffix(".pdf")),
            ]
        )
