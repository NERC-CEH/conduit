"""Unit tests for conduit.config."""

from pathlib import Path

import pytest

from conduit.config import (
    AnnotationPolicySpec,
    Config,
    IOSpec,
    NodeSpec,
    ParsedConfig,
    load_config,
)

TEST_CONFIG_PATH = Path(__file__).parent / "test_config.toml"

EXPECTED_MODULES = [
    "node",  # test_config.toml defines a single [[node]] derived variable
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
        assert "humidity" in vars_

    def test_static_input_vars(self, parsed_config):
        vars_ = parsed_config.input_specs["static"].vars
        assert "elevation" in vars_
        assert "roughness" in vars_

    def test_input_paths_are_absolute(self, parsed_config):
        for freq, spec in parsed_config.input_specs.items():
            assert Path(spec.path).is_absolute(), f"{freq} path should be absolute"

    def test_input_paths_resolve_relative_to_config(self, parsed_config):
        assert (
            Path(parsed_config.input_specs["daily"].path)
            == TEST_CONFIG_PATH.parent / "daily.nc"
        )

    def test_vars_mapping_form_parsed(self):
        config = Config(
            {"inputs": {"met": {"path": "m.nc", "vars": {"temperature_daily": "t2m"}}}}
        )
        spec = config.parse().input_specs["met"]
        assert spec.vars == {"temperature_daily": "t2m"}

    def test_vars_mapping_non_string_raises(self):
        config = Config(
            {"inputs": {"met": {"path": "m.nc", "vars": {"temperature": 3}}}}
        )
        with pytest.raises(ValueError, match="node_name = file_var"):
            config.parse()


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
    """Tests for driver_config: user module params only."""

    def test_node_specs_are_a_parsed_field(self, parsed_config):
        assert [s.name for s in parsed_config.node_specs] == ["mean_temperature_weekly"]

    def test_node_specs_not_in_driver_config(self, parsed_config):
        # node_specs are a real ParsedConfig field, not smuggled through Hamilton's
        # driver config (where every user module would see them as a config key).
        assert "node_specs" not in parsed_config.driver_config

    def test_module_params_merged_into_driver_config(self):
        config = Config(
            {"mymodel": {"_import_path": "pkg.mod", "threshold": 0.5, "mode": "fast"}}
        )
        dc = config.parse().driver_config
        assert dc["threshold"] == 0.5
        assert dc["mode"] == "fast"

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

    def test_non_importable_module_raises_value_error(self, tmp_path):
        config = Config({"mymodel": {"_import_path": "no_such_pkg.mod"}})

        def _build():
            from conduit.dag.driver import build_driver

            parsed = config.parse()
            build_driver(
                parsed.modules, parsed.driver_config, node_specs=parsed.node_specs
            )

        with pytest.raises(ValueError, match="Cannot load module"):
            _build()

    def test_duplicate_module_params_raise(self, tmp_path):
        config = Config(
            {
                "mod_a": {"_import_path": "pkg.a", "shared_param": "a"},
                "mod_b": {"_import_path": "pkg.b", "shared_param": "b"},
            }
        )
        with pytest.raises(ValueError, match="shared_param"):
            config.parse()

    def test_param_conflict_names_both_sections(self):
        config = Config(
            {
                "modela": {"_import_path": "pkg.a", "threshold": 1},
                "modelb": {"_import_path": "pkg.b", "threshold": 2},
            }
        )
        with pytest.raises(ValueError, match="threshold") as exc:
            config.parse()
        # A user cannot fix the collision without knowing who they collide with.
        message = str(exc.value)
        assert "[modela]" in message
        assert "[modelb]" in message

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
        config = Config({"grid": {}})
        parsed = config.parse()
        assert "grid" not in parsed.modules

    def test_no_grid_section_also_fine(self):
        config = Config({"grid": {}})
        parsed = config.parse()
        assert "grid" not in parsed.modules


class TestResample:
    """Tests for [[resample]] preset parsing (desugars to fan-out node specs)."""

    def test_resample_adds_node_module(self):
        config = Config(
            {
                "resample": [
                    {"vars": ["gpp"], "from": "daily", "to": "monthly", "freq": "1ME"}
                ],
            }
        )
        parsed = config.parse()
        assert parsed.modules == ["node"]
        assert "resample_specs" not in parsed.driver_config

    def test_no_resample_omits_node_module(self):
        config = Config({"grid": {}})
        parsed = config.parse()
        assert "node" not in parsed.modules

    def test_resample_desugars_to_passthrough_node_specs(self):
        config = Config(
            {
                "resample": [
                    {
                        "vars": ["gpp", "npp"],
                        "from": "daily",
                        "to": "weekly",
                        "freq": "7D",
                    }
                ],
            }
        )
        specs = config.parse().node_specs
        by_name = {s.name: s for s in specs}
        assert set(by_name) == {"gpp_weekly", "npp_weekly"}
        assert by_name["gpp_weekly"].inputs == ["gpp_daily"]
        assert by_name["gpp_weekly"].passthrough is True
        assert "freq='7D'" in (by_name["gpp_weekly"].expression or "")

    def test_from_and_to_are_bare_suffixes_not_frequencies(self):
        # ``from``/``to`` name the input and output nodes and mean nothing else;
        # the frequency is ``freq`` alone.
        config = Config(
            {
                "resample": [
                    {
                        "vars": ["gpp"],
                        "from": "raw",
                        "to": "smoothed",
                        "freq": "10D",
                    }
                ],
            }
        )
        spec = config.parse().node_specs[0]
        assert spec.name == "gpp_smoothed"
        assert spec.inputs == ["gpp_raw"]
        assert spec.freq == "10D"
        assert "freq='10D'" in (spec.expression or "")

    def test_duplicate_resample_output_raises(self):
        config = Config(
            {
                "resample": [
                    {"vars": ["gpp"], "from": "daily", "to": "monthly", "freq": "1ME"},
                    {"vars": ["gpp"], "from": "weekly", "to": "monthly", "freq": "1ME"},
                ],
            }
        )
        with pytest.raises(ValueError, match="Duplicate node name"):
            config.parse()

    @pytest.mark.parametrize("missing", ["vars", "from", "to", "freq"])
    def test_missing_required_key_raises(self, missing):
        entry = {"vars": ["gpp"], "from": "daily", "to": "weekly", "freq": "7D"}
        del entry[missing]
        config = Config({"resample": [entry]})
        with pytest.raises(ValueError, match=f"missing required key.*{missing}"):
            config.parse()

    def test_invalid_freq_raises_at_parse_time(self):
        config = Config(
            {
                "resample": [
                    {"vars": ["gpp"], "from": "daily", "to": "weekly", "freq": "nope"}
                ],
            }
        )
        with pytest.raises(ValueError, match="invalid frequency 'nope'"):
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
        config = Config({"grid": {}})
        parsed = config.parse()
        assert "node" not in parsed.modules

    def test_node_specs_parsed(self):
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
        specs = parsed.node_specs
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
                        "name": "mean_temperature_weekly",
                        "inputs": ["temperature_daily"],
                        "_import_path": "mypackage.met_utils",
                        "function": "mean_temperature",
                    }
                ]
            }
        )
        parsed = config.parse()
        spec = parsed.node_specs[0]
        assert isinstance(spec, NodeSpec)
        assert spec.expression is None
        assert spec.import_path == "mypackage.met_utils"
        assert spec.function == "mean_temperature"

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
        spec = config.parse().node_specs[0]
        assert spec.units == "1"

    def test_node_units_default_none(self):
        config = Config({"node": [{"name": "f", "inputs": ["a"], "expression": "a"}]})
        assert config.parse().node_specs[0].units is None

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

    @pytest.mark.parametrize("bad", ["mean temperature", "2fast", "a-b", "lambda"])
    def test_node_name_must_be_identifier(self, bad):
        config = Config({"node": [{"name": bad, "inputs": ["a"], "expression": "a"}]})
        with pytest.raises(ValueError, match=repr(bad)):
            config.parse()

    def test_node_input_must_be_identifier(self):
        config = Config(
            {"node": [{"name": "foo", "inputs": ["a b"], "expression": "a"}]}
        )
        with pytest.raises(ValueError, match="'a b'"):
            config.parse()

    @pytest.mark.parametrize("reserved", ["xr", "Any", "import_module", "__transforms"])
    def test_reserved_node_names_rejected(self, reserved):
        # A node named `xr` would shadow the helper bound in the generated module's
        # namespace for every later node's expression.
        config = Config(
            {"node": [{"name": reserved, "inputs": ["a"], "expression": "a"}]}
        )
        with pytest.raises(ValueError, match="reserved"):
            config.parse()

    def test_import_path_without_function_raises(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "foo",
                        "inputs": ["a"],
                        "_import_path": "some.module",
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="missing 'function'"):
            config.parse()

    def test_function_without_import_path_raises(self):
        config = Config(
            {
                "node": [
                    {
                        "name": "foo",
                        "inputs": ["a"],
                        "function": "some_fn",
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="missing '_import_path'"):
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


class TestAnnotationsSection:
    """Tests for the [annotations] section and its legacy [units] alias."""

    def test_units_alias_mode_and_exact(self):
        parsed = Config({"units": {"mode": "strict", "exact": True}}).parse()
        assert parsed.annotations.on_missing == "error"
        assert parsed.annotations.on_inexact == "error"
        assert parsed.annotations.on_mismatch is None

    def test_mode_off_disables(self):
        parsed = Config({"annotations": {"mode": "off"}}).parse()
        assert parsed.annotations.enabled is False

    def test_on_mismatch_drives_schema_and_temporal(self):
        parsed = Config({"annotations": {"on_mismatch": "warn"}}).parse()
        assert parsed.annotations.on_mismatch == "warn"

    def test_on_uninferable(self):
        parsed = Config({"annotations": {"on_uninferable": "ignore"}}).parse()
        assert parsed.annotations.on_uninferable == "ignore"

    def test_invalid_on_mismatch_raises(self):
        with pytest.raises(ValueError, match="on_mismatch"):
            Config({"annotations": {"on_mismatch": "explode"}}).parse()

    def test_invalid_on_uninferable_raises(self):
        with pytest.raises(ValueError, match="on_uninferable"):
            Config({"annotations": {"on_uninferable": "explode"}}).parse()

    def test_both_sections_raise(self):
        with pytest.raises(ValueError, match="not both"):
            Config({"annotations": {}, "units": {}}).parse()

    def test_absent_section_is_all_none(self):
        parsed = Config({}).parse()
        assert parsed.annotations.enabled is None
        assert parsed.annotations.on_mismatch is None
        assert parsed.annotations.on_uninferable is None


class TestAnnotationPolicyApply:
    """apply() pushes every axis into xarray-annotated's global policy."""

    def test_annotation_policy_apply_sets_all_axes(self):
        from xarray_annotated.schema import get_policy as schema_get_policy
        from xarray_annotated.schema import policy as schema_policy
        from xarray_annotated.temporal import get_policy as temporal_get_policy
        from xarray_annotated.temporal import policy as temporal_policy
        from xarray_annotated.units import get_policy as units_get_policy
        from xarray_annotated.units import policy as units_policy

        spec = AnnotationPolicySpec(
            enabled=True,
            on_missing="error",
            on_inexact="error",
            on_mismatch="warn",
            on_uninferable="ignore",
        )
        # The three context managers restore the process-global policy on exit.
        with units_policy(), schema_policy(), temporal_policy():
            spec.apply()
            units = units_get_policy()
            assert units.enabled is True
            assert units.on_missing == "error"
            assert units.on_inexact == "error"
            # on_mismatch drives *both* validate-only domains.
            assert schema_get_policy().on_mismatch == "warn"
            assert temporal_get_policy().on_mismatch == "warn"
            assert temporal_get_policy().on_uninferable == "ignore"

    def test_empty_policy_applies_nothing(self):
        from xarray_annotated.units import get_policy, policy

        with policy(enabled=True, on_missing="warn"):
            AnnotationPolicySpec().apply()
            assert get_policy().enabled is True
            assert get_policy().on_missing == "warn"


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


class TestCheckSpecs:
    """Tests for the `[validation].checks` block parsing (_parse_checks)."""

    def _cfg(self, checks):
        return Config(
            {
                "inputs": {
                    "climate": {"path": "c.nc", "vars": ["temperature"]},
                    "land": {"path": "l.nc", "vars": ["elevation"]},
                },
                "validation": {"checks": checks},
            }
        )

    def test_no_validation_section_defaults_empty(self):
        assert Config({"inputs": {"a": {"path": "a.nc"}}}).parse().checks == []

    def test_empty_validation_section_defaults_empty(self):
        cfg = Config({"inputs": {"a": {"path": "a.nc"}}, "validation": {}})
        assert cfg.parse().checks == []

    def test_unknown_validation_key_rejected(self):
        cfg = Config({"inputs": {"a": {"path": "a.nc"}}, "validation": {"chekcs": []}})
        with pytest.raises(ValueError, match="unknown key"):
            cfg.parse()

    def test_basic_check_parsed(self):
        parsed = self._cfg(
            [{"check": "time_equal", "inputs": ["climate", "land"]}]
        ).parse()
        assert len(parsed.checks) == 1
        spec = parsed.checks[0]
        assert spec.check == "time_equal"
        assert spec.inputs == ["climate", "land"]
        assert spec.kwargs == {}

    def test_wildcard_expands_to_all_inputs(self):
        parsed = self._cfg([{"check": "time_equal", "inputs": ["*"]}]).parse()
        assert parsed.checks[0].inputs == ["climate", "land"]

    def test_wildcard_mixed_with_names_rejected(self):
        with pytest.raises(ValueError, match="sole element"):
            self._cfg([{"check": "time_equal", "inputs": ["*", "climate"]}]).parse()

    def test_unknown_check_name_rejected(self):
        with pytest.raises(ValueError, match="unknown check"):
            self._cfg([{"check": "nope", "inputs": ["climate"]}]).parse()

    def test_unknown_input_section_rejected(self):
        with pytest.raises(ValueError, match="unknown input section"):
            self._cfg([{"check": "time_equal", "inputs": ["climate", "sea"]}]).parse()

    def test_kwargs_forwarded(self):
        parsed = self._cfg(
            [{"check": "coords_equal", "inputs": ["*"], "coords": ["latitude"]}]
        ).parse()
        assert parsed.checks[0].kwargs == {"coords": ["latitude"]}

    def test_fixed_arity_violation_rejected(self):
        # time_subset requires exactly 2 inputs; ["*"] expands to 2 here — OK —
        # but 3 explicit inputs is a parse-time arity error.
        cfg = Config(
            {
                "inputs": {
                    "a": {"path": "a.nc"},
                    "b": {"path": "b.nc"},
                    "c": {"path": "c.nc"},
                },
                "validation": {
                    "checks": [{"check": "time_subset", "inputs": ["a", "b", "c"]}]
                },
            }
        )
        with pytest.raises(ValueError, match="exactly 2 input"):
            cfg.parse()

    def test_missing_inputs_key_rejected(self):
        with pytest.raises(ValueError, match="missing a non-empty 'inputs'"):
            self._cfg([{"check": "time_equal"}]).parse()
