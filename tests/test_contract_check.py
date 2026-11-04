"""Tests for the build-time (static) DAG unit-consistency check."""

import sys
import types
from typing import Annotated, TypedDict

import numpy as np
import pytest
import xarray as xr
import xarray_annotated as xra
from hamilton import driver
from hamilton.function_modifiers import extract_fields
from hamilton.settings import ENABLE_POWER_USER_MODE
from xarray_annotated.schema import Coords, Dims, Dtype

from catena.build import build_driver
from catena.config import NodeSpec, ResampleSpec
from catena.contract_check import (
    check_dag_contracts,
    check_input_contracts,
)
from catena.errors import CatenaValueError


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
        gpp_weekly: Annotated[xr.DataArray, xra.Unit(unit)]

    @extract_fields()
    @xra.enforce
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
        "import xarray_annotated as xra\n"
        f"class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, xra.Unit('t ha-1')]\n"
        "@extract_fields()\n"
        "@xra.enforce\n"
        f"def {name}({in_name}: Annotated[xr.DataArray, xra.Unit({unit!r})]) -> _Out:\n"
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
        "import xarray_annotated as xra\n"
        "@xra.enforce\n"
        f"def {name}() -> Annotated[xr.DataArray, xra.Unit({unit!r})]:\n"
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
        "import xarray_annotated as xra\n"
        f"class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, xra.Unit('t ha-1')]\n"
        "@extract_fields()\n"
        "@xra.enforce\n"
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
            xra.enabled(True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_contracts(dr)

    def test_off_is_silent(self, register):
        dr = self._dr(register)
        with xra.enabled(False):
            check_dag_contracts(dr)

    def test_message_names_node_and_units(self, register):
        dr = self._dr(register)
        with xra.enabled(True), pytest.raises(ValueError, match="gpp_weekly") as exc:
            check_dag_contracts(dr)
        msg = str(exc.value)
        assert "'g m-2 d-1'" in msg
        assert "'kg'" in msg


# ---------------------------------------------------------------------------
# Compatible but unequal units (nothing converts them between nodes)
# ---------------------------------------------------------------------------


class TestExactMatch:
    def _dr(self, register):
        prod = register("ue_prod", _producer("Pa"))
        cons = register("ue_cons", _consumer("hPa"))
        return _build(prod, cons)

    def test_compatible_flagged(self, register):
        dr = self._dr(register)
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="exact match required"),
        ):
            check_dag_contracts(dr)

    def test_compatible_fails_the_build(self, register):
        register("ue2_prod", _producer("m"))
        register("ue2_cons", _consumer("km"))
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="exact match required"),
        ):
            build_driver(["ue2_prod", "ue2_cons"], {})

    def test_different_spellings_of_one_unit_pass(self, register):
        prod = register("ue3_prod", _producer("Pa"))
        cons = register("ue3_cons", _consumer("pascal"))
        with xra.enabled(True):
            check_dag_contracts(_build(prod, cons))


# ---------------------------------------------------------------------------
# Shared external input consumed with conflicting units (no producer)
# ---------------------------------------------------------------------------


class TestSharedInputConflict:
    def test_conflicting_consumers_flagged(self, register):
        a = register("us_a", _consumer("Pa", name="consumer_a"))
        b = register("us_b", _consumer("kg", name="consumer_b"))
        dr = _build(a, b)
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_contracts(dr)


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
            xra.enabled(True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_contracts(dr)

    def test_equal_units_pass(self, register):
        dr = self._dr(register, "g m-2 d-1", "g m-2 d-1")
        with (
            xra.enabled(True),
        ):
            check_dag_contracts(dr)

    def test_exact_string_mismatch_flagged(self, register):
        dr = self._dr(register, "Pa", "hPa")
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="exact match required"),
        ):
            check_dag_contracts(dr)


class TestOptInContract:
    """Unit checking is opt-in per edge: an edge is only compared when *both*
    sides declare a unit. An un-annotated consumer (or producer) is skipped, so
    partially-annotated future models never trigger false positives."""

    def test_unannotated_consumer_of_typed_producer_not_checked(self, register):
        prod = register("oc_prod", _producer("Pa"))
        cons = register("oc_cons", _plain_consumer())
        dr = _build(prod, cons)
        with (
            xra.enabled(True),
        ):
            check_dag_contracts(dr)


