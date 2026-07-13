"""Tests for the conduit CLI commands."""

import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import xarray as xr
from typer.testing import CliRunner

from conduit._version import __version__
from conduit.cli import app
from conduit.cli.graph import (
    _import_style_function,
    assign_freq_colors,
    cluster_nodes_by_frequency,
    color_edges_by_frequency,
    infer_frequencies,
    make_style_function,
    relabel_with_units,
)
from conduit.cli.graph_style import (
    DEFAULT_PALETTE,
    FREQ_COLOR_CYCLE,
    GraphvizSpec,
    load_graphviz_spec,
)
from conduit.config import load_config

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_toml(tmp_path, synthetic_data_dir):
    """Config TOML pointing to session-scoped synthetic NetCDF files."""
    content = f"""\
[[node]]
name = "mean_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"
units = "degC"
freq = "7D"

[grid]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p


@pytest.fixture
def inexact_units_module():
    """Register a module whose one DAG edge declares 'm' upstream and 'km' down.

    Compatible (both lengths) but *inexact*, so the build-time contract check
    flags it only when the units policy says ``on_inexact="error"`` — which is
    what ``[annotations] exact = true`` asks for. That makes it a probe for
    "did this command apply the config's policy?".
    """
    import sys
    import types
    from typing import Annotated

    name = "conduit_test_inexact_units"
    mod = types.ModuleType(name)

    def metres() -> Annotated[xr.DataArray, "m"]:
        return xr.DataArray([1.0])

    def consumer(metres: Annotated[xr.DataArray, "km"]) -> xr.DataArray:
        return metres

    for fn in (metres, consumer):
        fn.__module__ = name
        setattr(mod, fn.__name__, fn)
    sys.modules[name] = mod
    yield name
    del sys.modules[name]


@pytest.fixture
def inexact_units_config(tmp_path, inexact_units_module):
    p = tmp_path / "inexact.toml"
    p.write_text(
        f"""\
[annotations]
exact = true

[probe]
_import_path = "{inexact_units_module}"
"""
    )
    return p


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_exits_zero(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_shows_version_string(self):
        result = runner.invoke(app, ["version"])
        assert __version__ in result.output


class TestGriddedGeoExtraGuard:
    """`conduit gridded` fails fast with an install hint when `geo` is absent."""

    def test_missing_extra_exits_with_hint(self, monkeypatch):
        import importlib.util as importutil

        real = importutil.find_spec

        def fake_find_spec(name, *args, **kwargs):
            if name in ("rioxarray", "pyproj"):
                return None
            return real(name, *args, **kwargs)

        monkeypatch.setattr(importutil, "find_spec", fake_find_spec)

        result = runner.invoke(app, ["gridded", "merge", "tests/test_config.toml"])
        assert result.exit_code == 1
        assert "conduit[geo]" in result.output
        assert "rioxarray" in result.output


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_exits_zero(self, config_toml):
        result = runner.invoke(app, ["run", str(config_toml)])
        assert result.exit_code == 0, result.output

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["run", str(tmp_path / "nonexistent.toml")])
        assert result.exit_code != 0

    def test_run_without_outputs_prints_notice(self, tmp_path, synthetic_data_dir):
        # Previously exited 0 with no output and no message, which looked like a
        # successful run that had produced files somewhere.
        cfg = tmp_path / "no_outputs.toml"
        cfg.write_text(
            f"""\
[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
        )
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == 0, result.output
        assert "nothing to execute" in result.output


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


class TestPolicyAppliedByEveryCommand:
    """Every entry point applies the config's [annotations] policy before building.

    The build-time contract check consults the *process-global* policy, so a
    command that skipped `AnnotationPolicySpec.apply` would accept a config that
    `conduit run` rejects. These pin `run` and `graph` to the same verdict.
    """

    def _invoke(self, args):
        from xarray_annotated.units import policy

        # The test session disables contract checking globally (conftest); re-enable
        # it so the config's `exact = true` has something to tighten.
        with policy(enabled=True):
            return runner.invoke(app, args)

    def test_run_rejects_inexact_edge_under_exact_policy(self, inexact_units_config):
        result = self._invoke(["run", str(inexact_units_config)])
        assert result.exit_code != 0
        assert "exact match required" in str(result.exception)

    def test_graph_applies_config_policy(self, inexact_units_config, tmp_path):
        # Previously `graph` never applied the config policy, so it silently
        # accepted a DAG that `conduit run` rejected on the very same config.
        result = self._invoke(
            ["graph", str(inexact_units_config), "--output", str(tmp_path / "g")]
        )
        assert result.exit_code != 0
        assert "exact match required" in str(result.exception)


