"""Tests for breadboard.dag.node — runtime-generated Hamilton modules."""

import sys
import types

import xarray as xr

from breadboard.config import NodeSpec
from breadboard.dag.node import _build_fn_code, make_node_module
from breadboard.units import units_from_signature


def _expr_spec(name, inputs, expression, units=None):
    return NodeSpec(
        name=name,
        inputs=list(inputs),
        expression=expression,
        import_path=None,
        function=None,
        units=units,
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

    def test_expression_return_type_annotation(self):
        code = _build_fn_code(_expr_spec("f", [], "0"))
        assert "xr.DataArray" in code

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
    """A declared `units` makes the node a typed, stamped producer."""

    def test_no_units_is_plain_passthrough(self):
        code = _build_fn_code(_expr_spec("f", ["a"], "a"))
        assert "-> xr.DataArray" in code
        assert "@declare_units" not in code

    def test_units_annotate_return_and_decorate(self):
        code = _build_fn_code(_expr_spec("f", ["a"], "a", units="g m-2 d-1"))
        assert "@declare_units" in code
        assert "Annotated[xr.DataArray, 'g m-2 d-1']" in code

    def test_units_stamped_on_output_at_runtime(self):
        mod = make_node_module([_expr_spec("scaled", ["a"], "a", units="t ha-1")])
        out = mod.scaled(xr.DataArray([1.0, 2.0]))
        assert out.attrs["units"] == "t ha-1"

    def test_declared_units_reachable_for_static_check(self):
        mod = make_node_module([_expr_spec("ratio", ["a", "b"], "a / b", units="1")])
        _, out_units = units_from_signature(mod.ratio)
        assert out_units == "1"
