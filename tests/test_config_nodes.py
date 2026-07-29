"""[[node]] entries must inject their declared contracts into the built functions.

The existing ``test_config.toml`` defines a ``[[node]]`` entry, but it declares no
contracts (no units, freq, dims, or dtype), so the full integration suite never
exercises the annotation-injection-and-decorator-wrapping path. These tests build
nodes with the same shapes that real pipelines rely on and assert the declared
contract survives the entire chain: TOML → parse → NodeSpec → make_node_module →
build_driver → Hamilton Node.callable → ``typing.get_type_hints``.

Reading the hints back through ``get_type_hints(include_extras=True)`` catches
the injection being lost across ``functools.wraps`` — the Python 3.14 failure
mode where PEP 749 swapped ``__annotations__`` for ``__annotate__`` in
``functools.WRAPPER_ASSIGNMENTS``. Fixed in xarray-annotated 0.4.1.
"""

import textwrap
import typing

import pytest

from conduit.config import load_config
from conduit.dag.driver import build_driver

CONFIG = """
[[node]]
name = "balance"
inputs = ["rain", "demand"]
expression = "rain - demand"
units = "mm"
freq = "D"

[[node]]
name = "balance_is_positive"
inputs = ["balance"]
expression = "balance > 0"
units = "1"
freq = "D"

[[node]]
name = "full_featured"
inputs = ["a", "b"]
expression = "a * b"
units = "m s-1"
freq = "D"
dims = ["time", "pixel"]
dtype = "float64"
coords = ["x", "y"]

[[node]]
name = "dryness"
inputs = ["rain", "demand"]
expression = 'demand.sum("time") / rain.sum("time")'
units = "1"

[[node]]
name = "from_math"
inputs = ["a"]
_import_path = "math"
function = "sqrt"
units = "1"
freq = "D"
"""


@pytest.fixture(scope="module")
def node_config(tmp_path_factory):
    """A config whose only content is [[node]] entries, no external inputs."""
    path = tmp_path_factory.mktemp("nodes") / "config.toml"
    path.write_text(textwrap.dedent(CONFIG))
    return load_config(path)


class TestNodeSpecParsing:
    """Parsing is pure config handling and works on every supported Python."""

    def test_parses_into_node_specs(self, node_config):
        assert {spec.name for spec in node_config.node_specs} == {
            "balance",
            "balance_is_positive",
            "full_featured",
            "dryness",
            "from_math",
        }

    def test_balance_declares_units_and_freq(self, node_config):
        spec = next(s for s in node_config.node_specs if s.name == "balance")
        assert spec.units == "mm"
        assert spec.freq == "D"

    def test_consuming_node_uses_another_node_as_input(self, node_config):
        spec = next(
            s for s in node_config.node_specs if s.name == "balance_is_positive"
        )
        assert spec.inputs == ["balance"]

    def test_full_featured_declares_all_facets(self, node_config):
        spec = next(s for s in node_config.node_specs if s.name == "full_featured")
        assert spec.units == "m s-1"
        assert spec.freq == "D"
        assert spec.dims == ["time", "pixel"]
        assert spec.dtype == "float64"
        assert spec.coords == ["x", "y"]

    def test_climatological_node_declares_no_frequency(self, node_config):
        spec = next(s for s in node_config.node_specs if s.name == "dryness")
        assert spec.freq is None
        assert spec.units == "1"

    def test_function_import_node_parsed(self, node_config):
        spec = next(s for s in node_config.node_specs if s.name == "from_math")
        assert spec.import_path == "math"
        assert spec.function == "sqrt"
        assert spec.units == "1"
        assert spec.freq == "D"


_NODE_NAMES = frozenset(
    {"balance", "balance_is_positive", "full_featured", "dryness", "from_math"}
)


@pytest.fixture(scope="module")
def node_driver(node_config):
    """A built driver from the node-only config."""
    return build_driver(
        node_config.modules,
        node_config.driver_config,
        node_specs=node_config.node_specs,
    )


def _node_hints(driver):
    """Return ``get_type_hints`` for every real node in the graph."""
    return {
        name: typing.get_type_hints(
            driver.graph.nodes[name].callable, include_extras=True
        )
        for name in driver.graph.nodes
        if driver.graph.nodes[name].callable is not None
    }


class TestNodeLowering:
    """The contract must survive exec, injection, and decorator wrapping.

    Reading the hints through ``get_type_hints(include_extras=True)`` on
    Hamilton's own node callable catches the Python 3.14 failure mode where
    PEP 749 dropped the injected return annotation across ``functools.wraps``.
    """

    def test_driver_builds(self, node_driver):
        assert set(node_driver.graph.nodes) >= _NODE_NAMES
        for name in _NODE_NAMES:
            assert node_driver.graph.nodes[name].callable is not None

    def test_all_node_returns_have_annotations(self, node_driver):
        """Every generated node must carry its injected return annotation."""
        hints = _node_hints(node_driver)
        for name in _NODE_NAMES:
            assert "return" in hints[name], (
                f"{name} lost its injected return annotation"
            )

    def test_balance_return_has_units_and_freq(self, node_driver):
        ret = str(_node_hints(node_driver)["balance"]["return"])
        assert "mm" in ret
        assert "Freq" in ret

    def test_consuming_node_return_has_units_and_freq(self, node_driver):
        ret_s = str(_node_hints(node_driver)["balance_is_positive"]["return"])
        assert "1" in ret_s
        assert "Freq" in ret_s

    def test_full_featured_return_has_all_facets(self, node_driver):
        ret_s = str(_node_hints(node_driver)["full_featured"]["return"])
        assert "m s-1" in ret_s
        assert "Freq" in ret_s
        assert "Dims" in ret_s
        assert "time" in ret_s
        assert "pixel" in ret_s
        assert "Dtype" in ret_s
        assert "float64" in ret_s
        assert "Coords" in ret_s
        assert "x" in ret_s

    def test_dryness_return_has_units_but_no_freq(self, node_driver):
        ret = str(_node_hints(node_driver)["dryness"]["return"])
        assert "1" in ret
        assert "Freq" not in ret

    def test_function_import_node_return_has_units_and_freq(self, node_driver):
        ret_s = str(_node_hints(node_driver)["from_math"]["return"])
        assert "1" in ret_s
        assert "Freq" in ret_s
