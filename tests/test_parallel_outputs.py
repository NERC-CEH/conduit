"""Tests for parallel/subset output writing: stacked layout, create-store, merge."""

from typing import Any

import numpy as np
import pytest
import xarray as xr

from satterc.config import IOSpec, SubsetSpec
from satterc.io import (
    create_output_store,
    flatten_pixel_index,
    get_final_vars,
    get_outputs,
    load_inputs,
    merge_subset_outputs,
    save_outputs,
    subset_suffix,
    unstack_pixel,
)

VAR = "mean_growth_temperature"


def _output_specs(path) -> dict[str, IOSpec]:
    return {"weekly": IOSpec(path=str(path), vars=[VAR])}


def _execute(driver, config, spec: SubsetSpec | None, output_specs):
    inputs = load_inputs(config.input_specs, subset_spec=spec)
    final_vars: list[Any] = get_final_vars(output_specs)
    results = driver.execute(final_vars, inputs=inputs)  # type: ignore[reportArgumentType]
    return get_outputs(results, output_specs, stacked=spec is not None)


def _full_stacked(driver, config, output_specs):
    """Full-grid result in stacked (pixel) layout."""
    inputs = load_inputs(config.input_specs)
    final_vars: list[Any] = get_final_vars(output_specs)
    results = driver.execute(final_vars, inputs=inputs)  # type: ignore[reportArgumentType]
    return get_outputs(results, output_specs, stacked=True)


@pytest.fixture(scope="module")
def stacked_reference(pipeline_config, pipeline_driver):
    """Full-grid stacked result for the weekly output variable."""
    specs = _output_specs("unused")
    return _full_stacked(pipeline_driver, pipeline_config, specs)["weekly"].compute()


# ---------------------------------------------------------------------------
# Stacking helpers
# ---------------------------------------------------------------------------


class TestStackingHelpers:
    def test_subset_suffix(self):
        assert subset_suffix(SubsetSpec(0, 500)) == "_p0-500"

    def test_flatten_then_unstack_roundtrips(self, pipeline_driver, pipeline_config):
        """A flattened stacked dataset (the on-disk form) unstacks to a grid."""
        specs = _output_specs("unused")
        stacked = _full_stacked(pipeline_driver, pipeline_config, specs)["weekly"]
        assert "pixel" in stacked.dims  # stacked, MultiIndex already flattened
        gridded = unstack_pixel(flatten_pixel_index(stacked))
        assert "pixel" not in gridded.dims
        assert "pixel" not in gridded[VAR].dims


# ---------------------------------------------------------------------------
# NetCDF: unique suffixed files + merge
# ---------------------------------------------------------------------------


class TestNetcdfSubset:
    def test_subsets_write_distinct_files_and_merge(
        self, pipeline_config, pipeline_driver, stacked_reference, tmp_path
    ):
        out = tmp_path / "weekly.nc"
        specs = _output_specs(out)

        for spec in (SubsetSpec(0, 2), SubsetSpec(2, 4)):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

        parts = sorted(tmp_path.glob("weekly_p*.nc"))
        assert [p.name for p in parts] == ["weekly_p0-2.nc", "weekly_p2-4.nc"]
        assert not out.exists()  # un-suffixed path untouched until merge

        merge_subset_outputs(specs)
        gridded = xr.open_dataset(out)
        ref_grid = unstack_pixel(stacked_reference)
        np.testing.assert_allclose(
            gridded[VAR].transpose(*ref_grid[VAR].dims).values,
            ref_grid[VAR].values,
            equal_nan=True,
        )


# ---------------------------------------------------------------------------
# Zarr: shared pre-created store + region writes + merge
# ---------------------------------------------------------------------------


