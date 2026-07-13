"""Tests for the ``freq`` contract facet (xarray-annotated's temporal domain).

The frequency (and phase) of a node's time axis is one more facet of the whole-DAG
contract check: declared with ``Annotated[DataArray, Freq("7D")]`` (or a ``freq``
key on a ``[[node]]``), compared marker-vs-marker at build time and marker-vs-array
in ``--dry-run``. Unlike units, it is *not* preserved across a passthrough — a
``[[resample]]`` is exactly what changes it, so it declares its own output frequency.

Frequency validation is opt-in: an input is only checked where a consumer declares
a ``Freq`` for it. The old label-magic validator (``_validate_dates``, keyed on the
section being called ``daily``/``weekly``/``monthly``) is gone.
"""

import sys
import types
import warnings
from typing import Annotated

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE
from xarray_annotated.temporal import Freq, FreqError, FreqWarning
from xarray_annotated.units import policy

from conduit.config import Config, NodeSpec, ResampleSpec, resample_to_node_entry
from conduit.dag.contract_check import check_dag_contracts, check_input_contracts
from conduit.dag.driver import build_driver


def _series(freq: str, periods: int = 10, start: str = "2020-01-01") -> xr.DataArray:
    """A 1-D DataArray on a time axis of the given pandas frequency."""
    times = pd.date_range(start, periods=periods, freq=freq)
    return xr.DataArray(np.ones(periods), dims=("time",), coords={"time": times})


@pytest.fixture
def register():
    """Build Hamilton-scannable modules from functions, cleaning up afterwards."""
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


def _producer(name: str, marker: Freq | None):
    """A single-output node producing ``name``, optionally declaring a frequency."""
    hint = Annotated[xr.DataArray, marker] if marker else xr.DataArray

    def prod() -> hint:  # type: ignore[valid-type]
        return _series("D")

    prod.__name__ = name
    return prod


def _consumer(marker: Freq, in_name: str = "flux", name: str = "cons"):
    """A node consuming ``in_name`` and declaring the given frequency for it."""
    src = (
        "from typing import Annotated\n"
        "import xarray as xr\n"
        f"def {name}({in_name}: Annotated[xr.DataArray, _marker]) -> xr.DataArray:\n"
        f"    return {in_name}\n"
    )
    ns: dict = {"_marker": marker}
    exec(src, ns)
    return ns[name]


# ---------------------------------------------------------------------------
# Build-time edge check: declaration vs declaration
# ---------------------------------------------------------------------------


class TestFreqEdgeCheck:
    def _dr(self, register, produced: Freq | None, consumed: Freq):
        prod = register("fq_prod", _producer("flux", produced))
        cons = register("fq_cons", _consumer(consumed))
        return _build(prod, cons)

    def test_spacing_mismatch_raises(self, register):
        dr = self._dr(register, Freq("D"), Freq("7D"))
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="frequencies incompatible"),
        ):
            check_dag_contracts(dr)

    def test_message_names_node_and_freqs(self, register):
        dr = self._dr(register, Freq("D"), Freq("7D"))
        with policy(enabled=True), pytest.raises(ValueError, match="flux") as exc:
            check_dag_contracts(dr)
        assert "Freq('D')" in str(exc.value)
        assert "Freq('7D')" in str(exc.value)

    def test_matching_freqs_pass(self, register):
        dr = self._dr(register, Freq("7D"), Freq("7D"))
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_anchor_mismatch_raises(self, register):
        # The resample-phase footgun: same spacing, different anchor.
        dr = self._dr(register, Freq("W-SUN"), Freq("W-WED"))
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="frequencies incompatible"),
        ):
            check_dag_contracts(dr)

    def test_unanchored_declaration_matches_any_anchor(self, register):
        # "7D" spells no anchor, so it compares on spacing only.
        dr = self._dr(register, Freq("7D"), Freq("W-WED"))
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_undeclared_producer_is_not_checked(self, register):
        # Opt-in: an edge is compared only where both sides declare a frequency.
        dr = self._dr(register, None, Freq("7D"))
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)

    def test_disabled_policy_skips(self, register):
        dr = self._dr(register, Freq("D"), Freq("7D"))
        with policy(enabled=False), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_dag_contracts(dr)


# ---------------------------------------------------------------------------
# Input check: declaration vs the loaded array (the --dry-run leg)
# ---------------------------------------------------------------------------


