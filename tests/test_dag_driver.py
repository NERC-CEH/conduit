"""Tests for conduit.dag.driver — build_driver wiring."""

import pytest
from hamilton import driver

from conduit.config import Config, NodeSpec
from conduit.dag.driver import build_driver


class TestBuildDriverReturnType:
    def test_empty_module_list(self):
        assert isinstance(build_driver([], {}), driver.Driver)

    def test_resample_preset_builds(self):
        parsed = Config(
            {
                "resample": [
                    {"vars": ["x"], "from": "daily", "to": "weekly", "freq": "7D"}
                ]
            }
        ).parse()
        assert isinstance(
            build_driver(
                parsed.modules, parsed.driver_config, node_specs=parsed.node_specs
            ),
            driver.Driver,
        )

    def test_node_module(self):
        specs = [
            NodeSpec(
                name="y",
                inputs=["x"],
                expression="x * 2",
                import_path=None,
                function=None,
            )
        ]
        assert isinstance(build_driver(["node"], {}, node_specs=specs), driver.Driver)

    def test_allow_module_overrides_flag(self):
        specs = [
            NodeSpec(
                name="y",
                inputs=["x"],
                expression="x * 2",
                import_path=None,
                function=None,
            )
        ]
        dr = build_driver(["node"], {}, allow_module_overrides=True, node_specs=specs)
        assert isinstance(dr, driver.Driver)

    def test_importable_custom_module(self):
        """A dotted import path to a real module loads like any built-in."""
        dr = build_driver(["conduit.transforms"], {})
        assert isinstance(dr, driver.Driver)


class TestBuildDriverErrors:
    def test_non_importable_custom_module_raises(self):
        with pytest.raises(ValueError, match="Cannot load module"):
            build_driver(["does_not_exist_pkg.module"], {})

    def test_node_module_without_specs_raises(self):
        with pytest.raises(ValueError, match="no node_specs"):
            build_driver(["node"], {})


class TestBuildDriverDoesNotMutateConfig:
    """build_driver must not write Hamilton's power-user flag into the caller's dict."""

    def test_build_driver_does_not_mutate_config(self):
        config = {"threshold": 0.5}
        pristine = dict(config)
        build_driver([], config)
        assert config == pristine


class TestBuildDriverDAGStructure:
    """Verify that the built driver exposes expected DAG nodes."""

    def test_node_driver_exposes_generated_node(self):
        specs = [
            NodeSpec(
                name="my_var",
                inputs=["a", "b"],
                expression="a + b",
                import_path=None,
                function=None,
            )
        ]
        dr = build_driver(["node"], {}, node_specs=specs)
        available = {v.name for v in dr.list_available_variables()}
        assert "my_var" in available