class TestZarrSubset:
    def test_create_store_region_write_and_merge(
        self, pipeline_config, pipeline_driver, stacked_reference, tmp_path
    ):
        store = tmp_path / "weekly.zarr"
        specs = _output_specs(store)

        created = create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)
        assert created == [str(store)]

        # Freshly created store is all-NaN with the full pixel extent.
        empty = xr.open_zarr(store, consolidated=False)
        assert empty.sizes["pixel"] == stacked_reference.sizes["pixel"]
        assert bool(np.isnan(empty[VAR].values).all())

        for spec in (SubsetSpec(0, 2), SubsetSpec(2, 4)):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

        filled = xr.open_zarr(store, consolidated=False).compute()
        # No gaps: anywhere the reference has data, the store has data.
        ref = stacked_reference.transpose("time", "pixel")
        got = filled[VAR].transpose("time", "pixel").values
        gaps = np.isnan(got) & ~np.isnan(ref[VAR].values)
        assert gaps.sum() == 0
        np.testing.assert_allclose(got, ref[VAR].values, equal_nan=True)

        merge_subset_outputs(specs)
        gridded = xr.open_zarr(tmp_path / "weekly_gridded.zarr", consolidated=False)
        assert set(gridded[VAR].dims) == set(unstack_pixel(stacked_reference)[VAR].dims)

    def test_merge_out_override(self, pipeline_config, pipeline_driver, tmp_path):
        """--out writes the merged grid to an explicit path."""
        store = tmp_path / "weekly.zarr"
        specs = _output_specs(store)
        create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)
        for spec in (SubsetSpec(0, 2), SubsetSpec(2, 4)):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

        dest = tmp_path / "custom.zarr"
        written = merge_subset_outputs(specs, out=dest)
        assert written == [str(dest)]
        assert dest.exists()
        assert not (tmp_path / "weekly_gridded.zarr").exists()

    def test_multi_frequency_and_static_outputs(
        self, pipeline_config, pipeline_driver, tmp_path
    ):
        """create-store + region writes cover several frequencies, incl. static."""
        specs = {
            "daily": IOSpec(path=str(tmp_path / "daily.zarr"), vars=["temperature"]),
            "static": IOSpec(path=str(tmp_path / "static.zarr"), vars=["clay_content"]),
        }

        created = create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)
        assert len(created) == 2

        for spec in (SubsetSpec(0, 2), SubsetSpec(2, 4)):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

        ref = _full_stacked(pipeline_driver, pipeline_config, specs)

        # Daily output carries a time axis.
        daily = xr.open_zarr(tmp_path / "daily.zarr", consolidated=False).compute()
        assert set(daily["temperature"].dims) == {"time", "pixel"}
        np.testing.assert_allclose(
            daily["temperature"].transpose("time", "pixel").values,
            ref["daily"]["temperature"].transpose("time", "pixel").compute().values,
            equal_nan=True,
        )

        # Static output is pixel-only (no time dimension).
        static = xr.open_zarr(tmp_path / "static.zarr", consolidated=False).compute()
        assert set(static["clay_content"].dims) == {"pixel"}
        np.testing.assert_allclose(
            static["clay_content"].values,
            ref["static"]["clay_content"].compute().values,
            equal_nan=True,
        )

    def test_create_store_refuses_to_clobber(
        self, pipeline_config, pipeline_driver, tmp_path
    ):
        """Re-creating an existing store needs --overwrite, to protect written data."""
        store = tmp_path / "weekly.zarr"
        specs = _output_specs(store)
        create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)

        # Write something, then prove a second create-store won't silently wipe it.
        save_outputs(
            _execute(pipeline_driver, pipeline_config, SubsetSpec(0, 2), specs),
            specs,
            subset_spec=SubsetSpec(0, 2),
        )
        with pytest.raises(FileExistsError, match="overwrite"):
            create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)

        # overwrite=True recreates it as an empty (all-NaN) store.
        create_output_store(
            pipeline_config.input_specs, specs, pixel_chunk=2, overwrite=True
        )
        recreated = xr.open_zarr(store, consolidated=False).compute()
        assert bool(np.isnan(recreated[VAR].values).all())

    def test_merge_out_rejected_for_multiple_outputs(self):
        specs = {
            "daily": IOSpec(path="a.zarr", vars=[VAR]),
            "weekly": IOSpec(path="b.zarr", vars=[VAR]),
        }
        with pytest.raises(ValueError, match="multiple"):
            merge_subset_outputs(specs, out="x.zarr")


# ---------------------------------------------------------------------------
# CLI end-to-end: create-store -> subset runs -> merge
# ---------------------------------------------------------------------------


def _config_text(synthetic_data_dir, out_path, subset=None, block_size=2):
    blocks = f"""\
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
vars = ["{VAR}"]

[blocking]
block_size = {block_size}
"""
    if subset is not None:
        blocks += f"\n[subset]\npixel_start = {subset[0]}\npixel_end = {subset[1]}\n"
    return blocks