class TestGraphCommand:
    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_generates_dot_file(self, config_toml, tmp_path):
        out = tmp_path / "pipeline"
        result = runner.invoke(app, ["graph", str(config_toml), "--output", str(out)])
        assert result.exit_code == 0, result.output
        dot = out.with_suffix(".dot")
        assert dot.exists()
        text = dot.read_text()
        # Declared units appear in node labels in place of the "DataArray" type.
        assert "degC" in text  # the [[node]]'s declared output unit
        node_line = next(
            line
            for line in text.splitlines()
            if line.strip().startswith("mean_temperature_weekly ")
        )
        assert "<i>degC</i>" in node_line
        assert "DataArray" not in node_line

    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_style_file_pins_a_frequency_colour(self, config_toml, tmp_path):
        style = tmp_path / "style.toml"
        # The config's node declares freq = "7D"; pinning it overrides the cycle.
        style.write_text('[palette]\n"7D" = "#123456"\n')
        out = tmp_path / "pipeline"
        result = runner.invoke(
            app,
            ["graph", str(config_toml), "--output", str(out), "--style", str(style)],
        )
        assert result.exit_code == 0, result.output
        assert "#123456" in out.with_suffix(".dot").read_text()

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["graph", str(tmp_path / "no.toml")])
        assert result.exit_code != 0


class TestGraphRendering:
    """--png/--pdf render through the graphviz API, and failures are surfaced."""

    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_png_is_written(self, config_toml, tmp_path):
        out = tmp_path / "pipeline"
        result = runner.invoke(
            app, ["graph", str(config_toml), "--output", str(out), "--png"]
        )
        assert result.exit_code == 0, result.output
        png = out.with_suffix(".png")
        assert png.exists()
        assert png.read_bytes().startswith(b"\x89PNG")

    def test_graph_png_reports_missing_dot(self, config_toml, tmp_path, monkeypatch):
        # Previously subprocess.run(["dot", ...]) ran without check=True, so a
        # missing binary produced no output, no error and a zero exit code.
        import graphviz

        def boom(*args, **kwargs):
            raise graphviz.ExecutableNotFound(["dot"])

        monkeypatch.setattr(graphviz.Digraph, "pipe", boom)

        out = tmp_path / "pipeline"
        result = runner.invoke(
            app, ["graph", str(config_toml), "--output", str(out), "--png"]
        )
        assert result.exit_code != 0
        assert "graphviz" in result.output.lower()
        assert not out.with_suffix(".png").exists()


class TestGraphvizBodySurgery:
    """Canaries for the post-processing that rewrites Hamilton's rendered body.

    `relabel_with_units`, `color_edges_by_frequency` and `cluster_nodes_by_frequency`
    all pattern-match Hamilton's Graphviz output (`<i>DataArray</i>` in node labels,
    `a -> b` edge lines, `[label=` node definitions). If Hamilton changes how it
    renders, those patterns stop matching and every feature **silently degrades to a
    no-op** — the .dot file is still produced, just plain. These assert the surgery
    actually applied, so a rendering change fails loudly here instead.
    """

    @pytest.fixture
    def dot_source(self, config_toml, tmp_path):
        out = tmp_path / "pipeline"
        result = runner.invoke(app, ["graph", str(config_toml), "--output", str(out)])
        assert result.exit_code == 0, result.output
        return out.with_suffix(".dot").read_text()

    def test_dot_contains_declared_units(self, dot_source):
        # The declared unit replaced the DataArray type ...
        assert "<i>degC</i>" in dot_source
        # ... and no node with a declared unit still shows the type it replaced.
        for line in dot_source.splitlines():
            if line.strip().startswith("mean_temperature_weekly "):
                assert "DataArray" not in line

    def test_dot_contains_freq_clusters(self, dot_source):
        # One cluster per distinct declared frequency; the config declares 7D.
        assert "subgraph cluster_7D {" in dot_source
        assert 'label="7D"' in dot_source

    def test_dot_edges_coloured(self, dot_source):
        edges = [ln for ln in dot_source.splitlines() if " -> " in ln]
        assert edges, "no edges rendered at all"
        assert any("color=" in ln for ln in edges)


class TestFreqColorAssignment:
    """Colours are assigned to declared frequencies from a cycle, not a fixed table."""

    def test_distinct_freqs_get_distinct_colours(self):
        colors = assign_freq_colors(
            {"a": "7D", "b": "1ME", "c": "7D"}, dict(DEFAULT_PALETTE)
        )
        assert set(colors) == {"7D", "1ME"}
        assert colors["7D"] != colors["1ME"]

    def test_colours_come_from_the_cycle_in_first_seen_order(self):
        colors = assign_freq_colors({"a": "1ME", "b": "7D"}, dict(DEFAULT_PALETTE))
        assert colors["1ME"] == FREQ_COLOR_CYCLE[0]
        assert colors["7D"] == FREQ_COLOR_CYCLE[1]

    def test_palette_entry_pins_a_frequency(self):
        colors = assign_freq_colors({"a": "7D"}, {**DEFAULT_PALETTE, "7D": "#123456"})
        assert colors["7D"] == "#123456"

    def test_no_frequencies_no_colours(self):
        assert assign_freq_colors({}, dict(DEFAULT_PALETTE)) == {}


