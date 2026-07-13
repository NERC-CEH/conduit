"""Tests for the [subset] spatial pixel slicing feature."""

from typing import Any

import numpy as np
import pytest
import xarray as xr

from conduit.config import Config, IOSpec, SubsetSpec
from conduit.dag.driver import build_driver
from conduit.io import get_final_vars, load_inputs

_FINAL_VARS = get_final_vars({"weekly": IOSpec(path="", vars=["mean_temperature"])})


# ---------------------------------------------------------------------------
# SubsetSpec config validation
# ---------------------------------------------------------------------------


class TestSubsetSpecValidation:
    def test_valid(self):
        spec = SubsetSpec.from_config({"start": 0, "stop": 500})
        assert spec.start == 0
        assert spec.stop == 500

    def test_dim_defaults_to_pixel(self):
        assert SubsetSpec.from_config({"start": 0, "stop": 500}).dim == "pixel"

    def test_dim_can_be_any_dimension(self):
        spec = SubsetSpec.from_config({"start": 0, "stop": 10, "dim": "location"})
        assert spec.dim == "location"

    def test_empty_dim_raises(self):
        with pytest.raises(ValueError, match="'dim'"):
            SubsetSpec.from_config({"start": 0, "stop": 10, "dim": ""})

    def test_missing_start_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SubsetSpec.from_config({"stop": 500})

    def test_missing_stop_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SubsetSpec.from_config({"start": 0})

    def test_negative_start_raises(self):
        with pytest.raises(ValueError, match="'start'"):
            SubsetSpec.from_config({"start": -1, "stop": 500})

    def test_negative_stop_raises(self):
        with pytest.raises(ValueError, match="'stop'"):
            SubsetSpec.from_config({"start": 0, "stop": -1})

    def test_stop_equal_to_start_raises(self):
        with pytest.raises(ValueError, match="'stop'"):
            SubsetSpec.from_config({"start": 5, "stop": 5})

    def test_stop_less_than_start_raises(self):
        with pytest.raises(ValueError, match="'stop'"):
            SubsetSpec.from_config({"start": 5, "stop": 3})

    def test_non_integer_raises(self):
        with pytest.raises(ValueError, match="'start'"):
            SubsetSpec.from_config({"start": 0.5, "stop": 500})

    def test_parsed_from_toml(self):
        parsed = Config.loads("[subset]\nstart = 0\nstop = 100\n").parse()
        assert parsed.subset_spec == SubsetSpec(start=0, stop=100)

    def test_absent_section_gives_none(self):
        parsed = Config.loads("[grid]\n").parse()
        assert parsed.subset_spec is None


# ---------------------------------------------------------------------------
# Correctness: subsets reconstruct the full inputs
# ---------------------------------------------------------------------------


class TestSubsetCorrectness:
    """Two complementary subsets concatenate back to the full inputs."""

    def test_pixel_coords_correct(self, pipeline_config, pipeline_inputs):
        """Each subset contains the right pixel coordinates."""
        spec_a = SubsetSpec(start=0, stop=2)
        spec_b = SubsetSpec(start=2, stop=4)

        inputs_a = load_inputs(pipeline_config.input_specs, subset_spec=spec_a)
        inputs_b = load_inputs(pipeline_config.input_specs, subset_spec=spec_b)

        for name, full_val in pipeline_inputs.items():
            if not (isinstance(full_val, xr.DataArray) and "pixel" in full_val.dims):
                continue
            combined = xr.concat([inputs_a[name], inputs_b[name]], dim="pixel")
            xr.testing.assert_identical(combined, full_val)

    def test_no_pixel_inputs_unaffected(self, pipeline_config, pipeline_inputs):
        """Non-pixel inputs (dates, scalars) pass through unchanged."""
        import pandas as pd

        spec = SubsetSpec(start=0, stop=2)
        inputs_sub = load_inputs(pipeline_config.input_specs, subset_spec=spec)

        for name, full_val in pipeline_inputs.items():
            if isinstance(full_val, xr.DataArray) and "pixel" in full_val.dims:
                continue
            if isinstance(full_val, xr.DataArray):
                xr.testing.assert_identical(inputs_sub[name], full_val)
            elif isinstance(full_val, pd.DatetimeIndex):
                assert inputs_sub[name].equals(full_val)


