"""Regression tests for the executable flux-pipeline documentation example."""

import subprocess
import sys
from pathlib import Path

import xarray as xr

EXAMPLE = Path(__file__).parents[1] / "examples" / "flux_pipeline"


def test_flux_marimo_notebook_executes(tmp_path: Path) -> None:
    """Exporting the notebook executes every cell and produces valid products."""
    output_html = tmp_path / "flux-pipeline.html"
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "marimo",
                "export",
                "html",
                str(EXAMPLE / "demo.py"),
                "--output",
                str(output_html),
            ],
            cwd=EXAMPLE.parents[1],
            check=True,
            capture_output=True,
            text=True,
        )

        assert output_html.exists()
        products = xr.open_dataset(EXAMPLE / "results" / "flux_products.nc")
        try:
            expected = {
                "annual_nee",
                "annual_gpp",
                "annual_reco",
                "gpp_weekly",
                "bias",
                "rmse",
            }
            assert expected <= set(products)
            assert products.gpp_weekly.sizes["time"] == 53
        finally:
            products.close()
    finally:
        for path in (
            EXAMPLE / "pipeline.dot",
            EXAMPLE / "pipeline.png",
            EXAMPLE / "data" / "flux.nc",
            EXAMPLE / "data" / "satellite.nc",
            EXAMPLE / "results" / "flux_products.nc",
        ):
            path.unlink(missing_ok=True)
