"""Tests for the build-time (static) DAG unit-consistency check."""

import sys
import types
import warnings
from typing import Annotated, TypedDict

import numpy as np
import pytest
import xarray as xr
from hamilton import driver
from hamilton.function_modifiers import extract_fields
from hamilton.settings import ENABLE_POWER_USER_MODE
from xarray_annotated.schema import Coords, Dims, Dtype, SchemaError
from xarray_annotated.units import declare_units, policy

from conduit.config import NodeSpec, ResampleSpec
from conduit.dag.contract_check import (
    check_dag_contracts,
    check_dag_units,
    check_input_contracts,
)
from conduit.dag.driver import build_driver


def _da():
    return xr.DataArray([1.0])


@pytest.fixture
def register():
    """Build Hamilton-scannable modules from functions and clean up afterwards.

    Hamilton only picks up a module's functions when they live in ``sys.modules``
    and their ``__module__`` matches the module name (mirrors ``node.py``).
    """
    names: list[str] = []

    def _make(name: str, *funcs) -> types.ModuleType:
        mod = types.ModuleType(name)
        for fn in funcs:
            fn.__module__ = name
            setattr(mod, fn.__name__, fn)
        sys.modules[name] = mod
        names.append(name)
        return mod

    yield _make

    for name in names:
        sys.modules.pop(name, None)


def _build(*mods) -> driver.Driver:
    return (
        driver.Builder()
        .with_modules(*mods)
        .with_config({ENABLE_POWER_USER_MODE: True})
        .build()
    )


def _producer(unit: str):
    """A node producing ``gpp_weekly`` with the given declared output unit."""

    class Out(TypedDict):
        gpp_weekly: Annotated[xr.DataArray, unit]

    @extract_fields()
    @declare_units
    def producer() -> Out:  # type: ignore[valid-type]
        return {"gpp_weekly": _da()}

    return producer


def _consumer(unit: str, name: str = "consumer", in_name: str = "gpp_weekly"):
    """A node consuming ``in_name`` with the given declared input unit.

    Built via ``exec`` so the consumed parameter (= the upstream node name) and
    the function name are both dynamic. The output node is named ``f"{name}_out"``
    so multiple consumers can coexist in one graph without a name collision.
    """
    src = (
        "from typing import Annotated, TypedDict\n"
        "import xarray as xr\n"
        "from hamilton.function_modifiers import extract_fields\n"
        "from xarray_annotated.units import declare_units\n"
        f"class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, 't ha-1']\n"
        "@extract_fields()\n"
        "@declare_units\n"
        f"def {name}({in_name}: Annotated[xr.DataArray, {unit!r}]) -> _Out:\n"
        f"    return {{{name + '_out'!r}: {in_name}}}\n"
    )
    ns: dict = {}
    exec(src, ns)
    return ns[name]


def _bare_producer(unit: str, name: str = "flux"):
    """A *single-output* node producing ``name`` via a bare ``Annotated`` return.

    Unlike :func:`_producer` (a ``TypedDict`` + ``extract_fields`` multi-output
    node), this exercises the static check's other producer shape: a node whose
    own name *is* the produced variable and whose unit is the bare return
    annotation. Future model components may use either shape.
    """
    src = (
        "from typing import Annotated\n"
        "import xarray as xr\n"
        "from xarray_annotated.units import declare_units\n"
        "@declare_units\n"
        f"def {name}() -> Annotated[xr.DataArray, {unit!r}]:\n"
        "    return xr.DataArray([1.0])\n"
    )
    ns: dict = {}
    exec(src, ns)
    return ns[name]


def _plain_consumer(name: str = "plain_cons", in_name: str = "gpp_weekly"):
    """A consumer of ``in_name`` that declares **no** unit on the input.

    Used to pin the opt-in contract: an un-annotated consumer of a typed
    producer contributes no declaration, so the edge is not checked.
    """
    src = (
        "from typing import Annotated, TypedDict\n"
        "import xarray as xr\n"
        "from hamilton.function_modifiers import extract_fields\n"
        "from xarray_annotated.units import declare_units\n"
        f"class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, 't ha-1']\n"
        "@extract_fields()\n"
        "@declare_units\n"
        f"def {name}({in_name}: xr.DataArray) -> _Out:\n"
        f"    return {{{name + '_out'!r}: {in_name}}}\n"
    )
    ns: dict = {}
    exec(src, ns)
    return ns[name]


# ---------------------------------------------------------------------------
# Dimensional incompatibility (always a finding)
# ---------------------------------------------------------------------------


