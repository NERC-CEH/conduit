"""Boundaries the package layout is meant to enforce, as tests rather than directories.

`conduit` keeps every module at the top level except the two subpackages behind
install extras, so a directory can no longer mark where an optional or heavyweight
dependency is allowed to appear. These tests do that instead, and unlike a directory
they fail in CI when someone crosses the line.
"""

import importlib.util
import pathlib
import pkgutil
import subprocess
import sys

import pytest

import conduit

#: Modules permitted to import the Hamilton API. Everything here either builds a
#: ``Driver``, generates modules to feed one, configures one, executes one, or reads
#: the graph one holds. A new name belongs on this list only for the same reason.
HAMILTON_IMPORTERS = frozenset(
    {
        "conduit.build",
        "conduit.nodegen",
        "conduit.caching",
        "conduit.blocking",
        "conduit.contract_check",
        "conduit.wiring_check",
        "conduit.graph",
    }
)


def _module_sources() -> dict[str, str]:
    """Every module in the installed package, mapped to its source text."""
    root = conduit.__file__
    assert root is not None
    sources = {"conduit": pathlib.Path(root).read_text()}
    for mod in pkgutil.walk_packages(conduit.__path__, "conduit."):
        spec = importlib.util.find_spec(mod.name)
        assert spec is not None
        assert spec.origin is not None
        sources[mod.name] = pathlib.Path(spec.origin).read_text()
    return sources


class TestSubpackagesAreOptionalExtras:
    """A subpackage exists only when its contents are behind an install extra."""

    def test_only_cli_and_gridded_are_subpackages(self):
        packages = {
            mod.name
            for mod in pkgutil.walk_packages(conduit.__path__, "conduit.")
            if mod.ispkg
        }
        assert packages == {"conduit.cli", "conduit.gridded"}


class TestHamiltonIsConfinedToTheDagModules:
    """Hamilton is an implementation detail of a named handful of modules.

    Nothing stops `config.py` or `io.py` reaching for a ``Driver``, and once one
    does, "where does Hamilton live?" has no answer again.
    """

    def test_no_other_module_imports_hamilton(self):
        offenders = [
            name
            for name, text in _module_sources().items()
            if name not in HAMILTON_IMPORTERS and "hamilton" in text
        ]
        assert not offenders, offenders

    @pytest.mark.parametrize("name", sorted(HAMILTON_IMPORTERS))
    def test_every_listed_module_actually_imports_hamilton(self, name):
        """A stale entry would license an import nobody meant to allow."""
        assert "hamilton" in _module_sources()[name]


class TestTyperIsConfinedToTheCli:
    """No conduit module outside ``conduit.cli`` may import typer.

    typer ships in the optional ``cli`` extra, so a library import that reached
    for it would break every install that did not ask for the CLI — and would
    quietly re-establish the CLI as the place logic lives.
    """

    def test_no_library_module_imports_typer(self):
        offenders = [
            name
            for name, text in _module_sources().items()
            if not (name.startswith("conduit.cli") or name.endswith(".cli"))
            and "import typer" in text
        ]
        assert not offenders, offenders

    def test_import_conduit_needs_no_typer(self):
        code = (
            "import sys; sys.modules['typer'] = None; "
            "import conduit; "
            "assert conduit.run and conduit.dry_run and conduit.build_graph"
        )
        assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
