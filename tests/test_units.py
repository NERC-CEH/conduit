"""Tests for unit declarations and runtime unit validation."""

import warnings
from typing import Annotated, TypedDict

import numpy as np
import pint
import pytest
import xarray as xr

from conduit import units
from conduit.config import Config
from conduit.dag._utils import declare_units


def _da(values, unit=None):
    """Build a (time, pixel) DataArray, optionally with a units attribute."""
    arr = np.asarray(values, dtype=float)
    time = xr.date_range("2020-01-01", periods=arr.shape[0], freq="7D")
    da = xr.DataArray(
        arr,
        dims=("time", "pixel"),
        coords={"time": time, "pixel": np.arange(arr.shape[1])},
    )
    if unit is not None:
        da.attrs["units"] = unit
    return da


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


class TestMode:
    def test_default_mode_is_warn(self):
        with units.mode(None):
            assert units.get_mode() == "warn"

    def test_set_mode(self):
        with units.mode("strict"):
            assert units.get_mode() == "strict"

    def test_env_overrides_process_mode(self, monkeypatch):
        with units.mode("off"):
            monkeypatch.setenv(units.MODE_ENV_VAR, "strict")
            assert units.get_mode() == "strict"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid units mode"):
            units.set_mode("bogus")


# ---------------------------------------------------------------------------
# Declared-unit validation (fail fast at decoration time)
# ---------------------------------------------------------------------------


class TestAssertValidUnit:
    @pytest.mark.parametrize(
        "unit", ["degC", "Pa", "1", "umol m-2 s-1", "g m-2 d-1", "t ha-1 month-1"]
    )
    def test_valid_units_pass(self, unit):
        units.assert_valid_unit(unit, "ctx")  # no raise

    @pytest.mark.parametrize("unit", ["degrees_C", "not_a_unit", "kg/"])
    def test_invalid_units_raise_with_context(self, unit):
        with pytest.raises(ValueError, match="not a recognised"):
            units.assert_valid_unit(unit, "myctx input 'x'")


# ---------------------------------------------------------------------------
# check_units: conversion, round-trip, incompatibility, missing
# ---------------------------------------------------------------------------


