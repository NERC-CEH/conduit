"""Boundaries the package layout is meant to enforce, as tests rather than directories.

`catena` keeps every module at the top level except the two subpackages behind
install extras, so a directory can no longer mark where an optional or heavyweight
dependency is allowed to appear. These tests do that instead, and unlike a directory
they fail in CI when someone crosses the line.
"""

import ast
import importlib.util
import pathlib
import pkgutil
import subprocess
import sys

import pytest

import catena

#: Modules permitted to import the Hamilton API. Everything here either builds a
#: ``Driver``, generates modules to feed one, configures one, executes one, or reads
#: the graph one holds. A new name belongs on this list only for the same reason.
HAMILTON_IMPORTERS = frozenset(
    {
        "catena.build",
        "catena.nodegen",
        "catena.caching",
        "catena.blocking",
        "catena.contract_check",
        "catena.wiring_check",
        "catena.graph",
    }
)


def _module_sources() -> dict[str, str]:
    """Every module in the installed package, mapped to its source text."""
    root = catena.__file__
    assert root is not None
    sources = {"catena": pathlib.Path(root).read_text()}
    for mod in pkgutil.walk_packages(catena.__path__, "catena."):
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
            for mod in pkgutil.walk_packages(catena.__path__, "catena.")
            if mod.ispkg
        }
        assert packages == {"catena.cli", "catena.gridded"}


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
    """No catena module outside ``catena.cli`` may import typer.

    typer ships in the optional ``cli`` extra, so a library import that reached
    for it would break every install that did not ask for the CLI — and would
    quietly re-establish the CLI as the place logic lives.
    """

    def test_no_library_module_imports_typer(self):
        offenders = [
            name
            for name, text in _module_sources().items()
            if not (name.startswith("catena.cli") or name.endswith(".cli"))
            and "import typer" in text
        ]
        assert not offenders, offenders

    def test_import_catena_needs_no_typer(self):
        code = (
            "import sys; sys.modules['typer'] = None; "
            "import catena; "
            "assert catena.run and catena.dry_run and catena.build_graph"
        )
        assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def _catena_imports(text: str) -> set[str]:
    """The catena modules a source file imports, absolute or relative."""
    tree = ast.parse(text)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                found.add(f"catena.{node.module}" if node.module else "catena")
            elif node.module and node.module.split(".")[0] == "catena":
                found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.split(".")[0] == "catena")
    return found


class TestSpecsIsALeaf:
    """`specs` imports only `errors`, and `errors` imports nothing at all.

    Every other module depends on `specs`, so one import out of it can close a
    cycle through `config`, `input_checks` and `io`.
    """

    def test_specs_imports_only_errors(self):
        assert _catena_imports(_module_sources()["catena.specs"]) <= {"catena.errors"}

    def test_errors_imports_nothing(self):
        tree = ast.parse(_module_sources()["catena.errors"])
        imports = [
            n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
        ]
        assert not imports


class TestOptionalExtrasStayUnimported:
    """`import catena` must not pull in a package from an optional extra.

    `build_graph` is re-exported from the package root, so `catena.graph` is
    imported on every `import catena`. Its graphviz import is therefore confined
    to a ``TYPE_CHECKING`` block, and this is what keeps it there.
    """

    @pytest.mark.parametrize("package", ["graphviz", "rioxarray", "pyproj"])
    def test_importing_catena_does_not_load(self, package):
        code = (
            "import sys, catena; "
            f"loaded = [m for m in sys.modules if m.split('.')[0] == {package!r}]; "
            "assert not loaded, loaded"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
