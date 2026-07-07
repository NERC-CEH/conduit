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
    cluster_nodes_by_frequency,
    color_edges_by_frequency,
    infer_frequencies,
    make_style_function,
    relabel_with_units,
)
from conduit.cli.graph_style import DEFAULT_PALETTE, GraphvizSpec, load_graphviz_spec
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

[grid]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
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


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


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
    def test_style_file_overrides_palette(self, config_toml, tmp_path):
        style = tmp_path / "style.toml"
        # the test config's derived weekly node receives the overridden fill colour.
        style.write_text('[palette]\nweekly = "#123456"\n')
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


class TestCustomStyleFunction:
    def _mock_node(self, tags=None, type_=None, name=""):
        node = MagicMock()
        node.tags = tags or {}
        node.type = type_ or object
        node.name = name
        return node

    def _style(self, output_vars: "set[str] | frozenset[str]" = frozenset()):
        return make_style_function(GraphvizSpec(), set(output_vars))

    def test_static_input_gets_static_colour(self):
        node = self._mock_node(tags={"module": "conduit.inputs.static"})
        style, _, label = self._style()(node=node, node_class="default")
        assert style["fillcolor"] == DEFAULT_PALETTE["static"]
        assert label == "static input"

    def test_daily_dataarray_coloured_and_labelled(self):
        node = self._mock_node(type_=xr.DataArray, name="gpp_daily")
        style, _, label = self._style()(node=node, node_class="default")
        assert style["fillcolor"] == DEFAULT_PALETTE["daily"]
        assert label == "daily"

    def test_monthly_dataarray_coloured(self):
        node = self._mock_node(type_=xr.DataArray, name="gpp_monthly")
        style, _, _ = self._style()(node=node, node_class="default")
        assert style["fillcolor"] == DEFAULT_PALETTE["monthly"]

    def test_output_node_gets_highlight_border(self):
        node = self._mock_node(type_=xr.DataArray, name="gpp_monthly")
        style, _, label = self._style({"gpp_monthly"})(node=node, node_class="default")
        assert style["color"] == DEFAULT_PALETTE["output"]
        assert "penwidth" in style
        # frequency fill is retained alongside the output border
        assert style["fillcolor"] == DEFAULT_PALETTE["monthly"]
        assert label == "output"

    def test_unrecognised_node_has_empty_style(self):
        node = self._mock_node(name="some_other_node")
        style, _, label = self._style()(node=node, node_class="default")
        assert style == {}
        assert label is None


class TestGraphPostProcessing:
    def test_relabel_replaces_type_with_unit(self):
        digraph = SimpleNamespace(
            body=[
                "\tgpp_weekly [label=<<b>gpp_weekly</b><br /><br /><i>DataArray</i>>]\n",
                "\tdates_weekly [label=<<b>dates_weekly</b><br /><br /><i>DatetimeIndex</i>>]\n",
            ]
        )
        relabel_with_units(digraph, {"gpp_weekly": "g m-2 d-1"})  # type: ignore[arg-type]
        assert "<i>g m-2 d-1</i>" in digraph.body[0]
        # nodes without a declared unit keep their original type
        assert "<i>DatetimeIndex</i>" in digraph.body[1]

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
            {"temperature_weekly": "weekly"},
            DEFAULT_PALETTE,
        )
        assert f'color="{DEFAULT_PALETTE["weekly"]}"' in digraph.body[0]
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
                "\t_gpp_weekly_inputs [label=<<table></table>>]\n",  # joins weekly
                "\ttemperature_daily -> gpp_weekly\n",
                "\t_gpp_weekly_inputs -> gpp_weekly\n",
            ]
        )
        cluster_nodes_by_frequency(
            digraph,  # type: ignore[arg-type]
            {"gpp_weekly": "weekly", "temperature_daily": "daily"},
            DEFAULT_PALETTE,
        )
        source = "".join(digraph.body)
        assert "subgraph cluster_weekly {" in source
        assert "subgraph cluster_daily {" in source
        # monthly has no members, so no empty cluster is emitted
        assert "cluster_monthly" not in source
        # the input table joins the cluster of the node it feeds
        weekly = source.split("cluster_weekly {", 1)[1].split("}", 1)[0]
        assert "_gpp_weekly_inputs" in weekly
        assert "gpp_weekly [label" in weekly
        # ungrouped nodes stay outside any cluster
        plant_idx = source.index("surface_type [label")
        assert plant_idx > source.index("}")  # after the last cluster brace
        # every node is declared before any edge (clustering pitfall guard)
        assert source.index("gpp_weekly [label") < source.index(" -> ")


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
        f.write_text('[palette]\ndaily = "#000000"\n')
        spec = load_graphviz_spec(f)
        assert spec.palette["daily"] == "#000000"
        # untouched categories fall back to the defaults
        assert spec.palette["monthly"] == DEFAULT_PALETTE["monthly"]

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