class TestDimensionalMismatch:
    def _dr(self, register):
        prod = register("uc_prod", _producer("g m-2 d-1"))
        cons = register("uc_cons", _consumer("kg"))
        return _build(prod, cons)

    def test_strict_raises(self, register):
        dr = self._dr(register)
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_units(dr)

    def test_warn_also_raises(self, register):
        dr = self._dr(register)
        with (
            policy(enabled=True, on_missing="warn"),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_units(dr)

    def test_off_is_silent(self, register):
        dr = self._dr(register)
        with policy(enabled=False), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_units(dr)

    def test_message_names_node_and_units(self, register):
        dr = self._dr(register)
        with policy(enabled=True), pytest.raises(ValueError, match="gpp_weekly") as exc:
            check_dag_units(dr)
        msg = str(exc.value)
        assert "'g m-2 d-1'" in msg
        assert "'kg'" in msg


# ---------------------------------------------------------------------------
# Exact-string mismatch (only when on_inexact is "error")
# ---------------------------------------------------------------------------


class TestExactMatch:
    def _dr(self, register):
        prod = register("ue_prod", _producer("Pa"))
        cons = register("ue_cons", _consumer("hPa"))
        return _build(prod, cons)

    def test_compatible_passes_when_convert(self, register):
        dr = self._dr(register)
        with policy(enabled=True, on_inexact="convert"), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_units(dr)

    def test_compatible_flagged_when_error(self, register):
        dr = self._dr(register)
        with (
            policy(enabled=True, on_inexact="error"),
            pytest.raises(ValueError, match="exact match required"),
        ):
            check_dag_units(dr)


# ---------------------------------------------------------------------------
# Shared external input consumed with conflicting units (no producer)
# ---------------------------------------------------------------------------


class TestSharedInputConflict:
    def test_conflicting_consumers_flagged(self, register):
        a = register("us_a", _consumer("Pa", name="consumer_a"))
        b = register("us_b", _consumer("kg", name="consumer_b"))
        dr = _build(a, b)
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_units(dr)


# ---------------------------------------------------------------------------
# Consistent declarations pass (synthetic + real models)
# ---------------------------------------------------------------------------


class TestBareReturnProducer:
    """A single-output node (bare ``Annotated`` return) is a checkable producer.

    The existing producer tests all use ``TypedDict`` + ``extract_fields``; this
    covers the other node shape so the static check stays robust to model
    components that emit a single declared output.
    """

    def _dr(self, register, prod_unit, cons_unit):
        prod = register("br_prod", _bare_producer(prod_unit, name="flux"))
        cons = register("br_cons", _consumer(cons_unit, in_name="flux"))
        return _build(prod, cons)

    def test_incompatible_raises(self, register):
        dr = self._dr(register, "g m-2 d-1", "kg")
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_units(dr)

    def test_compatible_passes_under_exact(self, register):
        dr = self._dr(register, "g m-2 d-1", "g m-2 d-1")
        with (
            policy(enabled=True, on_inexact="error"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error")
            check_dag_units(dr)

    def test_exact_string_mismatch_flagged(self, register):
        dr = self._dr(register, "Pa", "hPa")
        with (
            policy(enabled=True, on_inexact="error"),
            pytest.raises(ValueError, match="exact match required"),
        ):
            check_dag_units(dr)


class TestOptInContract:
    """Unit checking is opt-in per edge: an edge is only compared when *both*
    sides declare a unit. An un-annotated consumer (or producer) is skipped, so
    partially-annotated future models never trigger false positives."""

    def test_unannotated_consumer_of_typed_producer_not_checked(self, register):
        prod = register("oc_prod", _producer("Pa"))
        cons = register("oc_cons", _plain_consumer())
        dr = _build(prod, cons)
        with (
            policy(enabled=True, on_inexact="error"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error")
            check_dag_units(dr)


class TestDefaultResolution:
    """``check_dag_units`` resolves ``on_inexact`` from the global state when
    its argument is left as ``None`` (the path ``build_driver`` relies on)."""

    def test_dimension_mismatch_raises_when_enabled(self, register):
        prod = register("dm_prod", _producer("g m-2 d-1"))
        cons = register("dm_cons", _consumer("kg"))
        dr = _build(prod, cons)
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="incompatible"),
        ):
            check_dag_units(dr)

    def test_off_global_skips(self, register):
        prod = register("dm2_prod", _producer("g m-2 d-1"))
        cons = register("dm2_cons", _consumer("kg"))
        dr = _build(prod, cons)
        with policy(enabled=False), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_units(dr)

    def test_on_inexact_resolves_from_global(self, register):
        prod = register("de_prod", _producer("Pa"))
        cons = register("de_cons", _consumer("hPa"))
        dr = _build(prod, cons)
        with (
            policy(enabled=True, on_inexact="error"),
            pytest.raises(ValueError, match="exact match required"),
        ):
            check_dag_units(dr)


class TestConsistent:
    def test_matching_units_pass_even_under_exact(self, register):
        prod = register("uk_prod", _producer("Pa"))
        cons = register("uk_cons", _consumer("Pa"))
        dr = _build(prod, cons)
        with (
            policy(enabled=True, on_inexact="error"),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error")
            check_dag_units(dr)

    def test_producer_consumer_same_unit_clean(self, register):
        register("clean_prod", _producer("g m-2 d-1"))
        register("clean_cons", _consumer("g m-2 d-1"))
        with policy(enabled=True, on_inexact="error"):
            dr = build_driver(["clean_prod", "clean_cons"], {})
        check_dag_units(dr, on_inexact="error")


# ---------------------------------------------------------------------------
# build_driver invokes the check (gated by the global policy)
# ---------------------------------------------------------------------------


class TestBuildDriverIntegration:
    def test_build_driver_runs_check_when_enabled(self, register):
        register("ub_prod", _producer("g m-2 d-1"))
        register("ub_cons", _consumer("kg"))
        with (
            policy(enabled=True, on_inexact="error"),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            build_driver(["ub_prod", "ub_cons"], {})

    def test_build_driver_skips_when_disabled(self, register):
        register("ub2_prod", _producer("g m-2 d-1"))
        register("ub2_cons", _consumer("kg"))
        with policy(enabled=False):
            build_driver(["ub2_prod", "ub2_cons"], {})


# ---------------------------------------------------------------------------
# Resample propagation: a resampled var inherits its source's unit
# ---------------------------------------------------------------------------


def _resample_node_specs(*specs):
    """Desugar ResampleSpecs into fan-out passthrough node specs (as config does)."""
    from conduit.config import expand_node_entries, resample_to_node_entry

    entries = [resample_to_node_entry(s) for s in specs]
    return [NodeSpec.from_config(e) for e in expand_node_entries(entries)]


class TestResamplePropagation:
    """A producer emits ``gpp_weekly`` ('g m-2 d-1'); a passthrough resample to
    ``gpp_monthly`` should propagate that unit so a downstream consumer is
    checked against it."""

    def _build(self, register, consumer_unit):
        register("rs_prod", _producer("g m-2 d-1"))  # produces gpp_weekly
        register("rs_cons", _consumer(consumer_unit, in_name="gpp_monthly"))
        specs = _resample_node_specs(
            ResampleSpec(vars=["gpp"], source_freq="weekly", target_freq="monthly")
        )
        return build_driver(["rs_prod", "node", "rs_cons"], {"node_specs": specs})

    def test_incompatible_consumer_of_resampled_var_raises(self, register):
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="gpp_monthly"),
        ):
            self._build(register, "kg")

    def test_compatible_consumer_of_resampled_var_passes(self, register):
        with policy(enabled=True):
            self._build(register, "g m-2 d-1")

    def test_chained_resample_propagates_through_multiple_hops(self, register):
        """The unit must propagate across a *chain* of resamples
        (daily -> weekly -> monthly), exercising the fixpoint loop, so a
        consumer of the twice-resampled variable is still checked."""

        class _P(TypedDict):
            gpp_daily: Annotated[xr.DataArray, "g m-2 d-1"]

        @extract_fields()
        @declare_units
        def prod() -> _P:  # type: ignore[valid-type]
            return {"gpp_daily": _da()}

        register("crp_prod", prod)
        register("crp_cons", _consumer("kg", in_name="gpp_monthly"))
        specs = _resample_node_specs(
            ResampleSpec(vars=["gpp"], source_freq="daily", target_freq="weekly"),
            ResampleSpec(vars=["gpp"], source_freq="weekly", target_freq="monthly"),
        )
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="gpp_monthly"),
        ):
            build_driver(["crp_prod", "node", "crp_cons"], {"node_specs": specs})


# ---------------------------------------------------------------------------
# Node: a declared `units=` makes the node a checkable producer
# ---------------------------------------------------------------------------


class TestNodePropagation:
    def _build(self, register, consumer_unit):
        register("dv_cons", _consumer(consumer_unit, in_name="flux"))
        specs = [
            NodeSpec(
                name="flux",
                inputs=["a", "b"],
                expression="a + b",
                import_path=None,
                function=None,
                units="g m-2 d-1",
            )
        ]
        return build_driver(["node", "dv_cons"], {"node_specs": specs})

    def test_incompatible_consumer_of_node_var_raises(self, register):
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="flux"),
        ):
            self._build(register, "kg")

    def test_compatible_consumer_of_node_var_passes(self, register):
        with policy(enabled=True):
            self._build(register, "g m-2 d-1")


