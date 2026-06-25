"""Tests for the satterc CLI commands."""

import shutil
import tomllib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import xarray as xr
from typer.testing import CliRunner

from satterc._version import __version__
from satterc.cli import app
from satterc.cli.data_gen import _parse_duration, _validate_output_paths
from satterc.cli.graph import (
    _import_style_function,
    cluster_nodes_by_frequency,
    color_edges_by_frequency,
    infer_frequencies,
    make_style_function,
    relabel_with_units,
)
from satterc.cli.graph_style import DEFAULT_PALETTE, GraphvizSpec, load_graphviz_spec
from satterc.cli.setup import _display_models, _parse_selections, _toggle_selections
from satterc.config import load_config

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_toml(tmp_path, synthetic_data_dir):
    """Config TOML pointing to session-scoped synthetic NetCDF files."""
    content = f"""\
[models.pmodel]
method_kphio = "sandoval"
method_optchi = "lavergne20_c3"

[models.rothc]
n_years_spinup = 1

[grid]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["precipitation", "sunshine_fraction", "temperature", "lai", "gpp"]

[inputs.weekly]
path = "{synthetic_data_dir / "weekly.nc"}"
vars = ["co2", "fapar", "ppfd", "pressure", "vpd"]

[inputs.monthly]
path = "{synthetic_data_dir / "monthly.nc"}"
vars = ["dummy_variable"]

[inputs.static]
path = "{synthetic_data_dir / "static.nc"}"
vars = [
  "elevation", "plant_type", "max_soil_moisture", "clay_content",
  "soil_depth", "organic_carbon_stocks", "root_pool_init",
  "leaf_pool_init", "stem_pool_init",
]
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p


@pytest.fixture
def datagen_config_toml(tmp_path):
    """Config TOML and output data dir for data-gen generate tests.

    The parent directory exists but no NetCDF files have been written yet.
    """
    data_dir = tmp_path / "data"
    content = f"""\
[models.rothc]
n_years_spinup = 1

[inputs.daily]
path = "{data_dir / "daily.nc"}"
vars = ["precipitation", "sunshine_fraction", "temperature"]

[inputs.weekly]
path = "{data_dir / "weekly.nc"}"
vars = ["co2", "fapar", "ppfd", "pressure", "vpd"]

[inputs.monthly]
path = "{data_dir / "monthly.nc"}"
vars = ["dummy_variable"]

