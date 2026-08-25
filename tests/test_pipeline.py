"""Tests for `conduit.run`, the Python entry point a pipeline actually runs through.

`conduit run` is a shim over this, so the behaviour that must hold on every real
run — input checks, output pre-flight, provenance — is tested here rather than
through the CLI.
"""

import pytest
import xarray as xr

from conduit import run
from conduit.checks import InputCheckError
from conduit.config import load_config


def _config(tmp_path, synthetic_data_dir, out, extra=""):
    """A one-node pipeline writing ``warmth`` to ``out``."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""\
[[node]]
name = "warmth_daily"
inputs = ["temperature_daily"]
expression = "temperature_daily * 2"

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[outputs.daily]
path = "{out}"
vars = ["warmth"]
{extra}
"""
    )
    return cfg


class TestRun:
    def test_writes_the_output_and_returns_it(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "out.nc"
        outputs = run(_config(tmp_path, synthetic_data_dir, out))
        assert out.exists()
        assert set(outputs) == {"daily"}
        assert isinstance(outputs["daily"], xr.Dataset)

    def test_no_outputs_returns_an_empty_dict(self, tmp_path, synthetic_data_dir):
        """A checks-only config is legitimate: it still parses, loads and builds."""
        cfg = tmp_path / "no_outputs.toml"
        cfg.write_text(
            f"""\
[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
        )
        assert run(cfg) == {}

    def test_accepts_a_parsed_config(self, tmp_path, synthetic_data_dir):
        """A caller may parse, adjust the spec in Python, then run the result."""
        out = tmp_path / "out.nc"
        parsed = load_config(_config(tmp_path, synthetic_data_dir, out))
        outputs = run(parsed)
        assert set(outputs) == {"daily"}
        assert out.exists()

    def test_provenance_is_stamped_for_a_config_path(
        self, tmp_path, synthetic_data_dir
    ):
        out = tmp_path / "out.nc"
        run(_config(tmp_path, synthetic_data_dir, out))
        with xr.open_dataset(out) as ds:
            assert "warmth_daily" in ds.attrs["conduit_config"]
            assert len(ds.attrs["conduit_config_sha256"]) == 64

    def test_parsed_config_stamps_no_provenance(self, tmp_path, synthetic_data_dir):
        """An in-memory config has no text to stamp, so it stamps nothing rather
        than something that cannot be trusted to reproduce the run."""
        out = tmp_path / "out.nc"
        run(load_config(_config(tmp_path, synthetic_data_dir, out)))
        with xr.open_dataset(out) as ds:
            assert "conduit_config" not in ds.attrs


class TestRunPreFlight:
    """Everything that must fail *before* the DAG executes."""

    def test_failing_input_check_aborts_before_writing(
        self, tmp_path, synthetic_data_dir
    ):
        """A configured check runs on the real path, not only in a dry run."""
        out = tmp_path / "out.nc"
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            f"""\
[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[inputs.weekly]
path = "{synthetic_data_dir / "weekly.nc"}"
vars = ["pressure"]

[outputs.daily]
path = "{out}"
vars = ["temperature"]

[validation]
checks = [{{ check = "time_equal", inputs = ["daily", "weekly"] }}]
"""
        )
        with pytest.raises(InputCheckError, match="input check\\(s\\) failed"):
            run(cfg)
        assert not out.exists()

    def test_passing_input_check_still_runs(self, tmp_path, synthetic_data_dir):
        out = tmp_path / "out.nc"
        cfg = _config(
            tmp_path,
            synthetic_data_dir,
            out,
            extra=(
                "\n[validation]\n"
                'checks = [{ check = "time_equal", inputs = ["daily"] }]\n'
            ),
        )
        run(cfg)
        assert out.exists()

    def test_missing_output_dir_fails_before_compute(
        self, tmp_path, synthetic_data_dir
    ):
        """Output paths are pre-flighted on the real run, not just in a dry run.

        Otherwise the whole DAG executes and the bad destination only surfaces
        inside save_outputs, after all the work.
        """
        out = tmp_path / "missing" / "out.nc"
        cfg = _config(tmp_path, synthetic_data_dir, out)
        with pytest.raises(FileNotFoundError, match="does not exist"):
            run(cfg)
        assert not out.parent.exists()

    def test_subset_zarr_without_store_fails_before_compute(
        self, tmp_path, synthetic_data_dir
    ):
        out = tmp_path / "out.zarr"
        cfg = _config(
            tmp_path,
            synthetic_data_dir,
            out,
            extra="\n[subset]\nstart = 0\nstop = 2\n",
        )
        with pytest.raises(FileNotFoundError, match="create-store"):
            run(cfg)
        assert not out.exists()

    def test_rejects_inexact_edge_under_exact_policy(self, inexact_units_config):
        """The build-time contract check consults the *process-global* policy, so
        an entry point that skipped `AnnotationPolicySpec.apply` would accept a
        config that another rejects."""
        from xarray_annotated.units import policy

        with policy(enabled=True), pytest.raises(ValueError, match="exact match"):
            run(inexact_units_config)
