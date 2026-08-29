"""Generate the synthetic input for the Pipeline 101 recipe.

Writes 90 days of daily temperature at three sites to ``data/climate.nc``,
relative to this file. The series is deterministic, so the pipeline output is
reproducible.

Run it directly, or call :func:`write_inputs` from a notebook.
"""

from pathlib import Path

import numpy as np
import xarray as xr

DATA_DIR = Path(__file__).parent / "data"


def write_inputs(data_dir: Path = DATA_DIR) -> Path:
    """Write the climate NetCDF file, returning its path."""
    data_dir.mkdir(parents=True, exist_ok=True)

    time = xr.date_range("2020-01-01", periods=90, freq="D")
    seasonal = 10.0 + 8.0 * np.sin(np.linspace(0.0, np.pi, time.size))
    per_site = np.arange(3.0)

    temperature = xr.DataArray(
        seasonal[:, None] + per_site,
        dims=("time", "site"),
        coords={"time": time, "site": ["a", "b", "c"]},
        attrs={"units": "degC", "long_name": "near-surface air temperature"},
    )

    path = data_dir / "climate.nc"
    xr.Dataset({"temperature": temperature}).to_netcdf(path)
    return path


if __name__ == "__main__":
    _written = write_inputs()
    _cwd = Path.cwd()
    print(
        f"wrote {_written.relative_to(_cwd) if _written.is_relative_to(_cwd) else _written}"
    )