[inputs.static]
path = "{data_dir / "static.nc"}"
vars = ["elevation", "plant_type", "clay_content", "soil_depth", "organic_carbon_stocks"]
"""
    toml_path = tmp_path / "datagen_config.toml"
    toml_path.write_text(content)
    return toml_path, data_dir


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
        assert "t ha-1" in text  # e.g. rothc soil carbon pools
        gpp_line = next(
            line for line in text.splitlines() if line.strip().startswith("gpp_weekly ")
        )
        assert "<i>g m-2 d-1</i>" in gpp_line
        assert "DataArray" not in gpp_line

    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_style_file_overrides_palette(self, config_toml, tmp_path):
        style = tmp_path / "style.toml"
        # the test config runs pmodel (weekly) + rothc (monthly), so weekly
        # function nodes are present to receive the overridden fill colour.
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
        node = self._mock_node(tags={"module": "satterc.inputs.static"})
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
        # sgam: weekly in, weekly out -> weekly; its input table follows it.
        digraph = SimpleNamespace(
            body=[
                "\ttemperature_weekly -> sgam\n",
                "\tsgam -> gpp_weekly\n",
                "\t_sgam_inputs -> sgam\n",
            ]
        )
        freq = infer_frequencies(
            digraph,  # type: ignore[arg-type]
            {"temperature_weekly": "weekly", "gpp_weekly": "weekly"},
        )
        assert freq["sgam"] == "weekly"
        assert freq["_sgam_inputs"] == "weekly"

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
                "\tplant_type [label=<<b>plant_type</b>>]\n",  # ungrouped
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
        plant_idx = source.index("plant_type [label")
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
        cfg.write_text("[graphviz]\nshow_legend = true\n[models.pmodel]\n")
        # must not raise the missing-_import_path error for [graphviz]
        parsed = load_config(cfg)
        assert "models.pmodel" in parsed.modules


# ---------------------------------------------------------------------------
# data-gen helpers
# ---------------------------------------------------------------------------


class TestDataGenHelpers:
    def test_parse_duration_years(self):
        assert _parse_duration("2y") == int(2 * 365.25)

    def test_parse_duration_months(self):
        assert _parse_duration("6m") == int(6 * 30.44)

    def test_parse_duration_days(self):
        assert _parse_duration("30d") == 30

    def test_parse_duration_case_insensitive(self):
        assert _parse_duration("1Y") == _parse_duration("1y")

    def test_parse_duration_invalid_format_raises(self):
        import typer

        with pytest.raises(typer.BadParameter):
            _parse_duration("bad")

    def test_validate_output_paths_fresh_files(self, datagen_config_toml):
        toml_path, data_dir = datagen_config_toml
        config = load_config(toml_path)
        paths, dirs_to_create, files_to_overwrite = _validate_output_paths(config)
        # data_dir does not exist yet → all four paths land in dirs_to_create
        assert len(paths) == 4
        assert data_dir in dirs_to_create
        assert files_to_overwrite == []

    def test_validate_output_paths_existing_files(self, datagen_config_toml):
        toml_path, data_dir = datagen_config_toml
        data_dir.mkdir()
        (data_dir / "daily.nc").write_bytes(b"")
        config = load_config(toml_path)
        _, _, files_to_overwrite = _validate_output_paths(config)
        assert any("daily.nc" in str(p) for p in files_to_overwrite)


# ---------------------------------------------------------------------------
# data-gen generate command
# ---------------------------------------------------------------------------


class TestDataGenGenerateCommand:
    def test_generate_creates_files(self, datagen_config_toml):
        toml_path, data_dir = datagen_config_toml
        result = runner.invoke(
            app,
            ["data-gen", "generate", str(toml_path), "--duration", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert (data_dir / "daily.nc").exists()
        assert (data_dir / "static.nc").exists()

    def test_shows_generation_params_in_output(self, datagen_config_toml):
        toml_path, _ = datagen_config_toml
        result = runner.invoke(
            app,
            ["data-gen", "generate", str(toml_path), "--duration", "30d"],
        )
        assert "Grid dimensions" in result.output
        assert "Duration" in result.output
        assert "Random seed" in result.output

    def test_overwrite_confirmed_reruns_successfully(self, datagen_config_toml):
        toml_path, _data_dir = datagen_config_toml
        # First run creates files.
        runner.invoke(
            app, ["data-gen", "generate", str(toml_path), "--duration", "30d"]
        )
        # Second run: files exist → prompt → confirm overwrite.
        result = runner.invoke(
            app,
            ["data-gen", "generate", str(toml_path), "--duration", "30d"],
            input="y\n",
        )
        assert result.exit_code == 0, result.output

    def test_overwrite_declined_aborts(self, datagen_config_toml):
        toml_path, _data_dir = datagen_config_toml
        runner.invoke(
            app, ["data-gen", "generate", str(toml_path), "--duration", "30d"]
        )
        result = runner.invoke(
            app,
            ["data-gen", "generate", str(toml_path), "--duration", "30d"],
            input="n\n",
        )
        assert result.exit_code != 0

    def test_invalid_duration_fails(self, datagen_config_toml):
        toml_path, _ = datagen_config_toml
        result = runner.invoke(
            app, ["data-gen", "generate", str(toml_path), "--duration", "bad"]
        )
        assert result.exit_code != 0

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["data-gen", "generate", str(tmp_path / "no.toml")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# setup helpers
# ---------------------------------------------------------------------------


class TestSetupHelpers:
    def test_parse_selections_comma_separated(self):
        assert _parse_selections("a,b") == ["a", "b"]

    def test_parse_selections_space_separated(self):
        assert _parse_selections("a b") == ["a", "b"]

    def test_parse_selections_mixed_delimiters(self):
        assert _parse_selections("a, b c") == ["a", "b", "c"]

    def test_parse_selections_empty_string(self):
        assert _parse_selections("") == []

    def test_toggle_adds_new_item(self):
        result = _toggle_selections([], ["splash"])
        assert "splash" in result

    def test_toggle_removes_existing_item(self):
        result = _toggle_selections(["splash"], ["splash"])
        assert "splash" not in result

    def test_toggle_skips_item_not_in_available_set(self):
        result = _toggle_selections([], ["unknown"], available={"splash", "pmodel"})
        assert result == []

    def test_display_models_marks_selected(self, capsys):
        _display_models(["splash", "pmodel", "rothc"], {"splash"})
        captured = capsys.readouterr()
        assert "[x]" in captured.out
        assert "splash" in captured.out
        assert "pmodel" in captured.out


# ---------------------------------------------------------------------------
# setup command — non-interactive (--defaults)
# ---------------------------------------------------------------------------


class TestSetupCommandNonInteractive:
    def test_defaults_creates_toml(self, tmp_path):
        out = tmp_path / "config.toml"
        result = runner.invoke(
            app,
            ["setup", "--defaults", "--models", "rothc", "--output", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_generated_toml_is_loadable(self, tmp_path):
        out = tmp_path / "config.toml"
        runner.invoke(
            app,
            ["setup", "--defaults", "--models", "rothc", "--output", str(out)],
        )
        # Should parse without error.
        load_config(out)

    def test_generated_toml_contains_model_params(self, tmp_path):
        out = tmp_path / "config.toml"
        runner.invoke(
            app,
            ["setup", "--defaults", "--models", "rothc", "--output", str(out)],
        )
        with open(out, "rb") as f:
            data = tomllib.load(f)
        assert "models" in data
        assert "rothc" in data["models"]

    def test_defaults_without_models_fails(self):
        result = runner.invoke(app, ["setup", "--defaults"])
        assert result.exit_code != 0

    def test_invalid_model_name_fails(self, tmp_path):
        out = tmp_path / "config.toml"
        result = runner.invoke(
            app,
            ["setup", "--defaults", "--models", "notamodel", "--output", str(out)],
        )
        assert result.exit_code != 0

    def test_existing_output_with_defaults_exits_with_error(self, tmp_path):
        out = tmp_path / "config.toml"
        out.write_text("# existing")
        result = runner.invoke(
            app,
            ["setup", "--defaults", "--models", "rothc", "--output", str(out)],
        )
        assert result.exit_code == 1
        assert str(out) in result.output


# ---------------------------------------------------------------------------
# setup command — interactive
# ---------------------------------------------------------------------------


class TestSetupCommandInteractive:
    def test_models_option_with_interactive_prompts_creates_config(self, tmp_path):
        out = tmp_path / "config.toml"
        # Prompts in order:
        #   _select_custom_modules: module path → "\n" (finish)
        #   confirm "Use default paths?" → "\n" (accept True)
        #   prompt "Output config path" → "\n" (accept default)
        #   confirm "Generate synthetic data?" → "\n" (accept False)
        result = runner.invoke(
            app,
            ["setup", "--models", "rothc", "--output", str(out)],
            input="\n\n\n\n",
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_interactive_overwrite_confirmed(self, tmp_path):
        out = tmp_path / "config.toml"
        out.write_text("# old content")
        # First prompt: "Overwrite?" → "y"; then the 4 interactive prompts.
        result = runner.invoke(
            app,
            ["setup", "--models", "rothc", "--output", str(out)],
            input="y\n\n\n\n\n",
        )
        assert result.exit_code == 0, result.output
        # File should have been replaced with valid TOML.
        with open(out, "rb") as f:
            tomllib.load(f)

    def test_interactive_overwrite_declined(self, tmp_path):
        out = tmp_path / "config.toml"
        original = "# old content"
        out.write_text(original)
        result = runner.invoke(
            app,
            ["setup", "--models", "rothc", "--output", str(out)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert out.read_text() == original

    def test_fully_interactive_model_selection(self, tmp_path):
        out = tmp_path / "config.toml"
        # Prompts in order:
        #   _select_builtin_models: "1\n" (select splash), "0\n" (done)
        #   _select_custom_modules: "\n" (finish)
        #   confirm "Use default paths?" → "\n"
        #   prompt "Output config path" → "\n"
        #   confirm "Generate synthetic data?" → "\n"
        result = runner.invoke(
            app,
            ["setup", "--output", str(out)],
            input="1\n0\n\n\n\n\n",
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_interactive_with_data_generation(self, tmp_path):
        out = tmp_path / "config.toml"
        # Prompts in order:
        #   custom modules → "\n"
        #   use default paths → "\n"
        #   output path → "\n"  (accepts --output default)
        #   generate data → "y\n"
        #   grid → "\n" (1,1)
        #   duration → "30d\n"
        #   seed → "\n" (42)
        result = runner.invoke(
            app,
            ["setup", "--models", "splash", "--output", str(out)],
            input="\n\n\ny\n\n30d\n\n",
        )
        assert result.exit_code == 0, result.output
        # Generated config must be loadable.
        load_config(out)
        # Input data files must have been written alongside the config.
        inputs_dir = out.parent / "inputs"
        assert inputs_dir.exists()
        assert any(inputs_dir.iterdir())
