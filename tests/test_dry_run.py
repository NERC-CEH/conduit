"""Tests for the ``conduit run --dry-run`` pre-flight and its building blocks.

Three layers:

- direct tests of :func:`conduit.dag.contract_check.check_input_units` (the runtime,
  data-dependent unit check), built on tiny Hamilton drivers so the inputs' ``units``
  attributes and the active mode are fully under test control;
- direct tests of :func:`conduit.io.assert_output_paths_writable`;
- CLI integration tests of the broader pre-flight (config / inputs / DAG plan /
  output paths) via ``runner.invoke(app, ["run", ..., "--dry-run"])``.
"""

import sys
import types

import pint
import pytest
import xarray as xr
from typer.testing import CliRunner
from xarray_annotated.units import UnitsWarning, policy

from conduit.cli import app
from conduit.config import IOSpec, ResampleSpec, SubsetSpec
from conduit.dag.contract_check import check_input_units
from conduit.dag.driver import build_driver
from conduit.io import assert_output_paths_writable

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/test_contract_check.py: build Hamilton-scannable modules
# from dynamically generated functions).
# ---------------------------------------------------------------------------


@pytest.fixture
def register():
    """Register synthetic modules in ``sys.modules`` and clean them up afterwards."""
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


def _consumer(unit: str, name: str = "consumer", in_name: str = "vpd_weekly"):
    """A node consuming ``in_name`` with the given declared input unit."""
    src = (
        "from typing import Annotated, TypedDict\n"
        "import xarray as xr\n"
        "from hamilton.function_modifiers import extract_fields\n"
        "from xarray_annotated.units import declare_units\n"
        "class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, 't ha-1']\n"
        "@extract_fields()\n"
        "@declare_units\n"
        f"def {name}({in_name}: Annotated[xr.DataArray, {unit!r}]) -> _Out:\n"
        f"    return {{{name + '_out'!r}: {in_name}}}\n"
    )
    ns: dict = {}
    exec(src, ns)
    return ns[name]


def _input(units_attr: str | None = None) -> xr.DataArray:
    da = xr.DataArray([1.0, 2.0])
    if units_attr is not None:
        da.attrs["units"] = units_attr
    return da


# ---------------------------------------------------------------------------
# check_input_units — direct, against an external input consumed with a unit
# ---------------------------------------------------------------------------


class TestCheckInputUnitsDirect:
    @pytest.fixture
    def dr(self, register):
        """Driver with external input ``vpd_weekly`` consumed declaring ``Pa``."""
        register("vpd_cons", _consumer("Pa"))
        return build_driver(["vpd_cons"], {})

    def test_matching_units_pass(self, dr):
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"vpd_weekly": _input("Pa")})

    def test_compatible_units_convert_without_error(self, dr):
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"vpd_weekly": _input("hPa")})

    def test_exact_match_rejects_compatible_but_different(self, dr):
        with (
            policy(enabled=True, on_missing="error", on_inexact="error"),
            pytest.raises(ValueError, match="on_inexact"),
        ):
            check_input_units(dr, {"vpd_weekly": _input("hPa")})

    def test_incompatible_units_raise(self, dr):
        with (
            policy(enabled=True, on_missing="error"),
            pytest.raises(pint.DimensionalityError),
        ):
            check_input_units(dr, {"vpd_weekly": _input("kg")})

    def test_missing_units_strict_raises(self, dr):
        with (
            policy(enabled=True, on_missing="error"),
            pytest.raises(ValueError, match="no 'units' attribute"),
        ):
            check_input_units(dr, {"vpd_weekly": _input(None)})

    def test_missing_units_warn_warns(self, dr):
        with (
            policy(enabled=True, on_missing="warn"),
            pytest.warns(UnitsWarning, match="unvalidated"),
        ):
            check_input_units(dr, {"vpd_weekly": _input(None)})

    def test_unparseable_units_strict_raises(self, dr):
        with (
            policy(enabled=True, on_missing="error"),
            pytest.raises(ValueError, match="unparseable"),
        ):
            check_input_units(dr, {"vpd_weekly": _input("fraction")})

    def test_unparseable_units_warn_warns(self, dr):
        with (
            policy(enabled=True, on_missing="warn"),
            pytest.warns(UnitsWarning, match="unparseable"),
        ):
            check_input_units(dr, {"vpd_weekly": _input("fraction")})

    def test_off_mode_skips_everything(self, dr):
        with policy(enabled=False):
            check_input_units(dr, {"vpd_weekly": _input("kg")})

    def test_input_without_declared_consumer_ignored(self, dr):
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"some_other_var": _input("kg")})

    def test_non_dataarray_inputs_ignored(self, dr):
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"vpd_weekly": 3.0})