class TestFreqInputCheck:
    def _dr(self, register, marker: Freq):
        return _build(register("fqi_cons", _consumer(marker, in_name="arr")))

    def test_inferred_frequency_contradicting_declaration_raises(self, register):
        dr = self._dr(register, Freq("7D"))
        with policy(enabled=True), pytest.raises(FreqError, match="frequency mismatch"):
            check_input_contracts(dr, {"arr": _series("D")})

    def test_matching_frequency_passes(self, register):
        dr = self._dr(register, Freq("7D"))
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_input_contracts(dr, {"arr": _series("7D")})

    def test_anchor_mismatch_raises(self, register):
        dr = self._dr(register, Freq("W-SUN"))
        with policy(enabled=True), pytest.raises(FreqError, match="frequency mismatch"):
            check_input_contracts(dr, {"arr": _series("W-WED")})

    def test_short_axis_is_uninferable_and_warns(self, register):
        # Fewer than three points: the declaration was never tested, not violated.
        dr = self._dr(register, Freq("7D"))
        with policy(enabled=True), pytest.warns(FreqWarning, match="uninferable"):
            check_input_contracts(dr, {"arr": _series("D", periods=2)})

    def test_undeclared_input_is_not_checked(self, register):
        # A pipeline with no Freq declarations skips the facet entirely.
        cons = register("fqi_plain", _consumer(Freq("D"), in_name="other"))
        dr = _build(cons)
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            check_input_contracts(dr, {"arr": _series("ME")})


# ---------------------------------------------------------------------------
# [[node]]: the `freq` config key
# ---------------------------------------------------------------------------


class TestNodeFreq:
    def test_invalid_offset_raises_at_parse_time(self):
        with pytest.raises(ValueError, match="invalid frequency"):
            NodeSpec.from_config(
                {"name": "x", "inputs": ["a"], "expression": "a", "freq": "nonsense"}
            )

    def test_node_freq_parsed(self):
        spec = NodeSpec.from_config(
            {"name": "x", "inputs": ["a"], "expression": "a", "freq": "7D"}
        )
        assert spec.freq == "7D"

    def _dr(self, register, node_freq: str, consumer: Freq):
        register("nf_cons", _consumer(consumer, in_name="flux"))
        specs = [
            NodeSpec(
                name="flux",
                inputs=["a"],
                expression="a",
                import_path=None,
                function=None,
                freq=node_freq,
            )
        ]
        return build_driver(["node", "nf_cons"], {}, node_specs=specs)

    def test_declared_node_freq_is_a_checkable_producer(self, register):
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="frequencies incompatible"),
        ):
            self._dr(register, "1ME", Freq("7D"))

    def test_matching_consumer_passes(self, register):
        with policy(enabled=True):
            self._dr(register, "7D", Freq("7D"))

    def test_runtime_check_on_node_output(self):
        # The generated node is wrapped in @declare_freq, so a node whose output
        # contradicts its declaration fails when it runs.
        specs = [
            NodeSpec(
                name="flux",
                inputs=["a"],
                expression="a",
                import_path=None,
                function=None,
                freq="1ME",
            )
        ]
        with policy(enabled=True):
            dr = build_driver(["node"], {}, node_specs=specs)
            with pytest.raises(FreqError, match="frequency mismatch"):
                dr.execute(["flux"], inputs={"a": _series("D")})


# ---------------------------------------------------------------------------
# [[resample]]: auto-declares its output frequency; freq is not propagated
# ---------------------------------------------------------------------------


def _resample_specs(*specs):
    from conduit.config import expand_node_entries

    entries = [resample_to_node_entry(s) for s in specs]
    return [NodeSpec.from_config(e) for e in expand_node_entries(entries)]