class TestCheckUnits:
    def test_round_trip_preserves_coords_and_stamps_declared(self):
        da = _da([[1.0, 2.0], [3.0, 4.0]], unit="Pa")
        out = units.check_units(da, "Pa", "vpd", "strict")
        assert out.attrs["units"] == "Pa"
        xr.testing.assert_equal(out["time"], da["time"])
        xr.testing.assert_equal(out["pixel"], da["pixel"])
        np.testing.assert_allclose(out.values, da.values)

    def test_conversion_hpa_to_pa(self):
        da = _da([[10.0, 20.0]], unit="hPa")
        out = units.check_units(da, "Pa", "vpd", "strict")
        assert out.attrs["units"] == "Pa"
        np.testing.assert_allclose(out.values, [[1000.0, 2000.0]])

    def test_incompatible_raises_dimensionality_error(self):
        da = _da([[1.0, 2.0]], unit="degC")
        with pytest.raises(pint.DimensionalityError):
            units.check_units(da, "kg", "x", "strict")

    def test_affine_kelvin_to_celsius(self):
        da = _da([[300.0, 273.15]], unit="K")
        out = units.check_units(da, "degC", "temperature", "strict")
        np.testing.assert_allclose(out.values, [[26.85, 0.0]])

    def test_missing_units_strict_raises(self):
        da = _da([[1.0, 2.0]])
        with pytest.raises(ValueError, match="no 'units' attribute"):
            units.check_units(da, "Pa", "vpd", "strict")

    def test_missing_units_warn_warns_and_passes_through(self):
        da = _da([[1.0, 2.0]])
        with pytest.warns(UserWarning, match="unvalidated"):
            out = units.check_units(da, "Pa", "vpd", "warn")
        assert "units" not in out.attrs
        np.testing.assert_array_equal(out.values, da.values)

    def test_unparseable_units_strict_raises(self):
        # A present-but-unparseable units string (a non-CF/UDUNITS spelling) cannot
        # be validated; strict mode reports it clearly rather than letting an opaque
        # pint parse error escape.
        da = _da([[1.0, 2.0]], unit="fraction")
        with pytest.raises(ValueError, match="unparseable 'units' attribute"):
            units.check_units(da, "1", "clay", "strict")

    def test_unparseable_units_warn_warns_and_passes_through(self):
        da = _da([[1.0, 2.0]], unit="fraction")
        with pytest.warns(UserWarning, match="unparseable"):
            out = units.check_units(da, "1", "clay", "warn")
        # Left untouched (its original, un-validatable unit is preserved).
        assert out.attrs["units"] == "fraction"
        np.testing.assert_array_equal(out.values, da.values)

    def test_unparseable_units_off_passes_through_silently(self):
        da = _da([[1.0, 2.0]], unit="fraction")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = units.check_units(da, "1", "clay", "off")
        assert out.attrs["units"] == "fraction"
        np.testing.assert_array_equal(out.values, da.values)

    def test_exact_forbids_converting_input(self):
        # hPa where Pa is declared: would scale values, so exact mode must raise.
        da = _da([[10.0, 20.0]], unit="hPa")
        with pytest.raises(ValueError, match="exact unit matching is enabled"):
            units.check_units(da, "Pa", "vpd", "strict", exact=True)

    def test_exact_accepts_equivalent_spelling(self):
        # 'pascal' is the same unit as 'Pa' (no value change), so exact accepts it.
        da = _da([[10.0, 20.0]], unit="pascal")
        out = units.check_units(da, "Pa", "vpd", "strict", exact=True)
        assert out.attrs["units"] == "Pa"
        np.testing.assert_allclose(out.values, [[10.0, 20.0]])

    def test_exact_still_raises_on_incompatible(self):
        da = _da([[1.0, 2.0]], unit="degC")
        with pytest.raises(pint.DimensionalityError):
            units.check_units(da, "kg", "x", "strict", exact=True)

    def test_exact_forbids_affine_conversion(self):
        # K -> degC is an *affine* (offset) conversion, not just a scale; it still
        # changes the values, so exact mode must reject it like the hPa/Pa case.
        da = _da([[300.0]], unit="K")
        with pytest.raises(ValueError, match="exact unit matching is enabled"):
            units.check_units(da, "degC", "temperature", "strict", exact=True)

    def test_missing_units_off_passes_through_silently(self):
        # off mode neither raises (unlike strict) nor warns (unlike warn).
        da = _da([[1.0, 2.0]])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = units.check_units(da, "Pa", "vpd", "off")
        assert "units" not in out.attrs
        np.testing.assert_array_equal(out.values, da.values)


# ---------------------------------------------------------------------------
# CF / UDUNITS string parsing
# ---------------------------------------------------------------------------


class TestCFParsing:
    @pytest.mark.parametrize(
        "unit",
        ["umol m-2 s-1", "g m-2 d-1", "t ha-1", "mm d-1", "ppm", "degC"],
    )
    def test_cf_unit_strings_parse_and_convert(self, unit):
        da = _da([[1.0, 2.0]], unit=unit)
        out = units.check_units(da, unit, "x", "strict")
        assert out.attrs["units"] == unit
        np.testing.assert_allclose(out.values, da.values)


# ---------------------------------------------------------------------------
# Dimensional compatibility (used by the build-time DAG check)
# ---------------------------------------------------------------------------


class TestUnitsCompatible:
    @pytest.mark.parametrize(
        ("a", "b"),
        [("Pa", "hPa"), ("g m-2 d-1", "kg m-2 s-1"), ("1", "dimensionless")],
    )
    def test_compatible(self, a, b):
        assert units.units_compatible(a, b)

    @pytest.mark.parametrize(
        ("a", "b"),
        [("Pa", "kg"), ("g m-2 d-1", "Pa"), ("mm", "1")],
    )
    def test_incompatible(self, a, b):
        assert not units.units_compatible(a, b)


class TestUnitsEqual:
    @pytest.mark.parametrize(
        ("a", "b"),
        [("Pa", "pascal"), ("1", "dimensionless"), ("g m-2 d-1", "g m-2 d-1")],
    )
    def test_equal(self, a, b):
        assert units.units_equal(a, b)

    @pytest.mark.parametrize(("a", "b"), [("hPa", "Pa"), ("g", "kg"), ("degC", "K")])
    def test_not_equal(self, a, b):
        # Compatible but value-changing → not equal.
        assert units.units_compatible(a, b)
        assert not units.units_equal(a, b)


# ---------------------------------------------------------------------------
# Exact-match flag resolution
# ---------------------------------------------------------------------------