# ---------------------------------------------------------------------------
# UnitsWarning: runtime decorator path includes node qualname in message
# ---------------------------------------------------------------------------


class TestUnitsWarningQualname:
    """The node function's qualname appears in UnitsWarning messages emitted by
    the @declare_units runtime wrapper, making the source of the warning clear
    without requiring the user to inspect the conduit call stack."""

    def test_missing_units_warning_includes_qualname(self):
        from typing import Annotated

        from xarray_annotated.units import UnitsWarning

        @declare_units
        def my_model_node(vpd: Annotated[xr.DataArray, "Pa"]) -> xr.DataArray:
            return vpd

        da = xr.DataArray([1.0])  # no 'units' attr
        with (
            policy(enabled=True, on_missing="warn"),
            pytest.warns(UnitsWarning, match=r"\[.*my_model_node\].*unvalidated"),
        ):
            my_model_node(vpd=da)

    def test_unparseable_units_warning_includes_qualname(self):
        from typing import Annotated

        from xarray_annotated.units import UnitsWarning

        @declare_units
        def another_node(vpd: Annotated[xr.DataArray, "Pa"]) -> xr.DataArray:
            return vpd

        da = xr.DataArray([1.0], attrs={"units": "fraction"})
        with (
            policy(enabled=True, on_missing="warn"),
            pytest.warns(UnitsWarning, match=r"\[.*another_node\].*unparseable"),
        ):
            another_node(vpd=da)


