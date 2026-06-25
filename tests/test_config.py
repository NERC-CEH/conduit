"""Unit tests for satterc.config."""

from pathlib import Path

import pytest

from satterc.config import Config, IOSpec, NodeSpec, ParsedConfig, load_config

TEST_CONFIG_PATH = Path(__file__).parent / "test_config.toml"

EXPECTED_MODULES = [
    "models.pmodel",
    "models.rothc",
    # resample absent — no [[resample]] entries in test_config.toml
    # inputs/outputs absent — now in input_specs / output_specs, not modules
]


@pytest.fixture(scope="module")
def parsed_config():
    return load_config(TEST_CONFIG_PATH)


class TestLoadConfig:
    """Tests for the load_config() convenience function."""

    def test_returns_parsed_config(self, parsed_config):
        assert isinstance(parsed_config, ParsedConfig)

    def test_has_expected_fields(self, parsed_config):
        assert hasattr(parsed_config, "modules")
        assert hasattr(parsed_config, "driver_config")
        assert hasattr(parsed_config, "input_specs")
        assert hasattr(parsed_config, "output_specs")


class TestModules:
    """Tests for the modules list derived from config sections."""

    def test_modules_list(self, parsed_config):
        assert parsed_config.modules == EXPECTED_MODULES

    def test_no_input_modules(self, parsed_config):
        assert not any(m.startswith("inputs.") for m in parsed_config.modules)

    def test_no_output_modules(self, parsed_config):
        assert not any(m.startswith("outputs.") for m in parsed_config.modules)

    def test_no_grid_module(self, parsed_config):
        assert "grid" not in parsed_config.modules


class TestInputSpecs:
    """Tests for input_specs derived from [inputs.*] config sections."""

    def test_input_frequencies_present(self, parsed_config):
        assert "daily" in parsed_config.input_specs
        assert "weekly" in parsed_config.input_specs
        assert "monthly" in parsed_config.input_specs
        assert "static" in parsed_config.input_specs

    def test_input_specs_are_iospec(self, parsed_config):
        for spec in parsed_config.input_specs.values():
            assert isinstance(spec, IOSpec)

    def test_daily_input_vars(self, parsed_config):
        vars_ = parsed_config.input_specs["daily"].vars
        assert "temperature" in vars_
        assert "precipitation" in vars_
        assert "sunshine_fraction" in vars_

    def test_static_input_vars(self, parsed_config):
        vars_ = parsed_config.input_specs["static"].vars
        assert "elevation" in vars_
        assert "clay_content" in vars_

    def test_input_paths_are_absolute(self, parsed_config):
        for freq, spec in parsed_config.input_specs.items():
            assert Path(spec.path).is_absolute(), f"{freq} path should be absolute"

    def test_input_paths_resolve_relative_to_config(self, parsed_config):
        assert (
            Path(parsed_config.input_specs["daily"].path)
            == TEST_CONFIG_PATH.parent / "daily.nc"
        )


class TestOutputSpecs:
    """Tests for output_specs — empty in test config (no [outputs.*] sections)."""

    def test_output_specs_empty(self, parsed_config):
        assert parsed_config.output_specs == {}

    def test_output_specs_populated_when_present(self, tmp_path):
        config = Config(
            {"outputs": {"daily": {"path": str(tmp_path / "out.nc"), "vars": ["gpp"]}}}
        )
        parsed = config.parse()
        assert "daily" in parsed.output_specs
        assert isinstance(parsed.output_specs["daily"], IOSpec)
        assert parsed.output_specs["daily"].vars == ["gpp"]


class TestDriverConfig:
    """Tests for driver_config: model params and resample_specs only."""

    def test_model_params_merged_into_driver_config(self, parsed_config):
        dc = parsed_config.driver_config
        assert dc["method_kphio"] == "sandoval"
        assert dc["method_optchi"] == "lavergne20_c3"
        assert dc["n_years_spinup"] == 1

    def test_no_io_path_keys_in_driver_config(self, parsed_config):
        dc = parsed_config.driver_config
        for freq in ("daily", "weekly", "monthly", "static"):
            assert f"{freq}_inputs_path" not in dc
            assert f"{freq}_inputs_vars" not in dc
            assert f"{freq}_inputs_format" not in dc
            assert f"{freq}_outputs_path" not in dc
            assert f"{freq}_outputs_vars" not in dc
            assert f"{freq}_outputs_format" not in dc


