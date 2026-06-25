"""Tests for Mechanism B: pixel-blocked driver execution.

Verifies that execute_blocked() produces results identical to an unblocked
dr.execute() call, regardless of block size.
"""

import numpy as np
import pytest
import xarray as xr

from satterc.config import BlockingSpec, Config, IOSpec
from satterc.dag.blocking import (
    _concat_results,
    _make_blocks,
    _pixel_input_names,
    execute_blocked,
)
from satterc.dag.driver import build_driver
from satterc.io import get_final_vars

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINAL_VARS = get_final_vars(
    {"weekly": IOSpec(path="", vars=["mean_growth_temperature"])}
)


def _run_unblocked(pipeline_config, pipeline_inputs):
    dr = build_driver(pipeline_config.modules, pipeline_config.driver_config)
    return dr.execute(_FINAL_VARS, inputs=pipeline_inputs)  # type: ignore[reportArgumentType]


def _run_blocked(pipeline_config, pipeline_inputs, block_size):
    spec = BlockingSpec(block_size=block_size)
    dr = build_driver(pipeline_config.modules, pipeline_config.driver_config)
    return execute_blocked(dr, pipeline_inputs, _FINAL_VARS, spec)


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


class TestPixelInputNames:
    def test_identifies_pixel_arrays(self):
        da_pixel = xr.DataArray(np.zeros((3, 4)), dims=["time", "pixel"])
        da_time = xr.DataArray(np.zeros(3), dims=["time"])
        scalar = 42
        inputs = {"a": da_pixel, "b": da_time, "c": scalar}
        assert _pixel_input_names(inputs) == ["a"]

    def test_empty_when_no_pixel_dim(self):
        inputs = {"x": xr.DataArray(np.zeros(3), dims=["time"])}
        assert _pixel_input_names(inputs) == []


class TestMakeBlocks:
    def _inputs(self, n_pixels: int) -> dict:
        da = xr.DataArray(
            np.arange(n_pixels, dtype=float),
            dims=["pixel"],
            coords={"pixel": np.arange(n_pixels)},
        )
        return {"da": da, "scalar": 1.0}

    def test_exact_divisor(self):
        blocks = list(_make_blocks(self._inputs(6), ["da"], block_size=3))
        assert len(blocks) == 2
        assert blocks[0]["da"].sizes["pixel"] == 3
        assert blocks[1]["da"].sizes["pixel"] == 3

    def test_non_divisor_last_block_smaller(self):
        blocks = list(_make_blocks(self._inputs(5), ["da"], block_size=3))
        assert len(blocks) == 2
        assert blocks[0]["da"].sizes["pixel"] == 3
        assert blocks[1]["da"].sizes["pixel"] == 2

    def test_block_size_exceeds_n_pixels(self):
        blocks = list(_make_blocks(self._inputs(3), ["da"], block_size=10))
        assert len(blocks) == 1
        assert blocks[0]["da"].sizes["pixel"] == 3

    def test_non_pixel_inputs_passed_through_unchanged(self):
        inputs = self._inputs(4)
        blocks = list(_make_blocks(inputs, ["da"], block_size=2))
        for b in blocks:
            assert b["scalar"] == 1.0

    def test_no_pixel_names_yields_full_inputs(self):
        inputs = {"x": 1}
        blocks = list(_make_blocks(inputs, [], block_size=3))
        assert len(blocks) == 1
        assert blocks[0] is inputs

    def test_pixel_coords_are_preserved(self):
        da = xr.DataArray(
            np.arange(6.0),
            dims=["pixel"],
            coords={"pixel": np.arange(6)},
        )
        blocks = list(_make_blocks({"da": da}, ["da"], block_size=3))
        assert list(blocks[0]["da"].coords["pixel"].values) == [0, 1, 2]
        assert list(blocks[1]["da"].coords["pixel"].values) == [3, 4, 5]


class TestConcatResults:
    def test_concatenates_along_pixel(self):
        b1 = {
            "x": xr.DataArray(
                [1.0, 2.0],
                dims=["pixel"],
                coords={"pixel": [0, 1]},
            )
        }
        b2 = {
            "x": xr.DataArray(
                [3.0, 4.0],
                dims=["pixel"],
                coords={"pixel": [2, 3]},
            )
        }
        result = _concat_results([b1, b2], ["x"])
        assert result["x"].sizes["pixel"] == 4
        np.testing.assert_array_equal(result["x"].values, [1.0, 2.0, 3.0, 4.0])

    def test_raises_on_no_pixel_dim(self):
        blocks = [{"x": xr.DataArray([1.0, 2.0], dims=["time"])}] * 2
        with pytest.raises(ValueError, match="pixel"):
            _concat_results(blocks, ["x"])

    def test_raises_on_scalar(self):
        blocks = [{"x": xr.DataArray(1.0)}] * 2
        with pytest.raises(ValueError, match="pixel"):
            _concat_results(blocks, ["x"])


# ---------------------------------------------------------------------------
# BlockingSpec config parsing
# ---------------------------------------------------------------------------