# ---------------------------------------------------------------------------
# Schema facets (dims / dtype / coords): the DAG check is facet-generic
# ---------------------------------------------------------------------------


def _schema_producer(name: str, *markers):
    """A single-output node producing ``name`` with the given schema markers."""

    def prod() -> Annotated[(xr.DataArray, *markers)]:  # type: ignore[valid-type]
        return _da()

    prod.__name__ = name
    return prod


def _schema_consumer(*markers, in_name: str = "arr"):
    """A node consuming ``in_name`` declaring the given schema markers on it."""
    src = (
        "from typing import Annotated\n"
        "import xarray as xr\n"
        f"def cons({in_name}: Annotated[(xr.DataArray, *_markers)]) -> xr.DataArray:\n"
        f"    return {in_name}\n"
    )
    ns: dict = {"_markers": markers}
    exec(src, ns)
    return ns["cons"]


class TestSchemaDagCheck:
    """The build-time edge check compares dims and dtype markers, always raising
    ``ValueError`` on a provable mismatch (a pipeline-definition error)."""

    def _dr(self, register, prod_markers, cons_markers):
        prod = register("scd_prod", _schema_producer("arr", *prod_markers))
        cons = register("scd_cons", _schema_consumer(*cons_markers))
        return _build(prod, cons)

    def test_dim_sets_differ_raises(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("time", "y")])
        with policy(enabled=True), pytest.raises(ValueError, match="dims incompatible"):
            check_dag_contracts(dr)

    def test_dim_order_differ_raises_when_both_ordered(self, register):
        dr = self._dr(
            register,
            [Dims("time", "x", ordered=True)],
            [Dims("x", "time", ordered=True)],
        )
        with policy(enabled=True), pytest.raises(ValueError, match="dims incompatible"):
            check_dag_contracts(dr)

    def test_same_dim_set_any_order_passes(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("x", "time")])
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_dtype_kinds_differ_raises(self, register):
        dr = self._dr(register, [Dtype("float64")], [Dtype("int32")])
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="dtypes incompatible"),
        ):
            check_dag_contracts(dr)

    def test_same_dtype_kind_passes(self, register):
        dr = self._dr(register, [Dtype("float64")], [Dtype("float32")])
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_coords_are_not_checked_at_edges(self, register):
        # Coords are lower bounds, so mismatched coord declarations never raise.
        dr = self._dr(register, [Coords("time")], [Coords("time", "lat")])
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_disabled_skips_schema(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("time", "y")])
        with policy(enabled=False), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)


class TestSchemaInputCheck:
    """``check_input_contracts`` validates a loaded array's dims/dtype/coords
    against its consumer's declaration, from file metadata alone."""

    def _dr(self, register, *markers):
        cons = register("sci_cons", _schema_consumer(*markers))
        return _build(cons)

    def test_dim_mismatch_raises(self, register):
        dr = self._dr(register, Dims("time", "x"))
        bad = xr.DataArray(np.zeros((2, 3)), dims=("time", "y"))
        with policy(enabled=True), pytest.raises(SchemaError, match="dims"):
            check_input_contracts(dr, {"arr": bad})

    def test_dim_match_passes(self, register):
        dr = self._dr(register, Dims("time", "x"))
        good = xr.DataArray(np.zeros((2, 3)), dims=("time", "x"))
        with policy(enabled=True):
            check_input_contracts(dr, {"arr": good})

    def test_dtype_kind_mismatch_raises(self, register):
        dr = self._dr(register, Dtype("float64"))
        bad = xr.DataArray(np.zeros((3,), dtype="int64"), dims=("x",))
        with policy(enabled=True), pytest.raises(SchemaError, match="dtype"):
            check_input_contracts(dr, {"arr": bad})