class TestPathResolution:
    """Tests for path resolution relative to the config file location."""

    def test_input_paths_are_absolute(self, parsed_config):
        for freq, spec in parsed_config.input_specs.items():
            assert Path(spec.path).is_absolute(), f"{freq} should be absolute"

    def test_input_paths_resolve_relative_to_config(self, parsed_config):
        assert (
            Path(parsed_config.input_specs["daily"].path)
            == TEST_CONFIG_PATH.parent / "daily.nc"
        )

    def test_direct_construction_paths_unchanged(self):
        """Config() constructed directly should not modify paths."""
        config = Config(
            {"inputs": {"daily": {"path": "relative/path.nc", "vars": ["x"]}}}
        )
        assert config._data["inputs"]["daily"]["path"] == "relative/path.nc"


class TestValidation:
    """Tests for config validation behaviour."""

    def test_unknown_model_raises_value_error(self, tmp_path):
        config = Config({"models": {"unknown_model": {"param": "value"}}})

        def _build():
            from satterc.dag.driver import build_driver

            parsed = config.parse()
            build_driver(parsed.modules, parsed.driver_config)

        with pytest.raises(ValueError, match="unknown_model"):
            _build()

    def test_duplicate_model_params_raise(self, tmp_path):
        config = Config(
            {
                "models": {
                    "pmodel": {"shared_param": "a"},
                    "splash": {"shared_param": "b"},
                }
            }
        )
        with pytest.raises(ValueError, match="shared_param"):
            config.parse()

    def test_external_module_missing_import_path_raises(self):
        config = Config({"my_section": {"param": "value"}})
        with pytest.raises(ValueError, match="_import_path"):
            config.parse()

    def test_external_module_invalid_import_path_raises(self):
        config = Config({"my_section": {"_import_path": "not a.valid..path"}})
        with pytest.raises(ValueError, match="not a valid dotted module path"):
            config.parse()

    def test_external_module_import_path_accepted(self):
        config = Config(
            {"my_section": {"_import_path": "mypackage.mymodule", "param": 42}}
        )
        parsed = config.parse()
        assert "mypackage.mymodule" in parsed.modules
        assert parsed.driver_config["param"] == 42

    def test_input_section_missing_path_raises(self):
        config = Config({"inputs": {"daily": {"vars": ["x"]}}})
        with pytest.raises(ValueError, match=r"\[inputs\.daily\].*'path'"):
            config.parse()

    def test_output_section_empty_vars_raises(self, tmp_path):
        config = Config(
            {"outputs": {"daily": {"path": str(tmp_path / "out.nc"), "vars": []}}}
        )
        with pytest.raises(ValueError, match=r"\[outputs\.daily\].*no 'vars'"):
            config.parse()

    def test_output_section_missing_vars_raises(self, tmp_path):
        config = Config({"outputs": {"daily": {"path": str(tmp_path / "out.nc")}}})
        with pytest.raises(ValueError, match=r"\[outputs\.daily\].*no 'vars'"):
            config.parse()

    def test_output_section_missing_path_raises(self, tmp_path):
        config = Config({"outputs": {"daily": {"vars": ["gpp"]}}})
        with pytest.raises(ValueError, match=r"\[outputs\.daily\].*'path'"):
            config.parse()


class TestGrid:
    """Tests for [grid] section parsing — now a no-op."""

    def test_grid_section_does_not_add_grid_module(self):
        config = Config({"grid": {}, "models": {"pmodel": {}}})
        parsed = config.parse()
        assert "grid" not in parsed.modules

    def test_no_grid_section_also_fine(self):
        config = Config({"models": {"pmodel": {}}})
        parsed = config.parse()
        assert "grid" not in parsed.modules