class TestBlockingSpecValidation:
    def test_valid(self):
        spec = BlockingSpec.from_config({"block_size": 4})
        assert spec.block_size == 4

    def test_missing_block_size_raises(self):
        with pytest.raises(ValueError, match="block_size"):
            BlockingSpec.from_config({})

    def test_zero_block_size_raises(self):
        with pytest.raises(ValueError, match="block_size"):
            BlockingSpec.from_config({"block_size": 0})

    def test_negative_block_size_raises(self):
        with pytest.raises(ValueError, match="block_size"):
            BlockingSpec.from_config({"block_size": -1})

    def test_string_block_size_raises(self):
        with pytest.raises(ValueError, match="block_size"):
            BlockingSpec.from_config({"block_size": "4"})

    def test_parsed_from_toml(self):
        parsed = Config.loads("[blocking]\nblock_size = 8\n").parse()
        assert parsed.blocking_spec == BlockingSpec(block_size=8)

    def test_absent_section_gives_none(self):
        parsed = Config.loads("[models.pmodel]\n").parse()
        assert parsed.blocking_spec is None


# ---------------------------------------------------------------------------
# Partition invariance (core correctness)
# ---------------------------------------------------------------------------


class TestPartitionInvariance:
    """Blocked runs must reproduce the unblocked result exactly, for any partition."""

    @pytest.fixture(scope="class")
    def reference(self, pipeline_config, pipeline_inputs):
        return _run_unblocked(pipeline_config, pipeline_inputs)

    @pytest.mark.parametrize("block_size", [1, 2, 3, 100])
    def test_blocked_matches_unblocked(
        self, pipeline_config, pipeline_inputs, reference, block_size
    ):
        result = _run_blocked(pipeline_config, pipeline_inputs, block_size)
        for var in _FINAL_VARS:
            xr.testing.assert_identical(result[var], reference[var])


# ---------------------------------------------------------------------------
# Caching with blocking
# ---------------------------------------------------------------------------


class TestCachingWithBlocking:
    """Blocking and Hamilton caching coexist correctly.

    Each block gets its own cache entry (pixel coords fold into the hash),
    so a warm re-run hits cache without recomputing.
    """

    def test_blocked_cached_matches_unblocked(
        self, pipeline_config, pipeline_inputs, tmp_path
    ):
        from satterc import CacheSpec

        spec = BlockingSpec(block_size=2)
        cache = CacheSpec(path=str(tmp_path / "cache"))

        def _run_blocked_cached():
            dr = build_driver(
                pipeline_config.modules, pipeline_config.driver_config, cache=cache
            )
            return execute_blocked(dr, pipeline_inputs, _FINAL_VARS, spec)

        reference = _run_unblocked(pipeline_config, pipeline_inputs)
        _run_blocked_cached()  # cold cache
        result = _run_blocked_cached()  # warm cache

        for var in _FINAL_VARS:
            xr.testing.assert_identical(result[var], reference[var])


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


class TestCLIEndToEnd:
    """satterc run with a [blocking] section exits zero and writes outputs."""

    @pytest.fixture
    def blocking_config_toml(self, tmp_path, synthetic_data_dir):
        out_path = tmp_path / "outputs.nc"
        content = f"""\
[models.pmodel]
method_kphio = "sandoval"
method_optchi = "lavergne20_c3"

[models.rothc]
n_years_spinup = 1

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

[blocking]
block_size = 2
"""
        p = tmp_path / "config.toml"
        p.write_text(content)
        return p, out_path

    def test_exits_zero(self, blocking_config_toml):
        from typer.testing import CliRunner

        from satterc.cli import app

        config_path, _ = blocking_config_toml
        result = CliRunner().invoke(app, ["run", str(config_path)])
        assert result.exit_code == 0, result.output

    def test_output_file_written(self, blocking_config_toml):
        from typer.testing import CliRunner

        from satterc.cli import app

        config_path, out_path = blocking_config_toml
        CliRunner().invoke(app, ["run", str(config_path)])
        assert out_path.exists()

    def test_output_matches_unblocked(self, blocking_config_toml):
        import xarray as xr
        from typer.testing import CliRunner

        from satterc.cli import app

        config_path, out_path = blocking_config_toml
        # Run with blocking.
        CliRunner().invoke(app, ["run", str(config_path)])
        blocked_ds = xr.open_dataset(out_path)

        # Run without blocking for reference.
        from satterc.config import load_config
        from satterc.dag.driver import build_driver
        from satterc.io import get_outputs, load_inputs

        parsed = load_config(config_path)
        parsed.blocking_spec = None
        dr = build_driver(parsed.modules, parsed.driver_config)
        inputs = load_inputs(parsed.input_specs)
        final_vars = get_final_vars(parsed.output_specs)
        ref_results = dr.execute(final_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        # get_outputs assembles results into per-frequency Datasets with the
        # same variable names the save/load round-trip uses (no freq suffix).
        ref_datasets = get_outputs(ref_results, parsed.output_specs)
        ref_ds = ref_datasets["weekly"]

        for var in blocked_ds.data_vars:
            xr.testing.assert_allclose(blocked_ds[var], ref_ds[var])
