"""Tests for catena.nodegen — runtime-generated Hamilton modules."""

import sys
import types

import pytest
import xarray as xr
import xarray_annotated as xra

from catena.config import NodeSpec
from catena.nodegen import _build_fn_code, _node_namespace, make_node_module
from catena.specs import RESERVED_NODE_NAMES


def test_reserved_names_match_generated_namespace():
    # The parser rejects node names in RESERVED_NODE_NAMES; that set is only
    # correct if it is exactly what the generated module's namespace binds.
    assert set(_node_namespace()) == RESERVED_NODE_NAMES


def _expr_spec(name, inputs, expression, units=None, passthrough=False):
    return NodeSpec(
        name=name,
        inputs=list(inputs),
        expression=expression,
        import_path=None,
        function=None,
        units=units,
        passthrough=passthrough,
    )


def _fn_spec(name, inputs, import_path, function):
    return NodeSpec(
        name=name,
        inputs=list(inputs),
        expression=None,
        import_path=import_path,
        function=function,
    )


class TestBuildFnCode:
    """_build_fn_code produces valid Python source for both spec types."""

    def test_expression_def_signature(self):
        code = _build_fn_code(_expr_spec("my_sum", ["a", "b"], "a + b"))
        assert "def my_sum(" in code

    def test_expression_parameters_typed_any(self):
        code = _build_fn_code(_expr_spec("f", ["x", "y"], "x"))
        assert "x: Any" in code
        assert "y: Any" in code

    def test_expression_return_line(self):
        code = _build_fn_code(_expr_spec("f", ["a"], "a * 2"))
        assert "return a * 2" in code

    def test_expression_bare_def_has_no_return_annotation(self):
        # The contract is attached later by make_node_module, not baked into source.
        code = _build_fn_code(_expr_spec("f", [], "0"))
        assert "->" not in code

    def test_function_spec_contains_import_module_call(self):
        code = _build_fn_code(_fn_spec("result", ["x"], "math", "sqrt"))
        assert "import_module" in code

    def test_function_spec_contains_module_path(self):
        code = _build_fn_code(_fn_spec("result", ["x"], "some.pkg", "fn"))
        assert "'some.pkg'" in code

    def test_function_spec_contains_function_name(self):
        code = _build_fn_code(_fn_spec("result", ["x"], "math", "my_func"))
        assert "'my_func'" in code

    def test_function_spec_passes_kwargs(self):
        code = _build_fn_code(_fn_spec("result", ["a", "b"], "mod", "fn"))
        assert "a=a" in code
        assert "b=b" in code


class TestMakeNodeModule:
    """make_node_module creates a Hamilton-compatible module at runtime."""

    def test_returns_module_type(self):
        mod = make_node_module([_expr_spec("f", [], "None")])
        assert isinstance(mod, types.ModuleType)

    def test_module_registered_in_sys_modules(self):
        mod = make_node_module([_expr_spec("sentinel_fn", [], "'ok'")])
        assert mod.__name__ in sys.modules

    def test_repeated_builds_do_not_accumulate_modules(self):
        # A random per-build name leaked one sys.modules entry per build, which is
        # unbounded in a long-lived process (a calibration loop, a test session).
        specs = [_expr_spec("acc_probe", ["a"], "a * 2")]
        before = {n for n in sys.modules if n.startswith("catena_node_generated")}
        for _ in range(5):
            make_node_module(specs)
        after = {n for n in sys.modules if n.startswith("catena_node_generated")}
        assert len(after - before) <= 1

    def test_different_specs_get_different_modules(self):
        a = make_node_module([_expr_spec("x", ["a"], "a")])
        b = make_node_module([_expr_spec("x", ["a"], "a * 2")])
        assert a.__name__ != b.__name__

    def test_same_specs_get_the_same_module_name(self):
        a = make_node_module([_expr_spec("y", ["a"], "a")])
        b = make_node_module([_expr_spec("y", ["a"], "a")])
        assert a.__name__ == b.__name__

    def test_expression_function_is_callable(self):
        mod = make_node_module([_expr_spec("add", ["a", "b"], "a + b")])
        assert callable(mod.add)

    def test_expression_function_evaluates_correctly(self):
        mod = make_node_module([_expr_spec("add", ["a", "b"], "a + b")])
        assert mod.add(3, 4) == 7

    def test_function_spec_dispatches_to_callable(self):
        # dict(x=42) → {"x": 42}; builtins.dict accepts arbitrary kwargs
        mod = make_node_module([_fn_spec("make_dict", ["x"], "builtins", "dict")])
        assert mod.make_dict(42) == {"x": 42}

    def test_function_module_attr_set(self):
        mod = make_node_module([_expr_spec("g", [], "42")])
        assert mod.g.__module__ == mod.__name__

    def test_multiple_specs_attach_all_functions(self):
        specs = [
            _expr_spec("double", ["x"], "x * 2"),
            _expr_spec("negate", ["x"], "-x"),
        ]
        mod = make_node_module(specs)
        assert mod.double(5) == 10
        assert mod.negate(5) == -5

    def test_empty_spec_list_creates_empty_module(self):
        mod = make_node_module([])
        assert isinstance(mod, types.ModuleType)
        # No function attrs expected
        public_attrs = [a for a in dir(mod) if not a.startswith("_")]
        assert len(public_attrs) == 0