class TestResample:
    """Tests for [[resample]] section parsing."""

    def test_resample_adds_resample_module(self):
        config = Config(
            {
                "models": {"pmodel": {}},
                "resample": [
                    {"vars": ["gpp"], "from_freq": "daily", "to_freq": "monthly"}
                ],
            }
        )
        parsed = config.parse()
        assert "resample" in parsed.modules

    def test_no_resample_omits_resample_module(self):
        config = Config({"models": {"pmodel": {}}})
        parsed = config.parse()
        assert "resample" not in parsed.modules

    def test_resample_specs_in_driver_config(self):
        from satterc.config import ResampleSpec

        config = Config(
            {
                "models": {"pmodel": {}},
                "resample": [
                    {"vars": ["gpp", "npp"], "from_freq": "daily", "to_freq": "weekly"}
                ],
            }
        )
        parsed = config.parse()
        specs = parsed.driver_config["resample_specs"]
        assert len(specs) == 1
        assert isinstance(specs[0], ResampleSpec)
        assert specs[0].vars == ["gpp", "npp"]
        assert specs[0].source_freq == "daily"
        assert specs[0].target_freq == "weekly"

    def test_duplicate_resample_output_raises(self):
        config = Config(
            {
                "models": {"pmodel": {}},
                "resample": [
                    {"vars": ["gpp"], "from_freq": "daily", "to_freq": "monthly"},
                    {"vars": ["gpp"], "from_freq": "weekly", "to_freq": "monthly"},
                ],
            }
        )
        with pytest.raises(ValueError, match="Duplicate resample output"):
            config.parse()

    def test_unsupported_freq_pair_raises(self):
        config = Config(
            {
                "models": {"pmodel": {}},
                "resample": [
                    {"vars": ["gpp"], "from_freq": "monthly", "to_freq": "daily"}
                ],
            }
        )
        with pytest.raises(ValueError, match="Unsupported resample direction"):
            config.parse()


class TestNode:
    """Tests for [[node]] section parsing."""

    def test_node_adds_node_module(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "aridity_index_daily",
                        "inputs": ["precipitation_daily", "aet_daily"],
                        "expression": "precipitation_daily / aet_daily",
                    }
                ]
            }
        )
        parsed = config.parse()
        assert "node" in parsed.modules

    def test_no_node_omits_node_module(self):
        config = Config({"models": {"pmodel": {}}})
        parsed = config.parse()
        assert "node" not in parsed.modules

    def test_node_specs_in_driver_config(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "aridity_index_daily",
                        "inputs": ["precipitation_daily", "aet_daily"],
                        "expression": "precipitation_daily / aet_daily",
                    }
                ]
            }
        )
        parsed = config.parse()
        specs = parsed.driver_config["node_specs"]
        assert len(specs) == 1
        assert isinstance(specs[0], NodeSpec)
        assert specs[0].name == "aridity_index_daily"
        assert specs[0].inputs == ["precipitation_daily", "aet_daily"]
        assert specs[0].expression == "precipitation_daily / aet_daily"
        assert specs[0].import_path is None
        assert specs[0].function is None

    def test_function_reference_spec(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "mean_growth_temperature_weekly",
                        "inputs": ["temperature_daily"],
                        "_import_path": "mypackage.met_utils",
                        "function": "mean_growth_temperature",
                    }
                ]
            }
        )
        parsed = config.parse()
        spec = parsed.driver_config["node_specs"][0]
        assert isinstance(spec, NodeSpec)
        assert spec.expression is None
        assert spec.import_path == "mypackage.met_utils"
        assert spec.function == "mean_growth_temperature"

    def test_node_units_parsed(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "aridity_index_daily",
                        "inputs": ["precipitation_daily", "aet_daily"],
                        "expression": "precipitation_daily / aet_daily",
                        "units": "1",
                    }
                ]
            }
        )
        spec = config.parse().driver_config["node_specs"][0]
        assert spec.units == "1"

    def test_node_units_default_none(self):
        config = Config({"node": [{"name": "f", "inputs": ["a"], "expression": "a"}]})
        assert config.parse().driver_config["node_specs"][0].units is None

    def test_invalid_node_units_raises(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "f",
                        "inputs": ["a"],
                        "expression": "a",
                        "units": "not_a_unit",
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="not a recognised"):
            config.parse()

    def test_duplicate_node_name_raises(self):
        config = Config(
            {
                "node": [
                    {"name": "foo", "inputs": ["a"], "expression": "a"},
                    {"name": "foo", "inputs": ["b"], "expression": "b"},
                ]
            }
        )
        with pytest.raises(ValueError, match="Duplicate node name"):
            config.parse()

    def test_both_expression_and_function_raises(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "foo",
                        "inputs": ["a"],
                        "expression": "a",
                        "_import_path": "some.module",
                        "function": "some_fn",
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="must specify either"):
            config.parse()

    def test_neither_expression_nor_function_raises(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "foo",
                        "inputs": ["a"],
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="must specify either"):
            config.parse()