# ---------------------------------------------------------------------------
# check_input_units — propagation through resample (covered) and derive (not)
# ---------------------------------------------------------------------------


class TestCheckInputUnitsPropagation:
    def _resample_driver(self, register):
        """External ``gpp_weekly`` -> resample -> ``gpp_monthly`` consumed as a rate."""
        register("rs_cons", _consumer("g m-2 d-1", in_name="gpp_monthly"))
        specs = [
            ResampleSpec(vars=["gpp"], source_freq="weekly", target_freq="monthly")
        ]
        return build_driver(["resample", "rs_cons"], {"resample_specs": specs})

    def test_resample_routed_input_is_validated(self, register):
        dr = self._resample_driver(register)
        with (
            policy(enabled=True, on_missing="error"),
            pytest.raises(pint.DimensionalityError),
        ):
            check_input_units(dr, {"gpp_weekly": _input("kg")})

    def test_resample_routed_input_passes_when_correct(self, register):
        dr = self._resample_driver(register)
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"gpp_weekly": _input("g m-2 d-1")})

    def test_derive_routed_input_not_validated(self, register):
        """Documented limitation: an input feeding a [[node]] module before a
        declaring consumer is not validated, since a node can change units."""
        from conduit.config import NodeSpec

        register("dv_cons", _consumer("g m-2 d-1", in_name="flux"))
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
        dr = build_driver(["node", "dv_cons"], {"node_specs": specs})
        with policy(enabled=True, on_missing="error"):
            check_input_units(dr, {"a": _input("kg"), "b": _input("kg")})


# ---------------------------------------------------------------------------
# assert_output_paths_writable
# ---------------------------------------------------------------------------


class TestAssertOutputPathsWritable:
    def test_writable_destination_passes(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "out.nc"), vars=["gpp"])}
        assert_output_paths_writable(specs)

    def test_unsupported_extension_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "out.txt"), vars=["gpp"])}
        with pytest.raises(ValueError, match="unsupported file extension"):
            assert_output_paths_writable(specs)

    def test_missing_parent_dir_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "nope" / "out.nc"), vars=["gpp"])}
        with pytest.raises(FileNotFoundError, match="parent directory"):
            assert_output_paths_writable(specs)

    def test_subset_zarr_without_store_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "store.zarr"), vars=["gpp"])}
        subset = SubsetSpec(pixel_start=0, pixel_end=10)
        with pytest.raises(FileNotFoundError, match="does not exist"):
            assert_output_paths_writable(specs, subset)

    def test_subset_csv_unsupported_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "out.csv"), vars=["gpp"])}
        subset = SubsetSpec(pixel_start=0, pixel_end=10)
        with pytest.raises(ValueError, match=r"\[subset\] is only supported"):
            assert_output_paths_writable(specs, subset)


# ---------------------------------------------------------------------------
# CLI: conduit run --dry-run
# ---------------------------------------------------------------------------


def _config(tmp_path, synthetic_data_dir, outputs: str = "") -> str:
    """Write a config pointing at the session synthetic data, with optional outputs."""
    content = f"""\
[[node]]
name = "mean_growth_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"

[grid]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["precipitation", "sunshine_fraction", "temperature", "lai", "gpp"]

[inputs.weekly]
path = "{synthetic_data_dir / "weekly.nc"}"
vars = ["co2", "fapar", "ppfd", "pressure", "vpd"]

[inputs.monthly]
path = "{synthetic_data_dir / "monthly.nc"}"
vars = ["dummy_variable"]

[inputs.static]
path = "{synthetic_data_dir / "static.nc"}"
vars = [
  "elevation", "plant_type", "max_soil_moisture", "clay_content",
  "soil_depth", "organic_carbon_stocks", "root_pool_init",
  "leaf_pool_init", "stem_pool_init",
]
{outputs}
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return str(p)


class TestDryRunCLI:
    def test_no_outputs_passes(self, tmp_path, synthetic_data_dir):
        cfg = _config(tmp_path, synthetic_data_dir)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run passed." in result.output
        assert "skipped (no [outputs.*] configured)" in result.output

    def test_passes_and_writes_nothing(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "gpp_daily.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run passed." in result.output
        assert "output node(s) reachable" in result.output
        # The dry run must not execute or save anything.
        assert not out.exists()

    def test_missing_output_dir_fails(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "missing" / "out.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code != 0

    def test_unreachable_output_var_fails(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "out.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["not_a_real_variable"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code != 0
        assert not out.exists()