class TestCLIParallelWorkflow:
    def test_zarr_create_run_merge(
        self, tmp_path, synthetic_data_dir, pipeline_config, pipeline_driver
    ):
        from typer.testing import CliRunner

        from satterc.cli import app

        store = tmp_path / "weekly.zarr"
        runner = CliRunner()

        base = tmp_path / "base.toml"
        base.write_text(_config_text(synthetic_data_dir, store))
        cfg_a = tmp_path / "a.toml"
        cfg_a.write_text(_config_text(synthetic_data_dir, store, subset=(0, 2)))
        cfg_b = tmp_path / "b.toml"
        cfg_b.write_text(_config_text(synthetic_data_dir, store, subset=(2, 4)))

        # create-store derives the pixel chunk from [blocking].block_size = 2
        r = runner.invoke(app, ["create-store", str(base)])
        assert r.exit_code == 0, r.output
        assert store.exists()

        for cfg in (cfg_a, cfg_b):
            r = runner.invoke(app, ["run", str(cfg)])
            assert r.exit_code == 0, r.output

        filled = xr.open_zarr(store, consolidated=False).compute()
        ref = (
            _full_stacked(pipeline_driver, pipeline_config, _output_specs(store))[
                "weekly"
            ]
            .transpose("time", "pixel")
            .compute()
        )
        gaps = np.isnan(filled[VAR].transpose("time", "pixel").values) & ~np.isnan(
            ref[VAR].values
        )
        assert gaps.sum() == 0
        np.testing.assert_allclose(
            filled[VAR].transpose("time", "pixel").values,
            ref[VAR].values,
            equal_nan=True,
        )

        r = runner.invoke(app, ["merge", str(base)])
        assert r.exit_code == 0, r.output
        assert (tmp_path / "weekly_gridded.zarr").exists()


# ---------------------------------------------------------------------------
# True concurrency: independent processes region-writing simultaneously
# ---------------------------------------------------------------------------


class TestConcurrentZarrWrites:
    """Mirror the real deployment: N OS processes writing disjoint regions at once.

    The sequential tests validate correctness but not concurrency safety. Here we
    launch genuinely independent ``satterc run`` processes (as ``parallel satterc
    run`` would) against one shared store and assert no writes are lost.
    """

    def test_independent_processes_no_lost_writes(
        self, tmp_path, synthetic_data_dir, pipeline_config, pipeline_driver
    ):
        import subprocess
        import sys

        from typer.testing import CliRunner

        from satterc.cli import app

        store = tmp_path / "weekly.zarr"

        # One shard per pixel (chunk size 1) => 4 processes each writing a distinct,
        # chunk-disjoint region of the 2x2 grid simultaneously.
        shards = [(i, i + 1) for i in range(4)]

        base = tmp_path / "base.toml"
        base.write_text(_config_text(synthetic_data_dir, store, block_size=1))
        shard_cfgs = []
        for start, end in shards:
            cfg = tmp_path / f"shard_{start}.toml"
            cfg.write_text(
                _config_text(
                    synthetic_data_dir, store, subset=(start, end), block_size=1
                )
            )
            shard_cfgs.append(cfg)

        # Create the shared store once (pixel chunk = 1) before the parallel writes.
        r = CliRunner().invoke(app, ["create-store", str(base), "--pixel-chunk", "1"])
        assert r.exit_code == 0, r.output

        # Launch all shards at once; collect output after they are all running.
        procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "from satterc.cli import app; app()",
                    "run",
                    str(cfg),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for cfg in shard_cfgs
        ]
        outputs = [p.communicate()[0] for p in procs]
        for cfg, proc, out in zip(shard_cfgs, procs, outputs, strict=True):
            assert proc.returncode == 0, f"{cfg.name} failed:\n{out}"

        filled = xr.open_zarr(store, consolidated=False).compute()
        ref = (
            _full_stacked(pipeline_driver, pipeline_config, _output_specs(store))[
                "weekly"
            ]
            .transpose("time", "pixel")
            .compute()
        )
        got = filled[VAR].transpose("time", "pixel").values
        # No lost writes: every pixel the reference has data for is present.
        gaps = np.isnan(got) & ~np.isnan(ref[VAR].values)
        assert gaps.sum() == 0
        np.testing.assert_allclose(got, ref[VAR].values, equal_nan=True)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestSubsetErrors:
    def test_region_write_missing_store_raises(
        self, pipeline_config, pipeline_driver, tmp_path
    ):
        specs = _output_specs(tmp_path / "missing.zarr")
        spec = SubsetSpec(0, 2)
        with pytest.raises(FileNotFoundError, match="create-store"):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

    def test_misaligned_subset_raises(self, pipeline_config, pipeline_driver, tmp_path):
        store = tmp_path / "weekly.zarr"
        specs = _output_specs(store)
        create_output_store(pipeline_config.input_specs, specs, pixel_chunk=2)

        spec = SubsetSpec(1, 3)  # not aligned to chunk size 2
        with pytest.raises(ValueError, match="aligned"):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )

    def test_csv_subset_raises(self, pipeline_config, pipeline_driver, tmp_path):
        specs = _output_specs(tmp_path / "weekly.csv")
        spec = SubsetSpec(0, 2)
        with pytest.raises(ValueError, match="only supported for NetCDF"):
            save_outputs(
                _execute(pipeline_driver, pipeline_config, spec, specs),
                specs,
                subset_spec=spec,
            )
