"""Generate the synthetic inputs for the flux pipeline.

Writes a year of half-hourly eddy-covariance data to ``data/flux.nc`` and
weekly satellite GPP to ``data/satellite.nc``, both relative to this file.
The series are deterministic, so the pipeline products are reproducible.

Run it directly, or call :func:`write_inputs` from a notebook.
"""

from pathlib import Path

import numpy as np
import xarray as xr

DATA_DIR = Path(__file__).parent / "data"
SEED = 20240301


def _series(
    values: np.ndarray,
    time: np.ndarray,
    units: str,
    dtype: str = "float64",
) -> xr.DataArray:
    return xr.DataArray(
        values.astype(dtype),
        dims="time",
        coords={"time": time},
        attrs={"units": units},
    )


def write_inputs(data_dir: Path = DATA_DIR) -> tuple[Path, Path]:
    """Write the flux and satellite NetCDF files, returning their paths."""
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    time = np.arange(
        "2023-01-01", "2024-01-01", np.timedelta64(30, "m"), dtype="datetime64[s]"
    )
    day = (time.astype("datetime64[D]") - np.datetime64("2023-01-01", "D")).astype(int)
    hour = (time.astype("datetime64[s]").astype(int) % 86400) / 3600.0

    # Clear-sky solar elevation for a site at 52 degrees north.
    declination = np.deg2rad(23.44) * np.sin(2 * np.pi * (day - 80) / 365.25)
    latitude = np.deg2rad(52.0)
    hour_angle = np.deg2rad(15.0 * (hour - 12.0))
    solar_elevation = np.clip(
        np.sin(latitude) * np.sin(declination)
        + np.cos(latitude) * np.cos(declination) * np.cos(hour_angle),
        0,
        None,
    )

    ppfd_values = (
        2100.0
        * solar_elevation
        * (0.85 + 0.15 * rng.normal(size=time.size).clip(-1, 1))
    ).clip(0)
    tair_c = (
        9.5
        + 8.5 * np.sin(2 * np.pi * (day - 110) / 365.25)
        + 4.0 * np.sin(2 * np.pi * (hour - 9) / 24.0)
        + 0.8 * rng.normal(size=time.size)
    )

    # Q10 respiration against a light- and temperature-limited GPP.
    reco = 2.60 * 2.0 ** ((tair_c - 10.0) / 10.0)
    lai = 0.25 + 0.75 * np.clip(np.sin(np.pi * (day - 90) / 190.0), 0, None)
    gpp_max = 21.4 * lai
    gpp = np.where(
        ppfd_values > 0,
        0.055 * ppfd_values * gpp_max / (0.055 * ppfd_values + gpp_max),
        0.0,
    ) / (1.0 + np.exp(-(tair_c - 2.0)))
    nee = reco - gpp + 0.35 * rng.normal(size=time.size)

    qc = np.zeros(time.size, dtype="int8")
    qc[rng.random(time.size) < 0.07] = 1
    qc[rng.random(time.size) < 0.02] = 2

    flux_path = data_dir / "flux.nc"
    xr.Dataset(
        {
            "nee_raw": _series(nee, time, "umol m-2 s-1"),
            "tair": _series(tair_c + 273.15, time, "K"),
            "ppfd": _series(ppfd_values, time, "umol m-2 s-1"),
            "qc": _series(qc, time, "1", dtype="int8"),
        }
    ).to_netcdf(flux_path)

    # Weekly satellite GPP in g C m-2 d-1, with a multiplicative retrieval error.
    conversion = 1e-6 * 12.011 * 86400.0
    gpp_daily = (
        _series(gpp, time, "umol m-2 s-1").resample(time="D").mean() * conversion
    )
    weekly = gpp_daily.resample(time="W-SUN")
    sat_gpp = (
        weekly.mean() * (1.0 + 0.08 * rng.normal(size=weekly.count().size))
    ).assign_attrs(units="g m-2 d-1")

    satellite_path = data_dir / "satellite.nc"
    xr.Dataset({"sat_gpp": sat_gpp}).to_netcdf(satellite_path)

    return flux_path, satellite_path


if __name__ == "__main__":
    for path in write_inputs():
        print(
            f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}"
        )