class TestExactMatchFlag:
    def test_default_is_false(self):
        units.set_exact_match(None)
        assert units.get_exact_match() is False

    def test_set_exact_match(self):
        try:
            units.set_exact_match(True)
            assert units.get_exact_match() is True
        finally:
            units.set_exact_match(None)

    @pytest.mark.parametrize(("env", "expected"), [("1", True), ("off", False)])
    def test_env_overrides_process_flag(self, monkeypatch, env, expected):
        units.set_exact_match(not expected)  # process value the env must override
        try:
            monkeypatch.setenv(units.EXACT_ENV_VAR, env)
            assert units.get_exact_match() is expected
        finally:
            units.set_exact_match(None)

    def test_invalid_env_raises(self, monkeypatch):
        monkeypatch.setenv(units.EXACT_ENV_VAR, "maybe")
        with pytest.raises(ValueError, match=units.EXACT_ENV_VAR):
            units.get_exact_match()


# ---------------------------------------------------------------------------
# units_from_signature: reading declarations off a node's annotations
# ---------------------------------------------------------------------------


class TestUnitsFromSignature:
    def test_extracts_inputs_and_typeddict_outputs(self):
        class Out(TypedDict):
            gpp: Annotated[xr.DataArray, "g m-2 d-1"]
            lue: Annotated[xr.DataArray, "g MJ-1"]

        def node(
            temp: Annotated[xr.DataArray, "degC"],
            plain: xr.DataArray,
            scalar: int = 3,
        ) -> Out: ...

        inputs, outputs = units.units_from_signature(node)
        # Only Annotated params with a string unit contribute; others are ignored.
        assert inputs == {"temp": "degC"}
        assert outputs == {"gpp": "g m-2 d-1", "lue": "g MJ-1"}

    def test_bare_annotated_return(self):
        def node(x: Annotated[xr.DataArray, "1"]) -> Annotated[xr.DataArray, "1"]: ...

        inputs, outputs = units.units_from_signature(node)
        assert inputs == {"x": "1"}
        assert outputs == "1"

    def test_no_annotations(self):
        def node(x: xr.DataArray) -> xr.DataArray: ...

        inputs, outputs = units.units_from_signature(node)
        assert inputs == {}
        assert outputs is None

    def test_partial_typeddict_only_annotated_fields_contribute(self):
        # A future model with a mix of unit-carrying and metadata-free outputs:
        # only the annotated fields appear in the declared output units.
        class Out(TypedDict):
            gpp: Annotated[xr.DataArray, "g m-2 d-1"]
            diagnostic: xr.DataArray  # no unit annotation

        def node() -> Out: ...

        _, outputs = units.units_from_signature(node)
        assert outputs == {"gpp": "g m-2 d-1"}

    def test_metadata_on_non_dataarray_param_is_not_a_unit(self):
        # A descriptive string on a *non-DataArray* parameter is metadata, not a
        # unit: only DataArray annotations carry units. So a config param like a
        # documented flag is ignored, and declaring the node does not fail.
        def node(flag: Annotated[bool, "toggles X"] = True) -> xr.DataArray: ...

        inputs, _ = units.units_from_signature(node)
        assert inputs == {}
        declare_units(node)  # no raise: the metadata is never parsed as a unit

    def test_unit_then_description_takes_unit_first(self):
        # Extra metadata after the unit (e.g. a human-readable description) is
        # ignored: the unit is the first string. This is the supported way to
        # attach both a unit and a description to a node parameter.
        def node(
            v: Annotated[xr.DataArray, "m s-1", "z component of velocity"],
        ) -> xr.DataArray: ...

        inputs, _ = units.units_from_signature(node)
        assert inputs == {"v": "m s-1"}
        declare_units(node)  # no raise: 'm s-1' validates, description ignored

    def test_non_string_metadata_before_unit_is_skipped(self):
        # Only strings are considered; a non-string marker before the unit string
        # does not shadow it.
        def node(v: Annotated[xr.DataArray, 42, "m s-1"]) -> xr.DataArray: ...

        inputs, _ = units.units_from_signature(node)
        assert inputs == {"v": "m s-1"}

    def test_description_before_unit_is_misread_and_fails_fast(self):
        # The convention is unit-first. A description placed *before* the unit is
        # mis-read as the unit -- but it fails loudly at decoration time rather
        # than passing silently (unless the description itself parses as a unit).
        def node(
            v: Annotated[xr.DataArray, "z component of velocity", "m s-1"],
        ) -> xr.DataArray: ...

        inputs, _ = units.units_from_signature(node)
        assert inputs == {"v": "z component of velocity"}
        with pytest.raises(ValueError, match="not a recognised"):
            declare_units(node)

    def test_unit_on_optional_dataarray_param_is_read(self):
        # An optional DataArray (DataArray | None) still carries its declared unit.
        def node(
            x: Annotated[xr.DataArray | None, "g m-2"] = None,
        ) -> xr.DataArray: ...

        inputs, _ = units.units_from_signature(node)
        assert inputs == {"x": "g m-2"}


