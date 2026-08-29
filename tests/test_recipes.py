"""Regression tests for the executable documentation recipes.

Exporting a recipe's marimo notebook runs every cell, which runs the pipeline,
so these tests fail if a recipe drifts away from the library.
"""

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import xarray as xr

import conduit

RECIPES = Path(__file__).parents[1] / "recipes"


@contextmanager
def executed_recipe(name: str, tmp_path: Path) -> Iterator[Path]:
    """Run a recipe's notebook, yielding its directory, then clean up after it."""
    recipe = RECIPES / name
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "marimo",
                "export",
                "html",
                str(recipe / "demo.py"),
                "--output",
                str(tmp_path / f"{name}.html"),
            ],
            cwd=RECIPES.parent,
            check=True,
            capture_output=True,
            text=True,
        )
        assert (tmp_path / f"{name}.html").exists()
        yield recipe
    finally:
        for path in (
            *(recipe / "data").glob("*"),
            *(recipe / "results").glob("*"),
        ):
            path.unlink(missing_ok=True)


def test_pipeline_101_notebook_executes(tmp_path: Path) -> None:
    """The 101 recipe writes both declared outputs, carrying their declared units."""
    with (
        executed_recipe("pipeline_101", tmp_path) as recipe,
        xr.open_dataset(recipe / "results" / "anomaly.nc") as result,
    ):
        assert {"temperature_anomaly", "anomaly_range"} <= set(result)
        assert result.temperature_anomaly.attrs["units"] == "degC"
        assert result.anomaly_range.attrs["units"] == "degC"
        assert "conduit_config_sha256" in result.attrs


def test_flux_notebook_executes(tmp_path: Path) -> None:
    """Exporting the notebook executes every cell and produces valid products."""
    with (
        executed_recipe("flux_pipeline", tmp_path) as recipe,
        xr.open_dataset(recipe / "results" / "flux_products.nc") as products,
    ):
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


def _write_inputs(recipe: Path) -> None:
    """Call the recipe's own ``make_data.write_inputs``, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        f"{recipe.name}_make_data", recipe / "make_data.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.write_inputs(recipe / "data")


@pytest.mark.parametrize("name", ["pipeline_101", "flux_pipeline"])
def test_recipe_config_dry_runs(name: str) -> None:
    """Every recipe's config passes a dry run against freshly generated inputs."""
    recipe = RECIPES / name
    try:
        (recipe / "results").mkdir(exist_ok=True)
        _write_inputs(recipe)
        report = conduit.dry_run(recipe / "config.toml")
        assert [stage for stage in report.stages if stage.status == "failed"] == []
    finally:
        for path in (recipe / "data").glob("*"):
            path.unlink(missing_ok=True)