class TestSwitch:
    """The checks follow xarray-annotated's on/off switch, block over variable."""

    def _dr(self, register):
        prod = register("sw_prod", _producer("g m-2 d-1"))
        cons = register("sw_cons", _consumer("kg"))
        return _build(prod, cons)

    def test_variable_off_skips_both_checks(self, register, monkeypatch):
        monkeypatch.setenv("XARRAY_ANNOTATED_ENABLED", "false")
        dr = self._dr(register)
        check_dag_contracts(dr)
        check_input_contracts(dr, {"gpp_weekly": xr.DataArray([1.0])})

    def test_variable_unset_checks(self, register, monkeypatch):
        monkeypatch.delenv("XARRAY_ANNOTATED_ENABLED")
        with pytest.raises(CatenaValueError, match="incompatible"):
            check_dag_contracts(self._dr(register))

    def test_block_off_beats_variable_on(self, register, monkeypatch):
        monkeypatch.setenv("XARRAY_ANNOTATED_ENABLED", "true")
        dr = self._dr(register)
        with xra.enabled(False):
            check_dag_contracts(dr)
            check_input_contracts(dr, {"gpp_weekly": xr.DataArray([1.0])})

    def test_block_on_beats_variable_off(self, register, monkeypatch):
        monkeypatch.setenv("XARRAY_ANNOTATED_ENABLED", "false")
        dr = self._dr(register)
        with xra.enabled(True), pytest.raises(CatenaValueError, match="incompatible"):
            check_dag_contracts(dr)
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="no 'units' attribute"),
        ):
            check_input_contracts(dr, {"gpp_weekly": xr.DataArray([1.0])})


class TestConsistent:
    def test_matching_units_pass(self, register):
        prod = register("uk_prod", _producer("Pa"))
        cons = register("uk_cons", _consumer("Pa"))
        dr = _build(prod, cons)
        with (
            xra.enabled(True),
        ):
            check_dag_contracts(dr)

    def test_producer_consumer_same_unit_clean(self, register):
        register("clean_prod", _producer("g m-2 d-1"))
        register("clean_cons", _consumer("g m-2 d-1"))
        with xra.enabled(True):
            dr = build_driver(["clean_prod", "clean_cons"], {})
            check_dag_contracts(dr)


# ---------------------------------------------------------------------------
# build_driver invokes the check (gated by the switch)
# ---------------------------------------------------------------------------


class TestBuildDriverIntegration:
    def test_build_driver_runs_check_when_enabled(self, register):
        register("ub_prod", _producer("g m-2 d-1"))
        register("ub_cons", _consumer("kg"))
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            build_driver(["ub_prod", "ub_cons"], {})

    def test_build_driver_skips_when_disabled(self, register):
        register("ub2_prod", _producer("g m-2 d-1"))
        register("ub2_cons", _consumer("kg"))
        with xra.enabled(False):
            build_driver(["ub2_prod", "ub2_cons"], {})


# ---------------------------------------------------------------------------
# Resample propagation: a resampled var inherits its source's unit
# ---------------------------------------------------------------------------


def _resample_node_specs(*specs):
    """Desugar ResampleSpecs into fan-out passthrough node specs (as config does)."""
    from catena.config import expand_node_entries, resample_to_node_entry

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
            ResampleSpec(vars=["gpp"], source="weekly", target="monthly", freq="1ME")
        )
        return build_driver(["rs_prod", "node", "rs_cons"], {}, node_specs=specs)

    def test_incompatible_consumer_of_resampled_var_raises(self, register):
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="gpp_monthly"),
        ):
            self._build(register, "kg")

    def test_compatible_consumer_of_resampled_var_passes(self, register):
        with xra.enabled(True):
            self._build(register, "g m-2 d-1")

    def test_chained_resample_propagates_through_multiple_hops(self, register):
        """The unit must propagate across a *chain* of resamples
        (daily -> weekly -> monthly), exercising the fixpoint loop, so a
        consumer of the twice-resampled variable is still checked."""

        class _P(TypedDict):
            gpp_daily: Annotated[xr.DataArray, xra.Unit("g m-2 d-1")]

        @extract_fields()
        @xra.enforce
        def prod() -> _P:  # type: ignore[valid-type]
            return {"gpp_daily": _da()}

        register("crp_prod", prod)
        register("crp_cons", _consumer("kg", in_name="gpp_monthly"))
        specs = _resample_node_specs(
            ResampleSpec(vars=["gpp"], source="daily", target="weekly", freq="7D"),
            ResampleSpec(vars=["gpp"], source="weekly", target="monthly", freq="1ME"),
        )
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="gpp_monthly"),
        ):
            build_driver(["crp_prod", "node", "crp_cons"], {}, node_specs=specs)


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
        return build_driver(["node", "dv_cons"], {}, node_specs=specs)

    def test_incompatible_consumer_of_node_var_raises(self, register):
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="flux"),
        ):
            self._build(register, "kg")

    def test_compatible_consumer_of_node_var_passes(self, register):
        with xra.enabled(True):
            self._build(register, "g m-2 d-1")


