"""Tests for breadboard.dag._hamilton_fixes."""

import sys
import types

import pytest
from hamilton import driver
from hamilton.function_modifiers.base import InvalidDecoratorException
from hamilton.settings import ENABLE_POWER_USER_MODE

from breadboard.dag._hamilton_fixes import NoOpDecorator


class TestNoOpDecorator:
    """NoOpDecorator is a transparent Hamilton NodeTransformer."""

    @pytest.fixture
    def dec(self):
        return NoOpDecorator()

    def test_validate_does_not_raise(self, dec):
        dec.validate(lambda: None)

    def test_transform_node_wraps_in_list(self, dec):
        sentinel = object()
        result = dec.transform_node(sentinel, {}, lambda: None)
        assert result == [sentinel]

    def test_transform_dag_returns_same_collection(self, dec):
        nodes = [object(), object()]
        result = dec.transform_dag(nodes, {}, lambda: None)
        assert result is nodes

    def test_select_nodes_is_empty(self, dec):
        nodes = [object(), object()]
        result = NoOpDecorator.select_nodes(None, nodes)  # type: ignore[arg-type]
        assert list(result) == []

    def test_allows_multiple_true(self):
        assert NoOpDecorator.allows_multiple() is True

    def test_lifecycle_name_is_transform(self):
        assert NoOpDecorator.get_lifecycle_name() == "transform"


class TestResolveValidatesReturnedDecorator:
    """Hamilton's standard ``@resolve`` must call ``validate()`` on the decorator
    returned from ``decorate_with``.

    This replaced our former ``FixedResolve`` workaround (apache-hamilton
    PR #1524, present since 1.90.0). ``resample.py`` relies on this so that a
    ``parameterize`` built from config is validated at driver-build time. This
    test guards against a future Hamilton bump regressing that behaviour.
    """

    @pytest.fixture
    def bad_module(self):
        # A standalone Hamilton module whose decorate_with returns a parameterize
        # referencing a parameter ('DOES_NOT_EXIST') that does not exist on the
        # decorated function. Hamilton only introspects modules registered in
        # sys.modules, so register it (with cleanup) before building a driver.
        src = (
            "import xarray as xr\n"
            "from hamilton.function_modifiers import (\n"
            "    ResolveAt, parameterize, resolve, source, value\n"
            ")\n"
            "@resolve(\n"
            "    when=ResolveAt.CONFIG_AVAILABLE,\n"
            "    decorate_with=lambda specs=None: parameterize(\n"
            "        bad_out={\n"
            "            'DOES_NOT_EXIST': value(1),\n"
            "            'var_in': source('x_daily'),\n"
            "        }\n"
            "    ),\n"
            ")\n"
            "def resample(var_in: xr.DataArray) -> xr.DataArray:\n"
            "    return var_in\n"
        )
        name = "_test_resolve_validate_mod"
        mod = types.ModuleType(name)
        mod.__file__ = f"{name}.py"
        exec(compile(src, mod.__file__, "exec"), mod.__dict__)
        sys.modules[name] = mod
        try:
            yield mod
        finally:
            del sys.modules[name]

    def test_invalid_parameterize_raises_at_build(self, bad_module):
        with pytest.raises(
            InvalidDecoratorException, match="don't appear in the function itself"
        ):
            (
                driver.Builder()
                .with_modules(bad_module)
                .with_config({"specs": [object()], ENABLE_POWER_USER_MODE: True})
                .build()
            )