class TestCustomStyleFunction:
    def _mock_node(self, tags=None, type_=None, name=""):
        node = MagicMock()
        node.tags = tags or {}
        node.type = type_ or object
        node.name = name
        return node

    def _style(
        self,
        output_vars: "set[str] | frozenset[str]" = frozenset(),
        freq_map: "dict[str, str] | None" = None,
    ):
        freq_map = freq_map if freq_map is not None else {}
        colors = assign_freq_colors(freq_map, dict(DEFAULT_PALETTE))
        return (
            make_style_function(GraphvizSpec(), set(output_vars), freq_map, colors),
            colors,
        )

    def test_declared_freq_node_coloured_and_labelled(self):
        # The fill comes from the node's *declared* frequency, not its name.
        node = self._mock_node(type_=xr.DataArray, name="gpp_smoothed")
        style_fn, colors = self._style(freq_map={"gpp_smoothed": "7D"})
        style, _, label = style_fn(node=node, node_class="default")
        assert style["fillcolor"] == colors["7D"]
        assert label == "7D"

    def test_output_node_gets_highlight_border(self):
        node = self._mock_node(type_=xr.DataArray, name="gpp_monthly")
        style_fn, colors = self._style({"gpp_monthly"}, freq_map={"gpp_monthly": "1ME"})
        style, _, label = style_fn(node=node, node_class="default")
        assert style["color"] == DEFAULT_PALETTE["output"]
        assert "penwidth" in style
        # frequency fill is retained alongside the output border
        assert style["fillcolor"] == colors["1ME"]
        assert label == "output"

    def test_node_without_a_declared_freq_has_empty_style(self):
        # A name suffix alone means nothing now — only declarations count.
        node = self._mock_node(type_=xr.DataArray, name="gpp_daily")
        style_fn, _ = self._style()
        style, _, label = style_fn(node=node, node_class="default")
        assert style == {}
        assert label is None