# ---------------------------------------------------------------------------
# Runtime: a failing input names the node it was declared on
# ---------------------------------------------------------------------------


class TestRuntimeQualname:
    def test_missing_units_error_includes_qualname(self):
        @xra.enforce
        def my_model_node(vpd: Annotated[xr.DataArray, xra.Unit("Pa")]) -> xr.DataArray:
            return vpd

        with (
            xra.enabled(True),
            pytest.raises(ValueError, match=r"\[.*my_model_node\].*no 'units'"),
        ):
            my_model_node(vpd=xr.DataArray([1.0]))

    def test_unparseable_units_error_includes_qualname(self):
        @xra.enforce
        def another_node(vpd: Annotated[xr.DataArray, xra.Unit("Pa")]) -> xr.DataArray:
            return vpd

        da = xr.DataArray([1.0], attrs={"units": "fraction"})
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match=r"\[.*another_node\].*unparseable"),
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


def _named_schema_consumer(fn_name: str, *markers, in_name: str = "arr"):
    """A named node consuming ``in_name``, declaring the given schema markers on it."""
    src = (
        "from typing import Annotated\n"
        "import xarray as xr\n"
        f"def {fn_name}({in_name}: Annotated[(xr.DataArray, *_markers)]) -> xr.DataArray:\n"
        f"    return {in_name}\n"
    )
    ns: dict = {"_markers": markers}
    exec(src, ns)
    return ns[fn_name]


class TestAllPairsEdgeCheck:
    """Every pair of declarations is compared, not just each against the first.

    Three of the four edge predicates are non-transitive: a *loose* declaration is
    compatible with everything, so it cannot serve as a base for a star-wise check.
    ``Dims("x","y")`` is compatible with both ``Dims("x","y", ordered=True)`` and
    ``Dims("y","x", ordered=True)`` — yet those two provably conflict. With no
    producer to anchor on, only an all-pairs comparison finds it.
    """

    def test_conflicting_consumers_caught_via_a_loose_declaration(self, register):
        mod = register(
            "ap_cons",
            # Deliberately loose first: it is compatible with each of the other two,
            # so a check anchored on it alone sees no problem.
            _named_schema_consumer("c1_loose", Dims("time", "x")),
            _named_schema_consumer("c2_time_x", Dims("time", "x", ordered=True)),
            _named_schema_consumer("c3_x_time", Dims("x", "time", ordered=True)),
        )
        dr = _build(mod)
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dims incompatible") as exc,
        ):
            check_dag_contracts(dr)
        # The conflicting *pair* is named, not just the mismatch with the base.
        message = str(exc.value)
        assert "c2_time_x" in message
        assert "c3_x_time" in message

    def test_mutually_compatible_consumers_still_pass(self, register):
        mod = register(
            "ap_ok",
            _named_schema_consumer("d1", Dims("time", "x")),
            _named_schema_consumer("d2", Dims("x", "time")),
            _named_schema_consumer("d3", Dims("time", "x", ordered=True)),
        )
        dr = _build(mod)
        with xra.enabled(True):
            check_dag_contracts(dr)


