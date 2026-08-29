"""Tests for resolving an ``_import_path`` to a module.

Two forms, told apart by the ``.py`` suffix: a dotted name imported from the
environment, or a file loaded from a path that is relative to the config. The file
form deliberately does not support importing another loose ``.py`` file, so the
error a user gets when they try is part of the contract.
"""

import os
import sys

import pytest

from conduit.config import Config
from conduit.errors import ConduitFileNotFoundError, ConduitValueError
from conduit.importing import _module_name, import_user_module, is_file_form


def _write_nodes(directory, marker):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "nodes.py").write_text(f"MARKER = {marker!r}\n")
    return directory / "nodes.py"


class TestForm:
    @pytest.mark.parametrize(
        "spec", ["nodes.py", "lib/nodes.py", "../shared/nodes.py", "/abs/nodes.py"]
    )
    def test_py_suffix_is_the_file_form(self, spec):
        assert is_file_form(spec)

    @pytest.mark.parametrize("spec", ["mypackage.nodes", "nodes", "a.b.c"])
    def test_dotted_names_are_not(self, spec):
        assert not is_file_form(spec)


class TestFileForm:
    def test_relative_path_resolves_against_the_base(self, tmp_path):
        _write_nodes(tmp_path / "pipeline", "here")
        module = import_user_module("nodes.py", base=tmp_path / "pipeline")
        assert module.MARKER == "here"

    def test_absolute_path_needs_no_base(self, tmp_path):
        path = _write_nodes(tmp_path / "shared", "shared")
        assert import_user_module(str(path)).MARKER == "shared"

    def test_relative_path_without_a_base_is_an_error(self):
        with pytest.raises(ConduitValueError, match="no file to resolve it against"):
            import_user_module("nodes.py")

    def test_missing_file_names_where_it_looked(self, tmp_path):
        with pytest.raises(ConduitFileNotFoundError, match=str(tmp_path)):
            import_user_module("nodes.py", base=tmp_path)

    def test_same_file_twice_is_one_module(self, tmp_path):
        _write_nodes(tmp_path, "once")
        first = import_user_module("nodes.py", base=tmp_path)
        assert import_user_module("nodes.py", base=tmp_path) is first


class TestNoCollisionBetweenDirectories:
    """Two configs, each with its own ``nodes.py``, in one process.

    Appending each directory to ``sys.path`` and importing ``nodes`` would hand the
    second config the first one's module, silently. Loading by file location under
    a path-derived name is what prevents that.
    """

    def test_each_directory_gets_its_own_module(self, tmp_path):
        _write_nodes(tmp_path / "a", "a")
        _write_nodes(tmp_path / "b", "b")
        first = import_user_module("nodes.py", base=tmp_path / "a")
        second = import_user_module("nodes.py", base=tmp_path / "b")
        assert (first.MARKER, second.MARKER) == ("a", "b")

    def test_module_names_are_distinct(self, tmp_path):
        _write_nodes(tmp_path / "a", "a")
        _write_nodes(tmp_path / "b", "b")
        first = import_user_module("nodes.py", base=tmp_path / "a")
        second = import_user_module("nodes.py", base=tmp_path / "b")
        assert first.__name__ != second.__name__

    def test_sys_path_is_untouched(self, tmp_path):
        _write_nodes(tmp_path, "x")
        before = list(sys.path)
        import_user_module("nodes.py", base=tmp_path)
        assert sys.path == before


