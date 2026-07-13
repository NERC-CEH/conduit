"""Tests for the before-compute wiring check (`conduit.dag.wiring_check`)."""

import sys
import types

import pytest
import xarray as xr
from hamilton import driver
from hamilton.settings import ENABLE_POWER_USER_MODE

from conduit.dag.wiring_check import WiringWarning, check_wiring


def _da():
    return xr.DataArray([1.0])


@pytest.fixture
def register():
    """Build Hamilton-scannable modules from functions and clean up afterwards."""
    names: list[str] = []

    def _make(name: str, *funcs) -> types.ModuleType:
        mod = types.ModuleType(name)
        for fn in funcs:
            fn.__module__ = name
            setattr(mod, fn.__name__, fn)
        sys.modules[name] = mod
        names.append(name)
        return mod

    yield _make

    for name in names:
        sys.modules.pop(name, None)


def _build(*mods) -> driver.Driver:
    return (
        driver.Builder()
        .with_modules(*mods)
        .with_config({ENABLE_POWER_USER_MODE: True})
        .build()
    )


def _consumer_module(register):
    """A node ``out`` requiring external input ``x``."""

    def out(x: xr.DataArray) -> xr.DataArray:
        return x

    return _build(register("wire_mod", out))


class TestUnbound:
    def test_missing_required_input_raises(self, register):
        dr = _consumer_module(register)
        with pytest.raises(ValueError, match="unbound pipeline input"):
            check_wiring(dr, ["out"], {})

    def test_present_input_passes(self, register):
        dr = _consumer_module(register)
        check_wiring(dr, ["out"], {"x": _da()})

    def test_optional_input_not_flagged(self, register):
        """An external input with a default value is optional, not unbound."""

        def out(x: xr.DataArray, y: xr.DataArray = None) -> xr.DataArray:  # type: ignore[assignment]
            return x if y is None else x + y

        dr = _build(register("wire_opt", out))
        # y is not loaded, but it has a default, so this must not raise.
        check_wiring(dr, ["out"], {"x": _da()})


class TestUnused:
    def test_unused_input_warns(self, register):
        dr = _consumer_module(register)
        with pytest.warns(WiringWarning, match="consumed by no node"):
            check_wiring(dr, ["out"], {"x": _da(), "stray": _da()})

    def test_exempt_suppresses_warning(self, register):
        import warnings

        dr = _consumer_module(register)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            check_wiring(
                dr, ["out"], {"x": _da(), "latitude": _da()}, exempt={"latitude"}
            )

    def test_clean_wiring_is_silent(self, register):
        import warnings

        dr = _consumer_module(register)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            check_wiring(dr, ["out"], {"x": _da()})