class TestResampleFreq:
    def test_entry_declares_the_offset(self):
        entry = resample_to_node_entry(
            ResampleSpec(vars=["gpp"], source="daily", target="weekly", freq="7D")
        )
        assert entry["freq"] == "7D"
        assert entry["passthrough"] is True

    def test_explicit_anchored_offset_is_declared(self):
        entry = resample_to_node_entry(
            ResampleSpec(
                vars=["gpp"],
                source="daily",
                target="weekly",
                freq="W-WED",
            )
        )
        assert entry["freq"] == "W-WED"

    def _dr(self, register, consumer: Freq, offset: str = "7D"):
        register("rf_cons", _consumer(consumer, in_name="gpp_weekly"))
        specs = _resample_specs(
            ResampleSpec(
                vars=["gpp"],
                source="daily",
                target="weekly",
                freq=offset,
            )
        )
        return build_driver(["node", "rf_cons"], {}, node_specs=specs)

    def test_consumer_matching_the_offset_passes(self, register):
        with policy(enabled=True):
            self._dr(register, Freq("7D"))

    def test_consumer_contradicting_the_offset_raises(self, register):
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="gpp_weekly"),
        ):
            self._dr(register, Freq("1ME"))

    def test_wrong_anchor_caught_against_declared_phase(self, register):
        # A fat-fingered W-WED offset against a downstream consumer that requires
        # Sundays: caught at build time, on the resample node's own declaration.
        with (
            policy(enabled=True),
            pytest.raises(ValueError, match="frequencies incompatible"),
        ):
            self._dr(register, Freq("W-SUN"), offset="W-WED")

    @pytest.mark.parametrize("offset", ["7D", "1ME", "W-WED"])
    def test_resampled_output_satisfies_its_declared_offset(self, offset):
        # End-to-end: the offset the transform resamples *to* is the same frequency
        # the checker infers from the result, for every offset spelling we default
        # to (and an anchored one). Without this the auto-declaration would be a
        # self-inflicted failure at run time.
        specs = _resample_specs(
            ResampleSpec(
                vars=["gpp"],
                source="daily",
                target="weekly",
                freq=offset,
            )
        )
        with policy(enabled=True), warnings.catch_warnings():
            warnings.simplefilter("error")
            dr = build_driver(["node"], {}, node_specs=specs)
            out = dr.execute(
                ["gpp_weekly"], inputs={"gpp_daily": _series("D", periods=120)}
            )
        assert xr.infer_freq(out["gpp_weekly"]["time"]) is not None

    def test_source_freq_is_not_propagated_across_the_resample(self, register):
        # Units propagate across a passthrough; frequency must not — the resample
        # changes it. A daily source feeding a 7D-declaring consumer of the
        # *resampled* var is fine.
        register("rfp_prod", _producer("gpp_daily", Freq("D")))
        register("rfp_cons", _consumer(Freq("7D"), in_name="gpp_weekly"))
        specs = _resample_specs(
            ResampleSpec(vars=["gpp"], source="daily", target="weekly", freq="7D")
        )
        with policy(enabled=True):
            build_driver(["rfp_prod", "node", "rfp_cons"], {}, node_specs=specs)


# ---------------------------------------------------------------------------
# Policy plumbing: [annotations] drives the temporal axes
# ---------------------------------------------------------------------------


class TestPolicyFromConfig:
    def test_on_mismatch_and_on_uninferable_parsed(self):
        parsed = Config(
            {"annotations": {"on_mismatch": "warn", "on_uninferable": "ignore"}}
        ).parse()
        assert parsed.on_mismatch == "warn"
        assert parsed.on_uninferable == "ignore"


# ---------------------------------------------------------------------------
# End-to-end: `conduit run --dry-run` flags a mis-declared input frequency
# ---------------------------------------------------------------------------


def _write_config(tmp_path, module: str) -> str:
    """A one-input pipeline whose sole (user-module) node consumes the daily input.

    The input is *daily*; what ``module``'s node declares about it is the variable
    under test. A ``[[node]]``'s ``freq`` key declares its *output*, so the input leg
    of the check is reached the same way it is for units: from a user module's
    parameter annotation.
    """
    _series("D", periods=30).rename("temperature").to_netcdf(tmp_path / "daily.nc")
    config = f"""
[inputs.daily]
path = "daily.nc"
vars = ["temperature"]

[mymodel]
_import_path = "{module}"

[outputs.weekly]
path = "out.nc"
suffix = ""
vars = ["mean_temperature"]
"""
    path = tmp_path / "config.toml"
    path.write_text(config)
    return str(path)


def _model(declared: Freq):
    """A user-module node consuming ``temperature_daily`` at a declared frequency."""
    src = (
        "from typing import Annotated\n"
        "import xarray as xr\n"
        "def mean_temperature(\n"
        "    temperature_daily: Annotated[xr.DataArray, _declared],\n"
        ") -> xr.DataArray:\n"
        "    return temperature_daily.mean('time')\n"
    )
    ns: dict = {"_declared": declared}
    exec(src, ns)
    return ns["mean_temperature"]


class TestDryRunEndToEnd:
    def _invoke(self, register, tmp_path, declared: Freq, module: str):
        from typer.testing import CliRunner

        from conduit.cli import app

        register(module, _model(declared))
        with policy(enabled=True):
            return CliRunner().invoke(
                app, ["run", _write_config(tmp_path, module), "--dry-run"]
            )

    def test_dry_run_passes_when_the_declaration_holds(self, register, tmp_path):
        result = self._invoke(register, tmp_path, Freq("D"), "fq_cli_ok")
        assert result.exit_code == 0, result.output
        assert "Dry run passed." in result.output

    def test_dry_run_flags_a_contradicted_input_frequency(self, register, tmp_path):
        # The consumer declares weekly; the loaded input is daily. Nothing executes
        # and nothing is written — the mis-declaration surfaces before any compute.
        result = self._invoke(register, tmp_path, Freq("7D"), "fq_cli_bad")
        assert result.exit_code != 0
        assert isinstance(result.exception, FreqError)
        assert "frequency mismatch" in str(result.exception)
        assert not (tmp_path / "out.nc").exists()