class TestSchemaDagCheck:
    """The build-time edge check compares dims and dtype markers, always raising
    ``ValueError`` on a provable mismatch (a pipeline-definition error)."""

    def _dr(self, register, prod_markers, cons_markers):
        prod = register("scd_prod", _schema_producer("arr", *prod_markers))
        cons = register("scd_cons", _schema_consumer(*cons_markers))
        return _build(prod, cons)

    def test_dim_sets_differ_raises(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("time", "y")])
        with xra.enabled(True), pytest.raises(ValueError, match="dims incompatible"):
            check_dag_contracts(dr)

    def test_dim_order_differ_raises_when_both_ordered(self, register):
        dr = self._dr(
            register,
            [Dims("time", "x", ordered=True)],
            [Dims("x", "time", ordered=True)],
        )
        with xra.enabled(True), pytest.raises(ValueError, match="dims incompatible"):
            check_dag_contracts(dr)

    def test_same_dim_set_any_order_passes(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("x", "time")])
        with xra.enabled(True):
            check_dag_contracts(dr)

    def test_dtype_kinds_differ_raises(self, register):
        dr = self._dr(register, [Dtype("float64")], [Dtype("int32")])
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dtypes incompatible"),
        ):
            check_dag_contracts(dr)

    def test_different_widths_raise(self, register):
        dr = self._dr(register, [Dtype("float64")], [Dtype("float32")])
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dtypes incompatible"),
        ):
            check_dag_contracts(dr)

    def test_kind_matches_any_width(self, register):
        dr = self._dr(register, [Dtype("float")], [Dtype("float32")])
        with xra.enabled(True):
            check_dag_contracts(dr)

    def test_coords_are_not_checked_at_edges(self, register):
        # Coords are lower bounds, so mismatched coord declarations never raise.
        dr = self._dr(register, [Coords("time")], [Coords("time", "lat")])
        with xra.enabled(True):
            check_dag_contracts(dr)

    def test_disabled_skips_schema(self, register):
        dr = self._dr(register, [Dims("time", "x")], [Dims("time", "y")])
        with xra.enabled(False):
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
        with xra.enabled(True), pytest.raises(CatenaValueError, match="dims"):
            check_input_contracts(dr, {"arr": bad})

    def test_dim_match_passes(self, register):
        dr = self._dr(register, Dims("time", "x"))
        good = xr.DataArray(np.zeros((2, 3)), dims=("time", "x"))
        with xra.enabled(True):
            check_input_contracts(dr, {"arr": good})

    def test_dtype_kind_mismatch_raises(self, register):
        dr = self._dr(register, Dtype("float64"))
        bad = xr.DataArray(np.zeros((3,), dtype="int64"), dims=("x",))
        with xra.enabled(True), pytest.raises(CatenaValueError, match="dtype"):
            check_input_contracts(dr, {"arr": bad})

    def test_every_failing_input_is_reported_at_once(self, register):
        consumers = register(
            "sci_many",
            _named_schema_consumer("e1", Dims("x"), in_name="first"),
            _named_schema_consumer("e2", Dtype("float64"), in_name="second"),
        )
        dr = _build(consumers)
        inputs = {
            "first": xr.DataArray([1.0], dims="y"),
            "second": xr.DataArray(np.zeros(1, dtype="int64"), dims="x"),
        }
        with xra.enabled(True), pytest.raises(CatenaValueError) as exc:
            check_input_contracts(dr, inputs)
        message = str(exc.value)
        assert "'first' (dims)" in message
        assert "'second' (dtype)" in message


class TestParameterizedNodes:
    """Nodes generated by Hamilton's ``@parameterize_sources``.

    The check reads each originating function's signature, keying inputs by the
    raw parameter name and the output by the function name. A parameterised
    function's parameter is not a node, and its outputs are named by the
    decorator, so neither end of its real edges is checked.
    """

    @pytest.mark.xfail(
        strict=True, reason="contracts on parameterised nodes are unread"
    )
    def test_mismatch_on_a_parameterised_edge_is_caught(self, register):
        from hamilton.function_modifiers import parameterize_sources

        @parameterize_sources(mass_nee={"flux": "nee"})
        @xra.enforce
        def to_mass(flux: Annotated[xr.DataArray, xra.Unit("kg")]) -> xr.DataArray:
            return flux

        prod = register("ps_prod", _bare_producer("umol m-2 s-1", name="nee"))
        cons = register("ps_cons", to_mass)
        dr = _build(prod, cons)
        with (
            xra.enabled(True),
            pytest.raises(ValueError, match="dimensionally incompatible"),
        ):
            check_dag_contracts(dr)

    @pytest.mark.xfail(strict=True, reason="shared parameter names collide")
    def test_shared_parameter_names_do_not_collide(self, register):
        from hamilton.function_modifiers import parameterize_sources

        @parameterize_sources(mass_a={"flux": "a"})
        @xra.enforce
        def as_mass(
            flux: Annotated[xr.DataArray, xra.Unit("g m-2 d-1")],
        ) -> xr.DataArray:
            return flux

        @parameterize_sources(molar_b={"flux": "b"})
        @xra.enforce
        def as_molar(
            flux: Annotated[xr.DataArray, xra.Unit("umol m-2 s-1")],
        ) -> xr.DataArray:
            return flux

        prods = register(
            "ps_prods",
            _bare_producer("g m-2 d-1", name="a"),
            _bare_producer("umol m-2 s-1", name="b"),
        )
        cons = register("ps_cons2", as_mass, as_molar)
        dr = _build(prods, cons)
        with xra.enabled(True):
            check_dag_contracts(dr)
