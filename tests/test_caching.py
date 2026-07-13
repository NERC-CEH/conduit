"""Tests for Hamilton result caching (config, fingerprinting, cross-run hits)."""

import sys
import types
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from hamilton.caching import fingerprinting

import conduit.dag.caching  # noqa: F401  (registers the xarray fingerprint)
from conduit import CacheSpec
from conduit.cli.run import _resolve_cache
from conduit.config import Config, IOSpec, load_config
from conduit.dag.driver import build_driver
from conduit.io import get_final_vars


class TestCacheConfig:
    """Parsing of the [cache] section."""

    def test_parses_spec(self):
        parsed = Config.loads(
            '[cache]\npath = "mycache"\nrecompute = ["mean_temperature"]\n'
        ).parse()
        assert parsed.cache_spec == CacheSpec(
            path="mycache", recompute=["mean_temperature"]
        )

    def test_defaults_when_minimal(self):
        parsed = Config.loads("[cache]\n").parse()
        assert parsed.cache_spec == CacheSpec()

    def test_enabled_false_disables(self):
        parsed = Config.loads('[cache]\nenabled = false\npath = "x"\n').parse()
        assert parsed.cache_spec is None

    def test_absent_section(self):
        parsed = Config.loads("[grid]\n").parse()
        assert parsed.cache_spec is None

    def test_recompute_bool(self):
        parsed = Config.loads("[cache]\nrecompute = true\n").parse()
        assert parsed.cache_spec is not None
        assert parsed.cache_spec.recompute is True

    def test_invalid_recompute_raises(self):
        with pytest.raises(ValueError, match="must be a boolean or a list"):
            Config.loads("[cache]\nrecompute = 5\n").parse()

    def test_path_resolved_relative_to_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[cache]\npath = "relcache"\n')
        parsed = load_config(config_file)
        assert parsed.cache_spec is not None
        assert parsed.cache_spec.path == str(tmp_path / "relcache")

    def test_absolute_path_left_untouched(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[cache]\npath = "/abs/cache"\n')
        parsed = load_config(config_file)
        assert parsed.cache_spec is not None
        assert parsed.cache_spec.path == "/abs/cache"


class TestResolveCache:
    """CLI override logic combining config spec with --cache / --cache-dir."""

    def test_no_flags_uses_config(self):
        spec = CacheSpec(path="cfg")
        assert _resolve_cache(spec, None, None) is spec

    def test_no_cache_flag_disables(self):
        assert _resolve_cache(CacheSpec(), False, None) is None

    def test_cache_flag_enables_default(self):
        assert _resolve_cache(None, True, None) == CacheSpec()

    def test_cache_dir_overrides_path(self):
        out = _resolve_cache(CacheSpec(recompute=["a"]), None, Path("/tmp/x"))
        assert out == CacheSpec(path="/tmp/x", recompute=["a"])

    def test_cache_dir_enables_when_no_config(self):
        out = _resolve_cache(None, None, Path("/tmp/x"))
        assert out == CacheSpec(path="/tmp/x")

    def test_no_cache_wins_over_cache_dir(self):
        assert _resolve_cache(CacheSpec(), False, Path("/tmp/x")) is None


class TestDataArrayFingerprint:
    """The registered xarray.DataArray versioning function."""

    def _da(self, values):
        return xr.DataArray(
            np.asarray(values, dtype=float),
            dims="t",
            coords={"t": np.arange(len(values))},
            name="x",
        )

    def test_content_based_not_unhashable(self):
        v = fingerprinting.hash_value(self._da([1, 2, 3]))
        assert "<unhashable>" not in v

    def test_stable_for_identical_content(self):
        a = fingerprinting.hash_value(self._da([1, 2, 3]))
        b = fingerprinting.hash_value(self._da([1, 2, 3]))
        assert a == b

    def test_sensitive_to_values(self):
        a = fingerprinting.hash_value(self._da([1, 2, 3]))
        b = fingerprinting.hash_value(self._da([1, 2, 4]))
        assert a != b

    def test_sensitive_to_name(self):
        da = self._da([1, 2, 3])
        a = fingerprinting.hash_value(da)
        b = fingerprinting.hash_value(da.rename("y"))
        assert a != b

    def test_fingerprint_changes_when_units_attr_changes(self):
        # Same numbers, different meaning: must not serve a stale cached result.
        kg = self._da([1, 2, 3])
        kg.attrs["units"] = "kg"
        g = self._da([1, 2, 3])
        g.attrs["units"] = "g"
        assert fingerprinting.hash_value(kg) != fingerprinting.hash_value(g)

    def test_fingerprint_stable_for_identical_arrays(self):
        # Guards against hashing object identity rather than content.
        def build():
            da = self._da([1, 2, 3])
            da.attrs["units"] = "kg"
            da.attrs["long_name"] = "mass"
            return da

        assert fingerprinting.hash_value(build()) == fingerprinting.hash_value(build())


def _make_counting_module(counter: list) -> types.ModuleType:
    """Build a one-node Hamilton module that records each real computation."""
    mod = types.ModuleType("conduit_test_cache_mod")

    def expensive(source: xr.DataArray) -> xr.DataArray:
        counter.append(1)
        return (source * 2.0).rename("expensive")

    expensive.__module__ = mod.__name__
    setattr(mod, expensive.__name__, expensive)  # variable name avoids ruff B010
    sys.modules[mod.__name__] = mod
    return mod


class TestCrossRunCacheHit:
    """A node is computed once across separate drivers sharing a cache dir."""

    def test_second_run_hits_cache(self, tmp_path):
        counter: list = []
        mod = _make_counting_module(counter)
        try:
            da = xr.DataArray(np.arange(5, dtype=float), dims="t", name="source")
            spec = CacheSpec(path=str(tmp_path / "cache"))

            def run():
                dr = build_driver([mod.__name__], {}, cache=spec)
                return dr.execute(["expensive"], inputs={"source": da})  # type: ignore[reportArgumentType]

            r1 = run()
            r2 = run()

            np.testing.assert_array_equal(
                r1["expensive"].values, r2["expensive"].values
            )
            assert isinstance(r2["expensive"], xr.DataArray)
            assert sum(counter) == 1, "expensive node should compute exactly once"
        finally:
            sys.modules.pop(mod.__name__, None)

    def test_recompute_forces_recomputation(self, tmp_path):
        counter: list = []
        mod = _make_counting_module(counter)
        try:
            da = xr.DataArray(np.arange(5, dtype=float), dims="t", name="source")
            spec = CacheSpec(
                path=str(tmp_path / "cache"),
                recompute=["expensive"],
                disable=["source"],
            )

            def run():
                dr = build_driver([mod.__name__], {}, cache=spec)
                return dr.execute(["expensive"], inputs={"source": da})  # type: ignore[reportArgumentType]

            run()
            run()
            # recompute=[...] means the node is recomputed every run despite the cache
            assert sum(counter) == 2
        finally:
            sys.modules.pop(mod.__name__, None)


class TestPipelineWithCache:
    """The real synthetic pipeline runs identically with caching enabled."""

    def test_cached_run_matches_uncached(
        self, pipeline_config, pipeline_inputs, tmp_path
    ):
        # A genuinely computed node that is satisfiable from synthetic inputs
        # (resamples temperature_daily).
        final_vars = get_final_vars(
            {"weekly": IOSpec(path="", vars=["mean_temperature"])}
        )
        spec = CacheSpec(path=str(tmp_path / "cache"))

        def run(cache):
            dr = build_driver(
                pipeline_config.modules, pipeline_config.driver_config, cache=cache
            )
            return dr.execute(final_vars, inputs=pipeline_inputs)  # type: ignore[reportArgumentType]

        uncached = run(None)
        run(spec)  # cold cache
        cached = run(spec)  # warm cache

        for name in final_vars:
            np.testing.assert_allclose(cached[name].values, uncached[name].values)
        assert (tmp_path / "cache").exists()
