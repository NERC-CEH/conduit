"""Tests for breadboard.dag.driver — build_driver wiring."""

import pytest
from hamilton import driver

from breadboard.config import NodeSpec, ResampleSpec
from breadboard.dag.driver import build_driver


class TestBuildDriverReturnType:
    def test_empty_module_list(self):
        assert isinstance(build_driver([], {}), driver.Driver)

    def test_resample_module(self):
        specs = [ResampleSpec(vars=["x"], source_freq="daily", target_freq="weekly")]
        assert isinstance(
            build_driver(["resample"], {"resample_specs": specs}), driver.Driver
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
        assert isinstance(build_driver(["node"], {"node_specs": specs}), driver.Driver)

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
        dr = build_driver(["node"], {"node_specs": specs}, allow_module_overrides=True)
        assert isinstance(dr, driver.Driver)

    def test_importable_custom_module(self):
        """A dotted import path to a real module loads like any built-in."""
        dr = build_driver(["breadboard.dag.resample"], {})
        assert isinstance(dr, driver.Driver)


class TestBuildDriverErrors:
    def test_non_importable_custom_module_raises(self):
        with pytest.raises(ValueError, match="Cannot load module"):
            build_driver(["does_not_exist_pkg.module"], {})


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
        dr = build_driver(["node"], {"node_specs": specs})
        available = {v.name for v in dr.list_available_variables()}
        assert "my_var" in available
