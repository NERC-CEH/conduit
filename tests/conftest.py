import multiprocessing
import os
from pathlib import Path

import pytest
import xarray as xr
from synthetic_data import write_synthetic_inputs

from catena.build import build_driver
from catena.config import load_config
from catena.io import load_inputs

multiprocessing.set_start_method("spawn", force=True)
os.environ["XARRAY_ANNOTATED_ENABLED"] = "false"

TEST_CONFIG_PATH = Path(__file__).parent / "test_config.toml"

GRID = (2, 2)
N_DAYS = 365
SEED = 42


@pytest.fixture(scope="session")
def synthetic_data_dir(tmp_path_factory):
    """Generate synthetic data once per test session."""
    data_dir = tmp_path_factory.mktemp("synthetic_data")

    write_synthetic_inputs(
        paths={
            "daily": str(data_dir / "daily.nc"),
            "weekly": str(data_dir / "weekly.nc"),
            "monthly": str(data_dir / "monthly.nc"),
            "static": str(data_dir / "static.nc"),
        },
        grid=GRID,
        n_days=N_DAYS,
        seed=SEED,
    )

    return data_dir


@pytest.fixture(scope="session")
def daily_ds(synthetic_data_dir):
    """Load daily synthetic dataset."""
    return xr.open_dataset(synthetic_data_dir / "daily.nc", decode_coords="all")


@pytest.fixture(scope="session")
def weekly_ds(synthetic_data_dir):
    """Load weekly synthetic dataset."""
    return xr.open_dataset(synthetic_data_dir / "weekly.nc", decode_coords="all")


@pytest.fixture(scope="session")
def monthly_ds(synthetic_data_dir):
    """Load monthly synthetic dataset."""
    return xr.open_dataset(synthetic_data_dir / "monthly.nc", decode_coords="all")


@pytest.fixture(scope="session")
def static_ds(synthetic_data_dir):
    """Load static synthetic dataset."""
    return xr.open_dataset(synthetic_data_dir / "static.nc", decode_coords="all")


@pytest.fixture(scope="session")
def pipeline_config(synthetic_data_dir):
    """Load test config with all paths pointing to the synthetic data dir."""
    config = load_config(TEST_CONFIG_PATH)
    config.input_specs["daily"].path = str(synthetic_data_dir / "daily.nc")
    config.input_specs["weekly"].path = str(synthetic_data_dir / "weekly.nc")
    config.input_specs["monthly"].path = str(synthetic_data_dir / "monthly.nc")
    config.input_specs["static"].path = str(synthetic_data_dir / "static.nc")
    return config


@pytest.fixture(scope="session")
def pipeline_inputs(pipeline_config):
    """Load all inputs using the new load_inputs() API."""
    return load_inputs(pipeline_config.input_specs)


@pytest.fixture(scope="session")
def pipeline_driver(pipeline_config):
    """Build Hamilton driver for integration tests."""
    return build_driver(
        pipeline_config.modules,
        pipeline_config.driver_config,
        node_specs=pipeline_config.node_specs,
    )


@pytest.fixture
def config_toml(tmp_path, synthetic_data_dir):
    """Config TOML pointing to session-scoped synthetic NetCDF files."""
    content = f"""\
[[node]]
name = "mean_temperature_weekly"
inputs = ["temperature_daily"]
expression = "temperature_daily.resample(time='7D').mean()"
units = "degC"
freq = "7D"

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p