class TestGraphPostProcessing:
    def test_relabel_replaces_type_with_unit(self):
        digraph = SimpleNamespace(
            body=[
                "\tgpp_weekly [label=<<b>gpp_weekly</b><br /><br /><i>DataArray</i>>]\n",
                "\tlatitude [label=<<b>latitude</b><br /><br /><i>DataArray</i>>]\n",
            ]
        )
        relabel_with_units(digraph, {"gpp_weekly": "g m-2 d-1"})  # type: ignore[arg-type]
        assert "<i>g m-2 d-1</i>" in digraph.body[0]
        # nodes without a declared unit keep their original type
        assert "<i>DataArray</i>" in digraph.body[1]

    def test_relabel_input_table_rows(self):
        row = "<tr><td>temperature_daily</td><td>DataArray</td></tr>"
        other = "<tr><td>latitude</td><td>DataArray</td></tr>"
        digraph = SimpleNamespace(
            body=[f'\t_inputs [label=<<table border="0">{row}{other}</table>>]\n']
        )
        relabel_with_units(digraph, {"temperature_daily": "degC"})  # type: ignore[arg-type]
        assert "<td>temperature_daily</td><td>degC</td>" in digraph.body[0]
        # rows for inputs without a declared unit are untouched
        assert "<td>latitude</td><td>DataArray</td>" in digraph.body[0]

    def test_color_edges_by_source_frequency(self):
        digraph = SimpleNamespace(
            body=[
                "\ttemperature_weekly -> gpp_weekly\n",
                "\tlatitude -> gpp_weekly\n",
            ]
        )
        color_edges_by_frequency(
            digraph,  # type: ignore[arg-type]
            {"temperature_weekly": "7D"},
            {"7D": "#8da0cb"},
        )
        assert 'color="#8da0cb"' in digraph.body[0]
        # edges from unknown-frequency sources are untouched
        assert "color=" not in digraph.body[1]

    def test_infer_frequencies_by_neighbour_consensus(self):
        # mymodel: weekly in, weekly out -> weekly; its input table follows it.
        digraph = SimpleNamespace(
            body=[
                "\ttemperature_weekly -> mymodel\n",
                "\tmymodel -> gpp_weekly\n",
                "\t_mymodel_inputs -> mymodel\n",
            ]
        )
        freq = infer_frequencies(
            digraph,  # type: ignore[arg-type]
            {"temperature_weekly": "weekly", "gpp_weekly": "weekly"},
        )
        assert freq["mymodel"] == "weekly"
        assert freq["_mymodel_inputs"] == "weekly"

    def test_infer_frequencies_conflict_stays_unresolved(self):
        # a node bridging daily and monthly has no consensus -> not assigned.
        digraph = SimpleNamespace(
            body=[
                "\ttemperature_daily -> bridge\n",
                "\tbridge -> soc_monthly\n",
            ]
        )
        freq = infer_frequencies(
            digraph,  # type: ignore[arg-type]
            {"temperature_daily": "daily", "soc_monthly": "monthly"},
        )
        assert "bridge" not in freq

    def test_cluster_groups_nodes_by_frequency(self):
        digraph = SimpleNamespace(
            body=[
                "\tgpp_weekly [label=<<b>gpp_weekly</b>>]\n",
                "\ttemperature_daily [label=<<b>temperature_daily</b>>]\n",
                "\tsurface_type [label=<<b>surface_type</b>>]\n",  # ungrouped
                "\t_gpp_weekly_inputs [label=<<table></table>>]\n",  # joins 7D
                "\ttemperature_daily -> gpp_weekly\n",
                "\t_gpp_weekly_inputs -> gpp_weekly\n",
            ]
        )
        cluster_nodes_by_frequency(
            digraph,  # type: ignore[arg-type]
            {"gpp_weekly": "7D", "temperature_daily": "1D"},
            {"7D": "#8da0cb", "1D": "#fc8d62", "1ME": "#a6d854"},
        )
        source = "".join(digraph.body)
        assert "subgraph cluster_7D {" in source
        assert "subgraph cluster_1D {" in source
        # a frequency with no members emits no empty cluster
        assert "cluster_1ME" not in source
        # the input table joins the cluster of the node it feeds
        weekly = source.split("cluster_7D {", 1)[1].split("}", 1)[0]
        assert "_gpp_weekly_inputs" in weekly
        assert "gpp_weekly [label" in weekly
        # ungrouped nodes stay outside any cluster
        plant_idx = source.index("surface_type [label")
        assert plant_idx > source.index("}")  # after the last cluster brace
        # every node is declared before any edge (clustering pitfall guard)
        assert source.index("gpp_weekly [label") < source.index(" -> ")

    def test_cluster_id_is_sanitised_and_label_quoted(self):
        # An anchored offset alias contains a hyphen, which Graphviz will not accept
        # in a bare cluster id.
        digraph = SimpleNamespace(body=["\tgpp [label=<<b>gpp</b>>]\n"])
        cluster_nodes_by_frequency(
            digraph,  # type: ignore[arg-type]
            {"gpp": "W-SUN"},
            {"W-SUN": "#8da0cb"},
        )
        source = "".join(digraph.body)
        assert "subgraph cluster_W_SUN {" in source
        assert 'label="W-SUN"' in source


class TestGraphvizSpec:
    def test_none_returns_defaults(self):
        spec = load_graphviz_spec(None)
        assert spec.palette == DEFAULT_PALETTE
        assert spec.style_function is None
        assert spec.show_legend is True
        assert spec.cluster_by_frequency is True

    def test_cluster_by_frequency_can_be_disabled(self, tmp_path):
        f = tmp_path / "style.toml"
        f.write_text("cluster_by_frequency = false\n")
        spec = load_graphviz_spec(f)
        assert spec.cluster_by_frequency is False

    def test_partial_palette_is_deep_merged(self, tmp_path):
        f = tmp_path / "style.toml"
        f.write_text('[palette]\n"7D" = "#000000"\n')
        spec = load_graphviz_spec(f)
        assert spec.palette["7D"] == "#000000"
        # untouched categories fall back to the defaults
        assert spec.palette["output"] == DEFAULT_PALETTE["output"]

    def test_graph_attr_collected_into_kwargs(self, tmp_path):
        f = tmp_path / "style.toml"
        f.write_text('[graph_attr]\nrankdir = "TB"\n')
        spec = load_graphviz_spec(f)
        assert spec.graphviz_kwargs == {"graph_attr": {"rankdir": "TB"}}

    def test_unknown_key_raises(self, tmp_path):
        f = tmp_path / "style.toml"
        f.write_text("bogus = 1\n")
        with pytest.raises(ValueError, match="Unknown key"):
            load_graphviz_spec(f)


class TestImportStyleFunction:
    def test_imports_module_function(self):
        import os.path

        assert _import_style_function("os.path:join") is os.path.join

    def test_rejects_malformed_path(self):
        with pytest.raises(ValueError, match="module:function"):
            _import_style_function("not_a_reference")


class TestStrayGraphvizSection:
    def test_science_config_ignores_graphviz_section(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[graphviz]\nshow_legend = true\n"
            '[[node]]\nname = "y"\ninputs = ["x"]\nexpression = "x * 2"\n'
        )
        # must not raise the missing-_import_path error for [graphviz]
        parsed = load_config(cfg)
        assert "node" in parsed.modules