# ---------------------------------------------------------------------------
# unwrap_annotated: seeing through unit metadata to the base type
# ---------------------------------------------------------------------------


class TestUnwrapAnnotated:
    def test_unwraps_annotated_to_base_type(self):
        assert units.unwrap_annotated(Annotated[xr.DataArray, "degC"]) is xr.DataArray

    def test_passes_through_plain_types(self):
        assert units.unwrap_annotated(xr.DataArray) is xr.DataArray
        assert units.unwrap_annotated(int) is int


# ---------------------------------------------------------------------------
# declare_units: input validation + output stamping + edge propagation
# ---------------------------------------------------------------------------


class TestDeclareUnits:
    def test_input_converted_before_reaching_body(self):
        class Out(TypedDict):
            out: Annotated[xr.DataArray, "Pa"]

        @declare_units
        def f(vpd: Annotated[xr.DataArray, "Pa"]) -> Out:
            # vpd reaches the body as a DataArray already converted to declared units
            return {"out": vpd}

        with units.mode("warn"):
            result = f(vpd=_da([[10.0, 20.0]], unit="hPa"))
        np.testing.assert_allclose(result["out"].values, [[1000.0, 2000.0]])

    def test_output_stamped_with_declared_unit_not_inherited(self):
        class Out(TypedDict):
            gpp_weekly: Annotated[xr.DataArray, "g m-2 d-1"]

        @declare_units
        def f(temperature_weekly: Annotated[xr.DataArray, "degC"]) -> Out:
            return {"gpp_weekly": temperature_weekly * 2}

        out = f(temperature_weekly=_da([[1.0, 2.0]], unit="degC"))
        assert out["gpp_weekly"].attrs["units"] == "g m-2 d-1"

    def test_edge_propagation_two_node_chain(self):
        """An internal edge is validated using the upstream node's stamped output."""

        class ProducerOut(TypedDict):
            gpp_weekly: Annotated[xr.DataArray, "g m-2 d-1"]

        class ConsumerOut(TypedDict):
            npp: Annotated[xr.DataArray, "g m-2 d-1"]

        @declare_units
        def producer(
            temperature_weekly: Annotated[xr.DataArray, "degC"],
        ) -> ProducerOut:
            return {"gpp_weekly": temperature_weekly}

        @declare_units
        def consumer(gpp_weekly: Annotated[xr.DataArray, "g m-2 d-1"]) -> ConsumerOut:
            return {"npp": gpp_weekly}

        with units.mode("strict"):
            produced = producer(temperature_weekly=_da([[1.0, 2.0]], unit="degC"))
            # No exception: the stamped 'g m-2 d-1' output validates as consumer input.
            consumed = consumer(gpp_weekly=produced["gpp_weekly"])
        np.testing.assert_allclose(consumed["npp"].values, [[1.0, 2.0]])

    def test_off_mode_skips_validation(self):
        class Out(TypedDict):
            out: Annotated[xr.DataArray, "Pa"]

        @declare_units
        def f(vpd: Annotated[xr.DataArray, "Pa"]) -> Out:
            return {"out": vpd}

        with units.mode("off"), warnings.catch_warnings():
            # Input has no units; strict would raise, but off skips validation and
            # leaves the data unconverted.
            warnings.simplefilter("error")
            result = f(vpd=_da([[10.0, 20.0]]))
        np.testing.assert_allclose(result["out"].values, [[10.0, 20.0]])

    def test_off_mode_still_stamps_output(self):
        class Out(TypedDict):
            gpp_weekly: Annotated[xr.DataArray, "g m-2 d-1"]

        @declare_units
        def f(temperature_weekly: Annotated[xr.DataArray, "degC"]) -> Out:
            return {"gpp_weekly": temperature_weekly}

        with units.mode("off"):
            out = f(temperature_weekly=_da([[1.0, 2.0]], unit="degC"))
        # Stamping applies regardless of mode (it is labelling, not validation):
        # the inherited 'degC' must not leak onto the output.
        assert out["gpp_weekly"].attrs["units"] == "g m-2 d-1"

    def test_bare_annotated_single_output_stamped(self):
        @declare_units
        def f(x: Annotated[xr.DataArray, "degC"]) -> Annotated[xr.DataArray, "1"]:
            return x

        out = f(x=_da([[1.0, 2.0]], unit="degC"))
        assert out.attrs["units"] == "1"

    def test_bad_input_unit_rejected_at_decoration(self):
        with pytest.raises(ValueError, match="not a recognised"):

            @declare_units
            def f(
                x: Annotated[xr.DataArray, "not_a_unit"],
            ) -> Annotated[xr.DataArray, "1"]:
                return x

    def test_bad_output_unit_rejected_at_decoration(self):
        class Out(TypedDict):
            y: Annotated[xr.DataArray, "bogus_unit"]

        with pytest.raises(ValueError, match="not a recognised"):

            @declare_units
            def f(x: Annotated[xr.DataArray, "degC"]) -> Out:
                return {"y": x}


