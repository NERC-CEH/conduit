"""Tests for the [subset] spatial pixel slicing feature."""

from typing import Any

import numpy as np
import pytest
import xarray as xr

from breadboard.config import Config, IOSpec, SubsetSpec
from breadboard.dag.driver import build_driver
from breadboard.io import get_final_vars, load_inputs

_FINAL_VARS = get_final_vars(
    {"weekly": IOSpec(path="", vars=["mean_growth_temperature"])}
)


# ---------------------------------------------------------------------------
# SubsetSpec config validation
# ---------------------------------------------------------------------------


class TestSubsetSpecValidation:
    def test_valid(self):
        spec = SubsetSpec.from_config({"pixel_start": 0, "pixel_end": 500})
        assert spec.pixel_start == 0
        assert spec.pixel_end == 500

    def test_missing_pixel_start_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SubsetSpec.from_config({"pixel_end": 500})

    def test_missing_pixel_end_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SubsetSpec.from_config({"pixel_start": 0})

    def test_negative_pixel_start_raises(self):
        with pytest.raises(ValueError, match="pixel_start"):
            SubsetSpec.from_config({"pixel_start": -1, "pixel_end": 500})

    def test_negative_pixel_end_raises(self):
        with pytest.raises(ValueError, match="pixel_end"):
            SubsetSpec.from_config({"pixel_start": 0, "pixel_end": -1})

    def test_pixel_end_equal_to_start_raises(self):
        with pytest.raises(ValueError, match="pixel_end"):
            SubsetSpec.from_config({"pixel_start": 5, "pixel_end": 5})

    def test_pixel_end_less_than_start_raises(self):
        with pytest.raises(ValueError, match="pixel_end"):
            SubsetSpec.from_config({"pixel_start": 5, "pixel_end": 3})

    def test_non_integer_raises(self):
        with pytest.raises(ValueError, match="pixel_start"):
            SubsetSpec.from_config({"pixel_start": 0.5, "pixel_end": 500})

    def test_parsed_from_toml(self):
        parsed = Config.loads("[subset]\npixel_start = 0\npixel_end = 100\n").parse()
        assert parsed.subset_spec == SubsetSpec(pixel_start=0, pixel_end=100)

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
        spec_a = SubsetSpec(pixel_start=0, pixel_end=2)
        spec_b = SubsetSpec(pixel_start=2, pixel_end=4)

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

        spec = SubsetSpec(pixel_start=0, pixel_end=2)
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
        dr = build_driver(pipeline_config.modules, pipeline_config.driver_config)
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
    """breadboard run with [subset] exits zero and writes only the subset pixels."""

    @pytest.fixture
    def subset_config_toml(self, tmp_path, synthetic_data_dir):
        out_path = tmp_path / "outputs.nc"
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

[outputs.weekly]
path = "{out_path}"
vars = ["mean_growth_temperature"]

[subset]
pixel_start = 0
pixel_end = 2
"""
        p = tmp_path / "config.toml"
        p.write_text(content)
        return p, out_path

    def _subset_path(self, out_path):
        """The auto-suffixed NetCDF path a [subset] run writes to."""
        from breadboard.io import subset_suffix

        spec = SubsetSpec(0, 2)
        return out_path.with_name(
            f"{out_path.stem}{subset_suffix(spec)}{out_path.suffix}"
        )

    def test_exits_zero(self, subset_config_toml):
        from typer.testing import CliRunner

        from breadboard.cli import app

        config_path, _ = subset_config_toml
        result = CliRunner().invoke(app, ["run", str(config_path)])
        assert result.exit_code == 0, result.output

    def test_output_is_stacked_subset(self, subset_config_toml):
        """A subset run writes a uniquely-suffixed, stacked (pixel) file."""
        from typer.testing import CliRunner

        from breadboard.cli import app

        config_path, out_path = subset_config_toml
        CliRunner().invoke(app, ["run", str(config_path)])

        # The un-suffixed path is never written; the suffixed one holds 2 pixels.
        assert not out_path.exists()
        ds = xr.open_dataset(self._subset_path(out_path))
        assert ds.sizes["pixel"] == 2

    def test_output_values_match_full_run(self, subset_config_toml):
        from typer.testing import CliRunner

        from breadboard.cli import app
        from breadboard.config import load_config
        from breadboard.io import get_outputs

        config_path, out_path = subset_config_toml
        CliRunner().invoke(app, ["run", str(config_path)])
        subset_ds = xr.open_dataset(self._subset_path(out_path))

        parsed = load_config(config_path)
        parsed.subset_spec = None
        dr = build_driver(parsed.modules, parsed.driver_config)
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
