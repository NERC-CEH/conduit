"""Tests for modules an installed package registers by entry point.

A downstream package declares its own modules under the ``conduit.modules``
entry-point group, and a config may then name one as a bare section with no
``_import_path``. These tests build `importlib.metadata.EntryPoint` objects
directly rather than installing packages, so they exercise conduit's handling of
what the metadata says without a real install.
"""

from importlib.metadata import EntryPoint

import pytest

import conduit
from conduit.config import Config
from conduit.errors import ConduitValueError
from conduit.importing import (
    ENTRY_POINT_GROUP,
    discover_registered_modules,
    registered_module,
)


class _FakeDist:
    def __init__(self, name):
        self.name = name


def _entry_point(name, value, distribution):
    """An EntryPoint carrying the distribution that declared it."""
    entry = EntryPoint(name=name, value=value, group=ENTRY_POINT_GROUP)
    # `dist` is a read-only property backed by a private attribute.
    object.__setattr__(entry, "dist", _FakeDist(distribution))
    return entry


@pytest.fixture
def registry(monkeypatch):
    """Install a fake set of entry points, and keep the cache from leaking."""

    def _install(*entries):
        monkeypatch.setattr(
            "conduit.importing.entry_points", lambda group=None: list(entries)
        )
        discover_registered_modules.cache_clear()

    discover_registered_modules.cache_clear()
    yield _install
    discover_registered_modules.cache_clear()


class TestDiscovery:
    def test_registered_name_is_found(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        found = registered_module("transforms")
        assert found is not None
        assert found.import_path == "conduit.transforms"

    def test_records_the_distribution(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        found = registered_module("transforms")
        assert found is not None
        assert found.distribution == "science"

    def test_unregistered_name_is_none(self, registry):
        registry()
        assert registered_module("transforms") is None

    def test_nothing_is_imported_by_discovery(self, registry):
        """The entry point's value is read as a string, so a registry costs nothing."""
        registry(_entry_point("nope", "package.that.does.not.exist", "science"))
        assert registered_module("nope") is not None


class TestCollisions:
    def test_two_packages_claiming_one_name_is_an_error(self, registry):
        registry(
            _entry_point("transforms", "a.transforms", "science"),
            _entry_point("transforms", "b.transforms", "other"),
        )
        with pytest.raises(ConduitValueError, match="both register"):
            discover_registered_modules()

    def test_the_error_names_both_packages(self, registry):
        registry(
            _entry_point("transforms", "a.transforms", "science"),
            _entry_point("transforms", "b.transforms", "other"),
        )
        with pytest.raises(ConduitValueError, match="'science' and 'other'"):
            discover_registered_modules()

    def test_shadowing_a_conduit_builtin_is_an_error(self, registry):
        registry(_entry_point("node", "science.node", "science"))
        with pytest.raises(ConduitValueError, match="conduit itself defines"):
            discover_registered_modules()


class TestThroughTheConfig:
    def test_bare_section_resolves(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        parsed = Config({"transforms": {}}).parse()
        assert parsed.modules == ["conduit.transforms"]

    def test_parsed_config_records_the_source(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        [source] = Config({"transforms": {}}).parse().registered_modules
        assert (source.section, source.distribution) == ("transforms", "science")

    def test_section_params_still_become_config(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        parsed = Config({"transforms": {"floor": 2.0}}).parse()
        assert parsed.driver_config["floor"] == 2.0

    def test_explicit_import_path_wins(self, registry):
        """A config can never be silently redirected by something installed."""
        registry(_entry_point("transforms", "science.transforms", "science"))
        parsed = Config({"transforms": {"_import_path": "conduit.io"}}).parse()
        assert parsed.modules == ["conduit.io"]
        assert parsed.registered_modules == []

    def test_unknown_section_says_none_are_registered(self, registry):
        registry()
        with pytest.raises(ConduitValueError, match="none is installed here"):
            Config({"mystery": {}}).parse()

    def test_unknown_section_lists_the_registered_names(self, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        with pytest.raises(ConduitValueError, match="transforms \\(from science\\)"):
            Config({"mystery": {}}).parse()


class TestReporting:
    """A section whose code the config does not name must not be invisible."""

    @pytest.fixture
    def config_toml(self, tmp_path, synthetic_data_dir):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            f"""\
[transforms]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
        )
        return cfg

    def test_dry_run_reports_the_source(self, registry, config_toml):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        report = conduit.dry_run(config_toml)
        [config_stage] = [s for s in report.stages if s.name == "config"]
        assert "provided by science" in config_stage.detail

    def test_dry_run_does_not_report_it_as_a_warning(self, registry, config_toml):
        """`findings` render with a warning glyph; provenance is information."""
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        [config_stage] = [
            s for s in conduit.dry_run(config_toml).stages if s.name == "config"
        ]
        assert config_stage.findings == ()

    def test_run_logs_the_source(self, registry, config_toml, caplog):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        with caplog.at_level("INFO", logger="conduit.pipeline"):
            conduit.run(config_toml)
        assert any("provided by science" in r.getMessage() for r in caplog.records)

    def test_nothing_reported_without_a_registry(self, config_toml, registry):
        registry(_entry_point("transforms", "conduit.transforms", "science"))
        cfg = config_toml.read_text().replace(
            "[transforms]\n", '[transforms]\n_import_path = "conduit.transforms"\n'
        )
        config_toml.write_text(cfg)
        [config_stage] = [
            s for s in conduit.dry_run(config_toml).stages if s.name == "config"
        ]
        assert config_stage.detail == "config parsed"


class TestARealInstalledDistribution:
    """The same thing, driven by real packaging metadata rather than a fake.

    The tests above monkeypatch `entry_points`, so they check conduit's handling of
    what the metadata says without checking that real metadata is read correctly.
    This builds a ``.dist-info`` directory on ``sys.path`` and lets
    `importlib.metadata` discover it, which is the mechanism a downstream package
    actually uses.
    """

    @pytest.fixture
    def installed_science_package(self, tmp_path, monkeypatch):
        dist_info = tmp_path / "science_demo-0.1.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: science-demo\nVersion: 0.1\n"
        )
        (dist_info / "entry_points.txt").write_text(
            "[conduit.modules]\ndiagnostics = science_demo.diagnostics\n"
        )
        package = tmp_path / "science_demo"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "diagnostics.py").write_text(
            "import xarray as xr\n\n\n"
            "def bias_daily(temperature_daily: xr.DataArray) -> xr.DataArray:\n"
            "    return temperature_daily - temperature_daily.mean()\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        discover_registered_modules.cache_clear()
        yield tmp_path
        discover_registered_modules.cache_clear()

    def test_entry_point_is_discovered(self, installed_science_package):
        found = registered_module("diagnostics")
        assert found is not None
        assert found.import_path == "science_demo.diagnostics"

    def test_distribution_name_comes_from_the_metadata(self, installed_science_package):
        found = registered_module("diagnostics")
        assert found is not None
        assert found.distribution == "science-demo"

    def test_a_bare_section_builds_a_working_dag(
        self, installed_science_package, tmp_path, synthetic_data_dir
    ):
        """End to end: no `_import_path`, and the package's node is in the graph."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            f"""\
[diagnostics]

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[outputs.daily]
path = "{tmp_path / "out.nc"}"
vars = ["bias"]
"""
        )
        report = conduit.run(cfg)
        assert "bias" in report.outputs["daily"]
