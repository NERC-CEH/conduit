"""Tests for the :func:`catena.dry_run` pre-flight and its building blocks.

Three layers:

- direct tests of :func:`catena.contract_check.check_input_contracts` (the runtime,
  data-dependent unit check), built on tiny Hamilton drivers so the inputs' ``units``
  attributes and the active mode are fully under test control;
- direct tests of :func:`catena.io.assert_output_paths_writable`;
- tests of the broader pre-flight (config / inputs / DAG plan / output paths) against
  the :class:`catena.DryRunReport` that ``dry_run`` returns, plus a thin layer
  checking that ``catena run --dry-run`` renders every stage of it.
"""

import os
import sys
import types

import pytest
import xarray as xr
import xarray_annotated as xra
from typer.testing import CliRunner

from catena import dry_run
from catena.build import build_driver
from catena.cli.app import app
from catena.config import IOSpec, NodeSpec, ResampleSpec, SubsetSpec, load_config
from catena.contract_check import check_input_contracts
from catena.errors import CatenaValueError
from catena.input_checks import InputCheckError
from catena.io import assert_output_paths_writable

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
        "import xarray_annotated as xra\n"
        "class _Out(TypedDict):\n"
        f"    {name}_out: Annotated[xr.DataArray, xra.Unit('t ha-1')]\n"
        "@extract_fields()\n"
        "@xra.enforce\n"
        f"def {name}({in_name}: Annotated[xr.DataArray, xra.Unit({unit!r})]) -> _Out:\n"
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
# check_input_contracts — direct, against an external input consumed with a unit
# ---------------------------------------------------------------------------


class TestCheckInputUnitsDirect:
    @pytest.fixture
    def dr(self, register):
        """Driver with external input ``vpd_weekly`` consumed declaring ``Pa``."""
        register("vpd_cons", _consumer("Pa"))
        return build_driver(["vpd_cons"], {})

    def test_matching_units_pass(self, dr):
        with xra.enabled(True):
            check_input_contracts(dr, {"vpd_weekly": _input("Pa")})

    def test_different_spelling_passes(self, dr):
        with xra.enabled(True):
            check_input_contracts(dr, {"vpd_weekly": _input("pascal")})

    def test_compatible_but_unequal_units_raise(self, dr):
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="differs from declared"),
        ):
            check_input_contracts(dr, {"vpd_weekly": _input("hPa")})

    def test_incompatible_units_raise(self, dr):
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="input 'vpd_weekly'"),
        ):
            check_input_contracts(dr, {"vpd_weekly": _input("kg")})

    def test_missing_units_raise(self, dr):
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="no 'units' attribute"),
        ):
            check_input_contracts(dr, {"vpd_weekly": _input(None)})

    def test_unparseable_units_raise(self, dr):
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="unparseable"),
        ):
            check_input_contracts(dr, {"vpd_weekly": _input("fraction")})

    def test_off_mode_skips_everything(self, dr):
        with xra.enabled(False):
            check_input_contracts(dr, {"vpd_weekly": _input("kg")})

    def test_input_without_declared_consumer_ignored(self, dr):
        with xra.enabled(True):
            check_input_contracts(dr, {"some_other_var": _input("kg")})

    def test_non_dataarray_on_a_declared_input_raises(self, dr):
        # enforce would raise TypeError when the node runs, so the pre-flight does too.
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="declared a DataArray, got float"),
        ):
            check_input_contracts(dr, {"vpd_weekly": 3.0})

    def test_non_dataarray_without_a_declared_consumer_ignored(self, dr):
        with xra.enabled(True):
            check_input_contracts(dr, {"some_other_var": 3.0})


# ---------------------------------------------------------------------------
# check_input_contracts — propagation through resample (covered) and derive (not)
# ---------------------------------------------------------------------------


class TestCheckInputUnitsPropagation:
    def _resample_driver(self, register):
        """External ``gpp_weekly`` -> passthrough resample -> ``gpp_monthly`` (rate)."""
        from catena.config import expand_node_entries, resample_to_node_entry

        register("rs_cons", _consumer("g m-2 d-1", in_name="gpp_monthly"))
        entry = resample_to_node_entry(
            ResampleSpec(vars=["gpp"], source="weekly", target="monthly", freq="1ME")
        )
        specs = [NodeSpec.from_config(e) for e in expand_node_entries([entry])]
        return build_driver(["node", "rs_cons"], {}, node_specs=specs)

    def test_resample_routed_input_is_validated(self, register):
        dr = self._resample_driver(register)
        with (
            xra.enabled(True),
            pytest.raises(CatenaValueError, match="gpp_weekly"),
        ):
            check_input_contracts(dr, {"gpp_weekly": _input("kg")})

    def test_resample_routed_input_passes_when_correct(self, register):
        dr = self._resample_driver(register)
        with xra.enabled(True):
            check_input_contracts(dr, {"gpp_weekly": _input("g m-2 d-1")})

    def test_derive_routed_input_not_validated(self, register):
        """Documented limitation: an input feeding a [[node]] module before a
        declaring consumer is not validated, since a node can change units."""
        from catena.config import NodeSpec

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
        dr = build_driver(["node", "dv_cons"], {}, node_specs=specs)
        with xra.enabled(True):
            check_input_contracts(dr, {"a": _input("kg"), "b": _input("kg")})


