"""Tests for the general fan-out [[node]] mechanism and node contract decls."""

import xarray as xr
from xarray_annotated.schema import Dims, Dtype, schema_from_signature

from conduit.config import Config, NodeSpec, expand_node_entries
from conduit.dag.driver import build_driver
from conduit.dag.node import PASSTHROUGH_TAG, make_node_module


def _node(name, inputs, expression, **kw):
    return NodeSpec(
        name=name,
        inputs=list(inputs),
        expression=expression,
        import_path=None,
        function=None,
        **kw,
    )


class TestForEachExpansion:
    def test_substitutes_var_in_all_string_fields(self):
        entries = expand_node_entries(
            [
                {
                    "for_each": ["a", "b"],
                    "name": "{var}_out",
                    "inputs": ["{var}_in"],
                    "expression": "{var}_in * 2",
                }
            ]
        )
        assert [e["name"] for e in entries] == ["a_out", "b_out"]
        assert entries[0]["inputs"] == ["a_in"]
        assert entries[0]["expression"] == "a_in * 2"
        assert "for_each" not in entries[0]

    def test_entry_without_for_each_passes_through(self):
        entries = expand_node_entries([{"name": "x", "inputs": [], "expression": "1"}])
        assert len(entries) == 1
        assert entries[0]["name"] == "x"

    def test_config_fan_out_generates_and_runs(self):
        parsed = Config(
            {
                "node": [
                    {
                        "for_each": ["a", "b"],
                        "name": "{var}_doubled",
                        "inputs": ["{var}"],
                        "expression": "{var} * 2",
                    }
                ]
            }
        ).parse()
        assert {s.name for s in parsed.node_specs} == {
            "a_doubled",
            "b_doubled",
        }
        dr = build_driver(
            parsed.modules, parsed.driver_config, node_specs=parsed.node_specs
        )
        out = dr.execute(["a_doubled"], inputs={"a": xr.DataArray([1.0, 2.0])})
        assert list(out["a_doubled"].values) == [2.0, 4.0]

    def test_fan_out_name_collision_raises(self):
        import pytest

        config = Config(
            {
                "node": [
                    {
                        "for_each": ["a", "a"],
                        "name": "{var}_x",
                        "inputs": ["{var}"],
                        "expression": "{var}",
                    }
                ]
            }
        )
        with pytest.raises(ValueError, match="Duplicate node name"):
            config.parse()


class TestSchemaOnNode:
    def test_schema_markers_annotated_and_decorated(self):
        # annotate() builds the schema return contract and declare_schema is applied,
        # so both markers are readable off the built node's signature.
        mod = make_node_module(
            [_node("f", ["a"], "a", dims=["time", "x"], dtype="float64")]
        )
        _, out = schema_from_signature(mod.f)
        # annotate() emits markers in a fixed order (unit, dims, dtype, coords).
        assert out == [Dims("time", "x"), Dtype("float64")]

    def test_declared_dims_readable_from_generated_signature(self):
        mod = make_node_module([_node("f", ["a"], "a", dims=["time", "x"])])
        _, out = schema_from_signature(mod.f)
        assert out == [Dims("time", "x")]

    def test_config_parses_and_validates_dims_dtype(self):
        spec = (
            Config(
                {
                    "node": [
                        {
                            "name": "f",
                            "inputs": ["a"],
                            "expression": "a",
                            "dims": ["time", "x"],
                            "dtype": "float64",
                        }
                    ]
                }
            )
            .parse()
            .node_specs[0]
        )
        assert spec.dims == ["time", "x"]
        assert spec.dtype == "float64"

    def test_invalid_dtype_raises(self):
        import pytest

        config = Config(
            {
                "node": [
                    {"name": "f", "inputs": ["a"], "expression": "a", "dtype": "nope"}
                ]
            }
        )
        with pytest.raises(ValueError, match="invalid dtype"):
            config.parse()


class TestPassthroughNode:
    def test_passthrough_is_tagged_and_undeclared(self):
        mod = make_node_module([_node("p", ["x"], "x", passthrough=True)])
        # Tagged for the contract check to propagate its input's declaration ...
        (tag_deco,) = mod.p.__dict__["decorate_nodes"]
        assert tag_deco.tags[PASSTHROUGH_TAG] == "true"
        # ... and declares no contract of its own (bare DataArray return).
        assert mod.p.__annotations__["return"] is xr.DataArray
        _, out = schema_from_signature(mod.p)
        assert out is None
