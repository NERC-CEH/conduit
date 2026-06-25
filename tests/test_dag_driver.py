"""Tests for satterc.dag.driver — build_driver wiring."""

import pytest
from hamilton import driver

from satterc.config import NodeSpec, ResampleSpec
from satterc.dag.driver import build_driver


class TestBuildDriverReturnType:
    def test_empty_module_list(self):
        assert isinstance(build_driver([], {}), driver.Driver)

    def test_known_model_splash(self):
        assert isinstance(build_driver(["models.splash"], {}), driver.Driver)

    def test_known_model_pmodel(self):
        assert isinstance(build_driver(["models.pmodel"], {}), driver.Driver)

    def test_known_model_rothc(self):
        assert isinstance(build_driver(["models.rothc"], {}), driver.Driver)

    def test_known_model_sgam(self):
        assert isinstance(build_driver(["models.sgam"], {}), driver.Driver)

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
        dr = build_driver(["models.splash"], {}, allow_module_overrides=True)
        assert isinstance(dr, driver.Driver)


class TestBuildDriverErrors:
    def test_unknown_model_prefix_raises(self):
        with pytest.raises(ValueError, match="Unknown model"):
            build_driver(["models.nonexistent"], {})

    def test_unknown_model_lists_known_models(self):
        with pytest.raises(ValueError, match=r"models\.pmodel"):
            build_driver(["models.typo"], {})

    def test_non_importable_custom_module_raises(self):
        with pytest.raises(ValueError, match="Cannot load module"):
            build_driver(["does_not_exist_pkg.module"], {})


class TestBuildDriverDAGStructure:
    """Verify that the built driver exposes expected DAG nodes."""

    def test_splash_driver_has_output_nodes(self):
        dr = build_driver(["models.splash"], {})
        available = {v.name for v in dr.list_available_variables()}
        assert "actual_evapotranspiration_daily" in available
        assert "soil_moisture_daily" in available
        assert "runoff_daily" in available

    def test_pmodel_driver_has_output_nodes(self):
        dr = build_driver(["models.pmodel"], {})
        available = {v.name for v in dr.list_available_variables()}
        assert "gpp_weekly" in available
        assert "lue_weekly" in available
        assert "iwue_weekly" in available

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