class TestMultipleFrequencies:
    """Tests for multiple input/output frequencies."""

    def test_multiple_input_frequencies(self, tmp_path):
        config = Config(
            {
                "inputs": {
                    "daily": {"path": str(tmp_path / "daily.nc"), "vars": ["temp"]},
                    "weekly": {"path": str(tmp_path / "weekly.nc"), "vars": ["co2"]},
                }
            }
        )
        parsed = config.parse()
        assert "daily" in parsed.input_specs
        assert "weekly" in parsed.input_specs

    def test_multiple_output_frequencies(self, tmp_path):
        config = Config(
            {
                "outputs": {
                    "daily": {"path": str(tmp_path / "out_daily.nc"), "vars": ["gpp"]},
                    "monthly": {
                        "path": str(tmp_path / "out_monthly.nc"),
                        "vars": ["gpp"],
                    },
                }
            }
        )
        parsed = config.parse()
        assert "daily" in parsed.output_specs
        assert "monthly" in parsed.output_specs


class TestExternalModules:
    """Tests for external module sections."""

    def test_multiple_external_modules(self):
        config = Config(
            {
                "custom_loader": {
                    "_import_path": "mypackage.loader",
                    "param_a": 1,
                },
                "custom_transform": {
                    "_import_path": "mypackage.transform",
                    "param_b": 2,
                },
            }
        )
        parsed = config.parse()
        assert "mypackage.loader" in parsed.modules
        assert "mypackage.transform" in parsed.modules
        assert parsed.driver_config["param_a"] == 1
        assert parsed.driver_config["param_b"] == 2


class TestDump:
    """Tests for Config serialization."""

    def test_dump_roundtrip(self, tmp_path):
        """Config loaded, dumped, and reloaded should parse to the same result."""
        original = Config.load(TEST_CONFIG_PATH)
        out_path = tmp_path / "roundtrip.toml"
        original.dump(out_path)

        reloaded = Config.load(out_path).parse()
        original_parsed = original.parse()

        assert reloaded.modules == original_parsed.modules
        assert reloaded.input_specs.keys() == original_parsed.input_specs.keys()
        assert reloaded.driver_config.keys() == original_parsed.driver_config.keys()

    def test_format_keys_not_in_dump(self, tmp_path):
        """Format keys derived at parse time should not appear in the serialized TOML."""
        original = Config.load(TEST_CONFIG_PATH)
        out_path = tmp_path / "config.toml"
        original.dump(out_path)
        content = out_path.read_text()
        assert "_inputs_format" not in content
        assert "_outputs_format" not in content

    def test_dump_refuses_overwrite_by_default(self, tmp_path):
        """dump() should raise FileExistsError if file already exists."""
        out_path = tmp_path / "config.toml"
        out_path.write_text("")
        config = Config.load(TEST_CONFIG_PATH)
        with pytest.raises(FileExistsError):
            config.dump(out_path)

    def test_dump_overwrite_ok(self, tmp_path):
        """dump(overwrite_ok=True) should succeed even if file exists."""
        out_path = tmp_path / "config.toml"
        out_path.write_text("")
        config = Config.load(TEST_CONFIG_PATH)
        config.dump(out_path, overwrite_ok=True)
        assert out_path.stat().st_size > 0