class TestNodeUnits:
    """A declared `units` makes the node a typed producer, checked when it runs."""

    def test_no_units_is_plain_passthrough(self):
        mod = make_node_module([_expr_spec("f", ["a"], "a")])
        # A bare DataArray return and no declared unit.
        assert mod.f.__annotations__["return"] is xr.DataArray
        _, out = xra.declarations_from_signature(mod.f)
        assert out is None

    def test_declared_units_reachable_for_static_check(self):
        mod = make_node_module([_expr_spec("ratio", ["a", "b"], "a / b", units="1")])
        _, out = xra.declarations_from_signature(mod.ratio)
        assert out == xra.Declared(unit=xra.Unit("1"))

    def test_output_already_in_the_declared_unit_passes(self):
        mod = make_node_module([_expr_spec("f", ["a"], "a", units="g m-2 d-1")])
        with xra.enabled(True):
            out = mod.f(xr.DataArray([1.0], attrs={"units": "g m-2 d-1"}))
        assert out.attrs["units"] == "g m-2 d-1"

    def test_output_with_no_unit_raises(self):
        mod = make_node_module([_expr_spec("f", ["a"], "a", units="t ha-1")])
        with (
            xra.enabled(True),
            pytest.raises(xra.units.UnitError, match="no 'units' attribute"),
        ):
            mod.f(xr.DataArray([1.0]))

    def test_output_with_a_stale_unit_raises(self):
        mod = make_node_module([_expr_spec("f", ["a"], "a * 0.01", units="hPa")])
        with (
            xra.enabled(True),
            pytest.raises(xra.units.UnitError, match="differs from declared"),
        ):
            mod.f(xr.DataArray([1.0], attrs={"units": "Pa"}))

    @pytest.mark.parametrize("passthrough", [False, True])
    def test_node_declaring_nothing_is_left_unwrapped(self, passthrough):
        spec = _expr_spec("f", ["a"], "a", passthrough=passthrough)
        assert not hasattr(make_node_module([spec]).f, "__wrapped__")

    def test_expression_states_a_changed_unit(self):
        expression = "(a * 0.01).assign_attrs(units='hPa')"
        mod = make_node_module([_expr_spec("f", ["a"], expression, units="hPa")])
        with xra.enabled(True):
            out = mod.f(xr.DataArray([100.0], attrs={"units": "Pa"}))
        assert out.attrs["units"] == "hPa"

    def test_expression_can_convert_with_xra(self):
        expression = "xra.units.convert(a, 'hPa')"
        mod = make_node_module([_expr_spec("f", ["a"], expression, units="hPa")])
        with xra.enabled(True):
            out = mod.f(xr.DataArray([100.0], attrs={"units": "Pa"}))
        assert out.attrs["units"] == "hPa"
        assert out.item() == pytest.approx(1.0)

    def test_xra_is_refused_as_a_node_name(self):
        with pytest.raises(ValueError, match="reserved"):
            NodeSpec.from_config({"name": "xra", "inputs": [], "expression": "0"})