class TestSiblingImportsAreUnsupported:
    """A loose ``.py`` file may import installed packages, and nothing else.

    Supporting it would mean putting the config's directory on ``sys.path``, which
    is what makes two same-named siblings collide. The error has to send the user
    to packaging instead of failing as a bare ModuleNotFoundError.
    """

    @pytest.fixture
    def pipeline_with_sibling(self, tmp_path):
        (tmp_path / "helpers.py").write_text("VALUE = 1\n")
        (tmp_path / "nodes.py").write_text("import helpers\n")
        return tmp_path

    def test_raises_a_conduit_error(self, pipeline_with_sibling):
        with pytest.raises(ConduitValueError):
            import_user_module("nodes.py", base=pipeline_with_sibling)

    def test_error_names_the_missing_module(self, pipeline_with_sibling):
        with pytest.raises(ConduitValueError, match="'helpers'"):
            import_user_module("nodes.py", base=pipeline_with_sibling)

    def test_error_points_at_packaging(self, pipeline_with_sibling):
        with pytest.raises(ConduitValueError, match="installed package"):
            import_user_module("nodes.py", base=pipeline_with_sibling)

    def test_failed_module_is_not_left_in_sys_modules(self, pipeline_with_sibling):
        """A half-executed module must not be handed to the next caller."""
        name = _module_name((pipeline_with_sibling / "nodes.py").resolve())
        with pytest.raises(ConduitValueError):
            import_user_module("nodes.py", base=pipeline_with_sibling)
        assert name not in sys.modules

    def test_installed_packages_still_import(self, tmp_path):
        (tmp_path / "nodes.py").write_text("import xarray\nMARKER = xarray.__name__\n")
        assert import_user_module("nodes.py", base=tmp_path).MARKER == "xarray"


class TestDottedForm:
    def test_importable_module_loads(self):
        assert import_user_module("conduit.transforms").resample is not None

    def test_missing_module_suggests_the_file_form(self):
        with pytest.raises(ConduitValueError, match="give its path"):
            import_user_module("no_such_package_anywhere")


class TestThroughTheConfig:
    """The path a real pipeline takes: config file on disk, module beside it."""

    def test_parsed_config_carries_its_base(self, tmp_path):
        (tmp_path / "config.toml").write_text('[local]\n_import_path = "nodes.py"\n')
        parsed = Config.load(tmp_path / "config.toml").parse()
        assert parsed.base == tmp_path

    def test_config_from_a_dict_has_no_base(self):
        assert Config({"local": {"_import_path": "pkg.mod"}}).parse().base is None

    def test_loads_accepts_an_explicit_base(self, tmp_path):
        parsed = Config.loads('[local]\n_import_path = "nodes.py"\n', base=tmp_path)
        assert parsed.parse().base == tmp_path


class TestAChangedFileIsReloaded:
    """A file-form module must not be pinned to the code it had when first loaded.

    Editing ``nodes.py`` and re-running is the documented notebook workflow, and
    the ``sys.modules`` key is a hash of the path, so a user cannot evict a stale
    module by hand even knowing it is there.
    """

    @pytest.fixture
    def module_file(self, tmp_path):
        path = tmp_path / "nodes.py"
        path.write_text("VALUE = 1\n")
        return path

    @staticmethod
    def _edit(path, text):
        """Rewrite the file as a human would: with the clock having moved on.

        Two writes in one test can share an mtime, and CPython's own __pycache__
        is keyed on mtime and size, so without this the stale *bytecode* is
        executed no matter what conduit decides.
        """
        path.write_text(text)
        stamp = path.stat().st_mtime_ns + 1_000_000_000
        os.utime(path, ns=(stamp, stamp))

    def test_an_edit_takes_effect(self, module_file):
        assert import_user_module(str(module_file)).VALUE == 1
        self._edit(module_file, "VALUE = 2\n")
        assert import_user_module(str(module_file)).VALUE == 2

    def test_an_untouched_file_is_not_reloaded(self, module_file):
        first = import_user_module(str(module_file))
        assert import_user_module(str(module_file)) is first

    def test_a_same_size_edit_takes_effect(self, module_file):
        assert import_user_module(str(module_file)).VALUE == 1
        self._edit(module_file, "VALUE = 9\n")
        assert import_user_module(str(module_file)).VALUE == 9

    def test_a_new_function_becomes_available(self, module_file):
        """The notebook case: add a node function, re-run the cell."""
        import_user_module(str(module_file))
        self._edit(module_file, "VALUE = 1\n\n\ndef added():\n    return 42\n")
        assert import_user_module(str(module_file)).added() == 42