# ---------------------------------------------------------------------------
# Pipeline result: two subsets concatenate to the full result
# ---------------------------------------------------------------------------


class TestSubsetPipelineResult:
    """Running on subsets and concatenating reproduces the unsubsetted result."""

    def test_two_halves_match_full(self, pipeline_config, pipeline_inputs):
        dr = build_driver(
            pipeline_config.modules,
            pipeline_config.driver_config,
            node_specs=pipeline_config.node_specs,
        )
        reference = dr.execute(_FINAL_VARS, inputs=pipeline_inputs)  # type: ignore[reportArgumentType]

        inputs_a = load_inputs(
            pipeline_config.input_specs, subset_spec=SubsetSpec(0, 2)
        )
        inputs_b = load_inputs(
            pipeline_config.input_specs, subset_spec=SubsetSpec(2, 4)
        )
        result_a = dr.execute(_FINAL_VARS, inputs=inputs_a)  # type: ignore[reportArgumentType]
        result_b = dr.execute(_FINAL_VARS, inputs=inputs_b)  # type: ignore[reportArgumentType]

        for var in _FINAL_VARS:
            combined = xr.concat([result_a[var], result_b[var]], dim="pixel")
            xr.testing.assert_identical(combined, reference[var])


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


class TestCLISubset:
    """conduit run with [subset] exits zero and writes only the subset pixels."""

    @pytest.fixture
    def subset_config_toml(self, tmp_path, synthetic_data_dir):
        out_path = tmp_path / "outputs.nc"
        # Load only what the pipeline consumes (temperature_daily), so a real
        # ``conduit run`` stays free of the unused-input WiringWarning. Broad
        # multi-section configs are exercised by the parser tests instead.
        content = f"""\
[[node]]
name = "mean_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"

[grid]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[outputs.weekly]
path = "{out_path}"
vars = ["mean_temperature"]

[subset]
start = 0
stop = 2
"""
        p = tmp_path / "config.toml"
        p.write_text(content)
        return p, out_path

    def _subset_path(self, out_path):
        """The auto-suffixed NetCDF path a [subset] run writes to."""
        from conduit.gridded.io import subset_suffix

        spec = SubsetSpec(0, 2)
        return out_path.with_name(
            f"{out_path.stem}{subset_suffix(spec)}{out_path.suffix}"
        )

    def test_exits_zero(self, subset_config_toml):
        from typer.testing import CliRunner

        from conduit.cli import app

        config_path, _ = subset_config_toml
        result = CliRunner().invoke(app, ["run", str(config_path)])
        assert result.exit_code == 0, result.output

    def test_output_is_stacked_subset(self, subset_config_toml):
        """A subset run writes a uniquely-suffixed, stacked (pixel) file."""
        from typer.testing import CliRunner

        from conduit.cli import app

        config_path, out_path = subset_config_toml
        CliRunner().invoke(app, ["run", str(config_path)])

        # The un-suffixed path is never written; the suffixed one holds 2 pixels.
        assert not out_path.exists()
        ds = xr.open_dataset(self._subset_path(out_path))
        assert ds.sizes["pixel"] == 2

    def test_output_values_match_full_run(self, subset_config_toml):
        from typer.testing import CliRunner

        from conduit.cli import app
        from conduit.config import load_config
        from conduit.io import get_outputs

        config_path, out_path = subset_config_toml
        CliRunner().invoke(app, ["run", str(config_path)])
        subset_ds = xr.open_dataset(self._subset_path(out_path))

        parsed = load_config(config_path)
        parsed.subset_spec = None
        dr = build_driver(
            parsed.modules, parsed.driver_config, node_specs=parsed.node_specs
        )
        full_inputs = load_inputs(parsed.input_specs)
        final_vars: list[Any] = get_final_vars(parsed.output_specs)
        full_results = dr.execute(final_vars, inputs=full_inputs)  # type: ignore[reportArgumentType]
        ref_ds = get_outputs(full_results, parsed.output_specs, stacked=True)["weekly"]

        for var in subset_ds.data_vars:
            np.testing.assert_allclose(
                subset_ds[var].transpose("time", "pixel").values,
                ref_ds[var].transpose("time", "pixel").isel(pixel=slice(0, 2)).values,
                equal_nan=True,
            )