# ---------------------------------------------------------------------------
# assert_output_paths_writable
# ---------------------------------------------------------------------------


class TestAssertOutputPathsWritable:
    def test_writable_destination_passes(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "out.nc"), vars=["gpp"])}
        assert_output_paths_writable(specs)

    def test_unsupported_extension_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "out.txt"), vars=["gpp"])}
        with pytest.raises(ValueError, match="Unsupported file extension"):
            assert_output_paths_writable(specs)

    def test_missing_parent_dir_passes_without_being_created(self, tmp_path):
        missing = tmp_path / "nope" / "nested"
        specs = {"daily": IOSpec(path=str(missing / "out.nc"), vars=["gpp"])}
        assert_output_paths_writable(specs)
        assert not (tmp_path / "nope").exists()

    def test_file_in_the_way_raises(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("")
        specs = {"daily": IOSpec(path=str(blocker / "sub" / "out.nc"), vars=["gpp"])}
        with pytest.raises(FileNotFoundError, match="not a directory"):
            assert_output_paths_writable(specs)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_missing_parent_under_readonly_dir_raises(self, tmp_path):
        readonly = tmp_path / "readonly"
        readonly.mkdir(mode=0o500)
        specs = {"daily": IOSpec(path=str(readonly / "sub" / "out.nc"), vars=["gpp"])}
        with pytest.raises(PermissionError, match="not writable"):
            assert_output_paths_writable(specs)

    def test_subset_zarr_without_store_raises(self, tmp_path):
        specs = {"daily": IOSpec(path=str(tmp_path / "store.zarr"), vars=["gpp"])}
        subset = SubsetSpec(start=0, stop=10, dim="pixel")
        with pytest.raises(FileNotFoundError, match="does not exist"):
            assert_output_paths_writable(specs, subset)


# ---------------------------------------------------------------------------
# dry_run: the report, and the CLI rendering of it
# ---------------------------------------------------------------------------


def _config(tmp_path, synthetic_data_dir, outputs: str = "") -> str:
    """Write a config pointing at the session synthetic data, with optional outputs."""
    content = f"""\
[[node]]
name = "mean_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
{outputs}
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return str(p)


@pytest.mark.parametrize(
    "section",
    [
        '[blocking]\nblock_size = 2\ndim = "locaton"\n',
        '[subset]\nstart = 0\nstop = 2\ndim = "locaton"\n',
    ],
)
def test_dry_run_rejects_a_dim_on_no_input(tmp_path, synthetic_data_dir, section):
    config = _config(tmp_path, synthetic_data_dir, outputs=section)
    with pytest.raises(CatenaValueError, match="dim 'locaton'"):
        dry_run(config)


def _stage(report, name: str):
    """The named stage of a report, so a test names what it asserts on."""
    return next(stage for stage in report.stages if stage.name == name)


class TestDryRunReport:
    """`dry_run` returns the outcome as data; only the CLI turns it into text."""

    def test_no_outputs_skips_the_output_stages(self, tmp_path, synthetic_data_dir):
        report = dry_run(_config(tmp_path, synthetic_data_dir))
        assert _stage(report, "config").status == "ok"
        assert _stage(report, "plan").status == "skipped"
        assert _stage(report, "outputs").status == "skipped"

    def test_passes_and_writes_nothing(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "gpp_daily.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        report = dry_run(_config(tmp_path, synthetic_data_dir, outputs))
        assert _stage(report, "plan").status == "ok"
        assert "output node(s) reachable" in _stage(report, "plan").detail
        assert _stage(report, "outputs").status == "ok"
        # The dry run must not execute or save anything.
        assert not out.exists()

    def test_output_blocked_by_a_file_raises(self, tmp_path, synthetic_data_dir):
        blocker = tmp_path / "blocker"
        blocker.write_text("")
        out = blocker / "out.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        with pytest.raises(FileNotFoundError):
            dry_run(cfg)

    def test_missing_input_file_is_a_catena_error(self, tmp_path):
        """The CLI shows a CatenaError without a traceback, so this must be one."""
        from catena.errors import CatenaFileNotFoundError

        cfg = _config(tmp_path, tmp_path / "no_such_dir")
        with pytest.raises(CatenaFileNotFoundError, match=r"\[inputs\.daily\]"):
            dry_run(cfg)

    def test_unreachable_output_var_raises(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "out.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["not_a_real_variable"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        with pytest.raises(ValueError, match="Unknown nodes"):
            dry_run(cfg)
        assert not out.exists()

    def test_parsed_config_needs_no_file(self, tmp_path, synthetic_data_dir):
        """A caller may parse, adjust the spec, then validate it in memory."""
        parsed = load_config(_config(tmp_path, synthetic_data_dir))
        report = dry_run(parsed)
        assert report.config_file is None
        assert _stage(report, "config").status == "ok"

    def test_soft_findings_are_collected_not_scattered(
        self, tmp_path, synthetic_data_dir
    ):
        """An unused input is a warning; the report carries it as a finding."""
        out = tmp_path / "out.nc"
        outputs = (
            f'[inputs.extra]\npath = "{synthetic_data_dir / "daily.nc"}"\n'
            'vars = ["humidity"]\n\n'
            f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        )
        report = dry_run(_config(tmp_path, synthetic_data_dir, outputs))
        findings = _stage(report, "plan").findings
        assert any("consumed by no node" in f for f in findings)


class TestSwitchedOff:
    """A dry run says so when contract checking is off, rather than claiming a pass."""

    def test_contract_stages_say_they_did_not_check(self, tmp_path, synthetic_data_dir):
        with xra.enabled(False):
            report = dry_run(_config(tmp_path, synthetic_data_dir))
        assert _stage(report, "contracts").status == "skipped"
        assert "switched off" in _stage(report, "dag").detail

    def test_contract_stages_report_a_check(self, tmp_path, synthetic_data_dir):
        with xra.enabled(True):
            report = dry_run(_config(tmp_path, synthetic_data_dir))
        assert _stage(report, "contracts").status == "ok"
        assert "passed" in _stage(report, "dag").detail


class TestDryRunRendering:
    """Captured CLI output carries no escape codes, because ``typer.echo`` strips them
    when stdout is not a terminal.
    """

    def test_no_line_wraps_at_eighty_columns(self, tmp_path, synthetic_data_dir):
        """The recipe pages capture this output verbatim at documentation-build
        time, so a line long enough to wrap would wrap differently depending on
        the terminal width wherever the build ran.
        """
        cfg = _config(tmp_path, synthetic_data_dir)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code == 0, result.output
        # The header echoes the config path, whose length catena does not
        # control; every line catena composes itself is indented.
        too_long = [
            line
            for line in result.output.splitlines()
            if line.startswith(" ") and len(line) > 80
        ]
        assert not too_long, too_long

    def test_output_carries_no_escape_codes(self, tmp_path, synthetic_data_dir):
        cfg = _config(tmp_path, synthetic_data_dir)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "\x1b[" not in result.output


class TestDryRunCLI:
    """The command renders the report; the pipeline decides what is in it."""

    def test_renders_every_stage(self, tmp_path, synthetic_data_dir):
        cfg = _config(tmp_path, synthetic_data_dir)
        report = dry_run(cfg)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run passed." in result.output
        for stage in report.stages:
            assert stage.detail in result.output

    def test_hard_failure_exits_non_zero(self, tmp_path, synthetic_data_dir):
        blocker = tmp_path / "blocker"
        blocker.write_text("")
        out = blocker / "out.nc"
        outputs = f'[outputs.daily]\npath = "{out}"\nvars = ["temperature"]\n'
        cfg = _config(tmp_path, synthetic_data_dir, outputs)
        result = runner.invoke(app, ["run", cfg, "--dry-run"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# [validation] input checks (catena.input_checks) through the dry run
# ---------------------------------------------------------------------------


def _checks_config(
    tmp_path,
    synthetic_data_dir,
    second: str,
    checks: str,
    second_var: str = "temperature",
) -> str:
    """Config with two input sections and a [validation].checks block."""
    content = f"""\
[[node]]
name = "mean_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[inputs.other]
path = "{synthetic_data_dir / second}"
vars = ["{second_var}"]

[validation]
checks = [{checks}]
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return str(p)


class TestDryRunInputChecks:
    """`[validation].checks` really run in the dry run, not just in unit tests."""

    def test_passing_check_reported(self, tmp_path, synthetic_data_dir):
        # daily.nc against itself: identical time index, so time_equal passes.
        cfg = _checks_config(
            tmp_path,
            synthetic_data_dir,
            "daily.nc",
            '{ check = "time_equal", inputs = ["daily", "other"] }',
        )
        report = dry_run(cfg)
        assert _stage(report, "checks").detail == "input checks passed (1)"

    def test_failing_check_aborts(self, tmp_path, synthetic_data_dir):
        # daily.nc vs weekly.nc: genuinely different time indices.
        cfg = _checks_config(
            tmp_path,
            synthetic_data_dir,
            "weekly.nc",
            '{ check = "time_equal", inputs = ["daily", "other"] }',
            second_var="pressure",
        )
        with pytest.raises(InputCheckError, match="time_equal"):
            dry_run(cfg)

    def test_no_checks_configured_reported(self, tmp_path, synthetic_data_dir):
        report = dry_run(_config(tmp_path, synthetic_data_dir))
        assert _stage(report, "checks").status == "skipped"
        assert "none configured" in _stage(report, "checks").detail

    def test_wildcard_inputs_expand(self, tmp_path, synthetic_data_dir):
        cfg = _checks_config(
            tmp_path,
            synthetic_data_dir,
            "daily.nc",
            '{ check = "time_equal", inputs = ["*"] }',
        )
        report = dry_run(cfg)
        assert _stage(report, "checks").detail == "input checks passed (1)"
