"""Import a user's node module, named by an ``_import_path`` in the config.

A section either carries an ``_import_path``, or is named after a module some
installed package has registered (see `discover_registered_modules`).

An ``_import_path`` takes one of two forms, told apart by whether it ends in
``.py``:

- **A dotted module name** — ``mypackage.indices`` — imported normally, so it must
  be installed in the environment (or otherwise on ``sys.path``). Use this for code
  that is packaged, and for any module that imports another module of your own.
- **A path to a ``.py`` file** — ``nodes.py``, ``lib/nodes.py``,
  ``/shared/models/nodes.py`` — loaded straight from that file. A relative path
  resolves against the directory holding the config, the same as every other path
  in it, so a config and its module travel together. An absolute path lets many
  configs in different directories share one module.

A file-form module is loaded on its own: it may import installed packages, but not
another loose ``.py`` file beside it. `import_user_module` raises with an
explanation pointing at packaging when one tries.
"""

import hashlib
import importlib.util
import sys
from functools import cache
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType

from .errors import ConduitFileNotFoundError, ConduitValueError
from .specs import RegisteredModule

#: Entry-point group a package declares to give its modules a bare section name.
#: An installed package announcing
#: ``[project.entry-points."conduit.modules"] diagnostics = "science.diagnostics"``
#: makes ``[diagnostics]`` a valid config section with no ``_import_path``.
ENTRY_POINT_GROUP = "conduit.modules"

#: Module names conduit itself claims, which no package may register. ``node`` is
#: generated from the config's ``[[node]]`` entries rather than imported, and is
#: handled directly in `conduit.build.build_driver`.
BUILTIN_MODULES: dict[str, str] = {
    "node": "conduit.nodegen",
}

#: Prefix for the ``sys.modules`` name a file-form module is registered under.
#: Hamilton resolves a node's originating function through ``sys.modules``, so the
#: module has to be registered; keying the name on the file's resolved path keeps
#: two same-named files in different directories apart.
_LOCAL_PREFIX = "_conduit_local"


def is_file_form(import_path: str) -> bool:
    """Return True if ``import_path`` names a ``.py`` file rather than a module."""
    return import_path.endswith(".py")


def is_valid_module_path(path: str) -> bool:
    """Return True if path is a non-empty dotted Python identifier."""
    return bool(path) and all(part.isidentifier() for part in path.split("."))


def resolve_file_form(import_path: str, base: Path | None) -> Path:
    """Resolve a file-form ``_import_path`` against the config's directory."""
    path = Path(import_path)
    if path.is_absolute():
        return path
    if base is None:
        raise ConduitValueError(
            f"'_import_path = {import_path!r}' is a relative path, but this config "
            f"has no file to resolve it against. Give an absolute path, use a "
            f"dotted module name for an installed package, or load the config from "
            f"a file with Config.load()."
        )
    return base / path


def _module_name(path: Path) -> str:
    """Return a ``sys.modules`` name unique to this file, readable in a traceback."""
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:8]
    return f"{_LOCAL_PREFIX}_{path.parent.name}_{digest}.{path.stem}"


def _load_from_file(path: Path, import_path: str) -> ModuleType:
    """Load a module from a ``.py`` file, without touching ``sys.path``."""
    resolved = path.resolve()
    if not resolved.is_file():
        raise ConduitFileNotFoundError(
            f"'_import_path = {import_path!r}' names no file. Looked for {resolved}."
        )

    name = _module_name(resolved)
    if (cached := sys.modules.get(name)) is not None:
        return cached

    spec = importlib.util.spec_from_file_location(name, resolved)
    if spec is None or spec.loader is None:
        raise ConduitValueError(f"Could not load a Python module from {resolved}.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        del sys.modules[name]
        raise ConduitValueError(
            f"{resolved} imports {exc.name!r}, which is not installed. A module "
            f"named by a file path is loaded on its own, so it can import "
            f"installed packages but not another loose .py file beside it. Either "
            f"install {exc.name!r}, or make your own code an installed package and "
            f"name it with a dotted '_import_path'."
        ) from exc
    except Exception:
        del sys.modules[name]
        raise
    return module


def import_user_module(import_path: str, base: Path | None = None) -> ModuleType:
    """Import the module named by an ``_import_path``.

    Parameters
    ----------
    import_path
        A dotted module name, or a path to a ``.py`` file.
    base
        The directory a relative file path resolves against, normally the one
        holding the config.
    """
    if is_file_form(import_path):
        return _load_from_file(resolve_file_form(import_path, base), import_path)

    from importlib import import_module

    try:
        return import_module(import_path)
    except ModuleNotFoundError as exc:
        raise ConduitValueError(
            f"Could not import {import_path!r}, named by an '_import_path' in the "
            f"config. A dotted name must be importable from this environment, so "
            f"the package has to be installed. To point at a .py file instead, "
            f"give its path: '_import_path = \"nodes.py\"', relative to the config."
        ) from exc


@cache
def discover_registered_modules() -> dict[str, RegisteredModule]:
    """Return the modules installed packages have registered, keyed by section name.

    A package makes its modules addressable by a bare section name by declaring
    them in its own ``pyproject.toml``::

        [project.entry-points."conduit.modules"]
        transforms = "science.transforms"
        diagnostics = "science.diagnostics"

    A config may then write ``[transforms]`` with no ``_import_path``. Nothing is
    imported here: the entry point's value is read as a string, so a registered
    module costs nothing until a config names it.

    The result is cached for the life of the process. Call ``cache_clear()`` after
    installing a package into the running interpreter.
    """
    found: dict[str, RegisteredModule] = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        distribution = entry.dist.name if entry.dist is not None else "<unknown>"
        if entry.name in BUILTIN_MODULES:
            raise ConduitValueError(
                f"Package {distribution!r} registers a conduit module named "
                f"{entry.name!r}, which conduit itself defines. The package must "
                f"choose another name."
            )
        if (clash := found.get(entry.name)) is not None:
            raise ConduitValueError(
                f"Packages {clash.distribution!r} and {distribution!r} both "
                f"register a conduit module named {entry.name!r} "
                f"({clash.import_path} and {entry.value}). Uninstall one, or name "
                f"the module you want with an explicit '_import_path'."
            )
        found[entry.name] = RegisteredModule(
            section=entry.name, import_path=entry.value, distribution=distribution
        )
    return found


def registered_module(section: str) -> RegisteredModule | None:
    """Return the module registered under ``section``, if any package registers one."""
    return discover_registered_modules().get(section)