# ---------------------------------------------------------------------------
# Config [units] section
# ---------------------------------------------------------------------------


class TestConfigUnits:
    def test_parse_units_mode(self):
        parsed = Config.loads('[units]\nmode = "strict"\n').parse()
        assert parsed.units_mode == "strict"

    def test_no_units_section_is_none(self):
        parsed = Config.loads("").parse()
        assert parsed.units_mode is None
        assert parsed.units_exact is None

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="must be one of"):
            Config.loads('[units]\nmode = "bogus"\n').parse()

    def test_parse_units_exact(self):
        parsed = Config.loads("[units]\nexact = true\n").parse()
        assert parsed.units_exact is True

    def test_invalid_exact_raises(self):
        with pytest.raises(ValueError, match="'exact' must be a boolean"):
            Config.loads('[units]\nexact = "yes"\n').parse()


# ---------------------------------------------------------------------------
# End-to-end: units validation/conversion through a @declare_units model node
# ---------------------------------------------------------------------------


class TestModelNodeEndToEnd:
    """Units behaviour through a synthetic ``@declare_units`` node, strict mode.

    Exercises the real ``@declare_units`` decorator on a typed multi-output
    node: every declared input is validated, a convertible wrong-unit input is
    converted, an incompatible one raises, and the output unit is stamped.
    """

    @staticmethod
    def _model():
        from typing import Annotated, TypedDict

        from conduit.dag._utils import declare_units

        class Out(TypedDict):
            gpp_weekly: Annotated[xr.DataArray, "g m-2 d-1"]

        @declare_units
        def mymodel(
            temperature_weekly: Annotated[xr.DataArray, "degC"],
            pressure_weekly: Annotated[xr.DataArray, "Pa"],
        ) -> Out:  # type: ignore[valid-type]
            return {"gpp_weekly": temperature_weekly * 0.0 + 1.0}

        return mymodel

    @staticmethod
    def _inputs(**overrides):
        # (value, unit) per declared input; overrides replace specific entries.
        spec = {
            "temperature_weekly": (15.0, "degC"),
            "pressure_weekly": (101325.0, "Pa"),
        }
        spec.update(overrides)
        return {
            name: _da([[value]] * 4, unit=unit) for name, (value, unit) in spec.items()
        }

    def test_convertible_input_accepted_and_output_stamped(self):
        model = self._model()
        # Pressure supplied in hPa where Pa is declared: must convert, not fail.
        inputs = self._inputs(pressure_weekly=(1013.25, "hPa"))
        with units.mode("strict"):
            out = model(**inputs)
        assert out["gpp_weekly"].attrs["units"] == "g m-2 d-1"

    def test_incompatible_input_raises(self):
        import pint

        model = self._model()
        # Pressure supplied in kg where Pa is declared: dimensionally incompatible.
        inputs = self._inputs(pressure_weekly=(1000.0, "kg"))
        with units.mode("strict"), pytest.raises(pint.DimensionalityError):
            model(**inputs)

    def test_missing_units_strict_raises(self):
        model = self._model()
        inputs = self._inputs()
        inputs["temperature_weekly"].attrs.pop("units")
        with units.mode("strict"), pytest.raises(ValueError, match="no 'units'"):
            model(**inputs)
