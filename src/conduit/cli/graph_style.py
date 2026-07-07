"""Styling configuration for the ``conduit graph`` DAG visualisation.

The canonical default styling lives in :class:`GraphvizSpec`, a typed dataclass
that is the single source of truth.  Users may supply an optional TOML file via
``conduit graph --style <file>`` whose keys are deep-merged over these defaults,
so one style can be reused across many science configs without duplicating it.

Recognised top-level keys in a ``--style`` file::

    style_function = "my_pkg.styling:my_style"   # import path "module:function"
    show_legend = true
    cluster_by_frequency = true                  # box nodes by daily/weekly/monthly

    [palette]                                    # override any category colour
    daily = "#ff7f00"

    [graph_attr]                                 # graphviz graph attributes
    rankdir = "TB"

    [node_attr]                                  # graphviz node attributes
    fontname = "Courier"

    [edge_attr]                                  # graphviz edge attributes
    color = "#444444"
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ColorBrewer "Set2": a colour-blind-friendly qualitative palette. These work
# both as node fill colours (with black text) and as edge colours.
DEFAULT_PALETTE: dict[str, str] = {
    "static": "#66c2a5",  # static inputs
    "daily": "#fc8d62",  # daily-frequency nodes/edges
    "weekly": "#8da0cb",  # weekly-frequency nodes/edges
    "monthly": "#a6d854",  # monthly-frequency nodes/edges
    "output": "#e7298a",  # border highlight on requested output nodes
}

# Top-level keys accepted in a ``--style`` TOML file.
_GRAPHVIZ_ATTR_KEYS = ("graph_attr", "node_attr", "edge_attr")
_KNOWN_KEYS = frozenset(
    {
        "palette",
        "style_function",
        "show_legend",
        "cluster_by_frequency",
        *_GRAPHVIZ_ATTR_KEYS,
    }
)


@dataclass(frozen=True)
class GraphvizSpec:
    """Resolved styling for a single ``conduit graph`` invocation.

    Attributes
    ----------
    palette
        Category → hex-colour map (see :data:`DEFAULT_PALETTE`).
    style_function
        Optional ``"module:function"`` import path to a user-supplied Hamilton
        ``custom_style_function``.  When set, it replaces the built-in default.
    show_legend
        Whether to draw the legend.
    cluster_by_frequency
        Whether to box nodes into ``daily``/``weekly``/``monthly`` subgraph
        clusters (in addition to colouring them).
    graphviz_kwargs
        Kwargs forwarded to ``Driver.display_all_functions`` (``graph_attr``,
        ``node_attr``, ``edge_attr`` nested dicts).
    """

    palette: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    style_function: str | None = None
    show_legend: bool = True
    cluster_by_frequency: bool = True
    graphviz_kwargs: dict[str, Any] = field(default_factory=dict)


def load_graphviz_spec(path: Path | None) -> GraphvizSpec:
    """Load a styling spec from ``path``, falling back to the built-in defaults.

    When ``path`` is ``None`` the dataclass defaults are returned unchanged.
    Otherwise the TOML file is parsed and deep-merged over the defaults: the
    ``palette`` is updated key-by-key (so a file need only override the colours
    it cares about), and the graphviz attribute tables are collected into
    ``graphviz_kwargs``.  Unknown top-level keys raise ``ValueError``.
    """
    if path is None:
        return GraphvizSpec()

    with Path(path).open("rb") as file:
        data = tomllib.load(file)

    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        raise ValueError(
            f"Unknown key(s) in graphviz style file {path}: {sorted(unknown)}. "
            f"Recognised keys: {sorted(_KNOWN_KEYS)}."
        )

    palette = {**DEFAULT_PALETTE, **data.get("palette", {})}
    graphviz_kwargs = {k: data[k] for k in _GRAPHVIZ_ATTR_KEYS if k in data}

    return GraphvizSpec(
        palette=palette,
        style_function=data.get("style_function"),
        show_legend=data.get("show_legend", True),
        cluster_by_frequency=data.get("cluster_by_frequency", True),
        graphviz_kwargs=graphviz_kwargs,
    )
