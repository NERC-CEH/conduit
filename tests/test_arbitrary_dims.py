"""Phase 2: non-temporal, non-geospatial pipelines with arbitrary dims/labels.

These exercise the generalised I/O layer: input section labels need not be known
frequencies, variables may carry arbitrary dimensions (no ``time``, no ``pixel``,
no CRS), the frequency-suffix naming is opt-out, and the geospatial stack
(rioxarray/pyproj) is never touched when no CRS is present.
"""

import subprocess
import sys

import numpy as np
import xarray as xr

from conduit.config import IOSpec, load_config
from conduit.dag.driver import build_driver
from conduit.io import effective_suffix, get_final_vars, get_outputs, load_inputs


def _write_scene(path) -> None:
    """A (location, band) reflectance cube — no time, no pixel, no CRS."""
    ds = xr.Dataset(
        {"reflectance": (("location", "band"), np.linspace(0, 1, 12).reshape(4, 3))},
        coords={"location": np.arange(4), "band": ["red", "nir", "swir"]},
    )
    ds.to_netcdf(path, engine="netcdf4")


def test_effective_suffix_rules():
    assert effective_suffix("daily", IOSpec(path="", vars=[])) == "_daily"
    assert effective_suffix("static", IOSpec(path="", vars=[])) == ""
    assert effective_suffix("scene", IOSpec(path="", vars=[])) == "_scene"
    # explicit override wins, including bare names on any label
    assert effective_suffix("daily", IOSpec(path="", vars=[], suffix="")) == ""
    assert effective_suffix("x", IOSpec(path="", vars=[], suffix="_y")) == "_y"


class TestArbitraryDimLoading:
    def test_arbitrary_label_and_dims(self, tmp_path):
        _write_scene(tmp_path / "scene.nc")
        specs = {"scene": IOSpec(path=str(tmp_path / "scene.nc"), vars=["reflectance"])}
        inputs = load_inputs(specs)
        # arbitrary label -> suffix; arbitrary dims preserved; no time/pixel/grid
        da = inputs["reflectance_scene"]
        assert da.dims == ("location", "band")
        assert "dates_scene" not in inputs
        assert "latitude" not in inputs
        assert "longitude" not in inputs

    def test_bare_suffix_for_non_static_label(self, tmp_path):
        ds = xr.Dataset({"threshold": ((), 0.5)})
        ds.to_netcdf(tmp_path / "params.nc", engine="netcdf4")
        specs = {
            "params": IOSpec(
                path=str(tmp_path / "params.nc"), vars=["threshold"], suffix=""
            )
        }
        inputs = load_inputs(specs)
        assert "threshold" in inputs  # bare, not "threshold_params"


class TestNonTemporalPipeline:
    def test_end_to_end(self, tmp_path):
        _write_scene(tmp_path / "scene.nc")
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[[node]]\n"
            'name = "mean_reflectance_scene"\n'
            'inputs = ["reflectance_scene"]\n'
            "expression = \"reflectance_scene.mean('band')\"\n\n"
            "[inputs.scene]\n"
            f'path = "{tmp_path / "scene.nc"}"\n'
            'vars = ["reflectance"]\n\n'
            "[outputs.scene]\n"
            f'path = "{tmp_path / "out.nc"}"\n'
            'vars = ["mean_reflectance"]\n'
        )
        parsed = load_config(cfg)
        inputs = load_inputs(parsed.input_specs)
        dr = build_driver(parsed.modules, parsed.driver_config)
        final_vars = get_final_vars(parsed.output_specs)
        assert final_vars == ["mean_reflectance_scene"]
        results = dr.execute(final_vars, inputs=inputs)  # type: ignore[reportArgumentType]
        out = get_outputs(results, parsed.output_specs)["scene"]
        assert out["mean_reflectance"].dims == ("location",)
        assert out.sizes["location"] == 4


class TestBlockingArbitraryDim:
    def test_blocked_matches_unblocked_over_location(self, tmp_path):
        from conduit.config import BlockingSpec
        from conduit.dag.blocking import execute_blocked

        _write_scene(tmp_path / "scene.nc")
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[[node]]\n"
            'name = "scaled_scene"\n'
            'inputs = ["reflectance_scene"]\n'
            'expression = "reflectance_scene * 2.0"\n\n'
            "[inputs.scene]\n"
            f'path = "{tmp_path / "scene.nc"}"\n'
            'vars = ["reflectance"]\n'
        )
        parsed = load_config(cfg)
        inputs = load_inputs(parsed.input_specs)
        dr = build_driver(parsed.modules, parsed.driver_config)
        final = ["scaled_scene"]

        ref = dr.execute(final, inputs=inputs)  # type: ignore[reportArgumentType]
        spec = BlockingSpec(block_size=2, dim="location")
        blocked = execute_blocked(dr, inputs, final, spec)
        xr.testing.assert_identical(blocked["scaled_scene"], ref["scaled_scene"])


def test_no_geospatial_deps_imported_without_crs(tmp_path):
    """Loading non-CRS inputs must not import rioxarray/pyproj (optional 'geo')."""
    _write_scene(tmp_path / "scene.nc")
    path = str(tmp_path / "scene.nc")
    script = f"""\
import sys
from conduit.config import IOSpec
from conduit.io import load_inputs
load_inputs({{"scene": IOSpec(path={path!r}, vars=["reflectance"])}})
assert "rioxarray" not in sys.modules, "rioxarray was imported"
assert "pyproj" not in sys.modules, "pyproj was imported"
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
