"""Tests for the explicit/aliasable file<->node mapping (Phase C)."""

import numpy as np
import pytest
import xarray as xr

from conduit.config import IOSpec
from conduit.io import (
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
    var_mapping,
)


def _write_nc(path, **vars_):
    xr.Dataset(
        {k: (("x",), np.asarray(v, dtype=float)) for k, v in vars_.items()}
    ).to_netcdf(path)


class TestVarMapping:
    def test_list_form_uses_suffix(self):
        spec = IOSpec(path="p", vars=["temperature"])
        assert var_mapping("daily", spec) == {"temperature_daily": "temperature"}

    def test_empty_suffix_gives_bare_names(self):
        spec = IOSpec(path="p", vars=["elevation"], suffix="")
        assert var_mapping("static", spec) == {"elevation": "elevation"}

    def test_mapping_form_is_verbatim_and_suffix_free(self):
        spec = IOSpec(path="p", vars={"temperature_daily": "t2m"})
        assert var_mapping("daily", spec) == {"temperature_daily": "t2m"}


class TestAliasedInputs:
    def test_alias_reads_file_var_into_node_name(self, tmp_path):
        nc = tmp_path / "in.nc"
        _write_nc(nc, t2m=[1.0, 2.0, 3.0])
        specs = {"met": IOSpec(path=str(nc), vars={"temperature_daily": "t2m"})}
        inputs = load_inputs(specs)
        assert "temperature_daily" in inputs
        assert "t2m" not in inputs
        np.testing.assert_allclose(inputs["temperature_daily"].values, [1, 2, 3])

    def test_colliding_node_names_raise(self, tmp_path):
        nc = tmp_path / "in.nc"
        _write_nc(nc, temperature=[1.0], foo=[2.0])
        specs = {
            "a": IOSpec(path=str(nc), vars=["temperature"], suffix=""),
            "b": IOSpec(path=str(nc), vars={"temperature": "foo"}),
        }
        with pytest.raises(ValueError, match="collides"):
            load_inputs(specs)


class TestAliasedOutputs:
    def test_get_final_vars_uses_mapping_keys(self):
        specs = {"daily": IOSpec(path="o.nc", vars={"gpp_daily": "gpp"})}
        assert get_final_vars(specs) == ["gpp_daily"]

    def test_get_outputs_renames_node_to_file_var(self):
        specs = {"daily": IOSpec(path="o.nc", vars={"gpp_daily": "gpp"})}
        results = {"gpp_daily": xr.DataArray([1.0, 2.0], dims=("x",))}
        out = get_outputs(results, specs)
        assert "gpp" in out["daily"].data_vars

    def test_duplicate_output_node_names_raise(self):
        specs = {
            "a": IOSpec(path="a.nc", vars={"shared": "x"}),
            "b": IOSpec(path="b.nc", vars={"shared": "y"}),
        }
        with pytest.raises(ValueError, match="more than one output section"):
            get_final_vars(specs)


class TestProvenance:
    def test_provenance_attrs_stamped_on_output(self, tmp_path):
        out = tmp_path / "out.nc"
        ds = xr.Dataset({"v": (("x",), [1.0, 2.0])})
        specs = {"static": IOSpec(path=str(out), vars=["v"])}
        save_outputs(
            {"static": ds}, specs, provenance={"conduit_config_sha256": "abc123"}
        )
        reloaded = xr.open_dataset(out)
        assert reloaded.attrs["conduit_config_sha256"] == "abc123"
