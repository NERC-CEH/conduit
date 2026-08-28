"""Tests for the conduit CLI: argument handling, exit codes, and what it prints.

The CLI is a shim over `conduit.pipeline` and `conduit.graph`, so the pipeline
behaviour itself is tested in ``test_pipeline.py`` and ``test_graph.py``. What is
left here is the part only the command can get wrong.
"""

import shutil
import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from conduit._version import __version__
from conduit.cli import main
from conduit.cli.app import _prepare_import_path, app
from conduit.errors import (
    ConduitError,
    ConduitFileNotFoundError,
    ConduitPermissionError,
    ConduitValueError,
)
from conduit.input_checks import InputCheckError

runner = CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersionFlag:
    @pytest.mark.parametrize("flag", ["--version", "-v"])
    def test_exits_zero(self, flag):
        result = runner.invoke(app, [flag])
        assert result.exit_code == 0

    @pytest.mark.parametrize("flag", ["--version", "-v"])
    def test_shows_version_string(self, flag):
        result = runner.invoke(app, [flag])
        assert __version__ in result.output


class TestGriddedGeoExtraGuard:
    """`conduit gridded` fails fast with an install hint when `geo` is absent."""

    def test_missing_extra_exits_with_hint(self, monkeypatch):
        import importlib.util as importutil

        real = importutil.find_spec

        def fake_find_spec(name, *args, **kwargs):
            if name in ("rioxarray", "pyproj"):
                return None
            return real(name, *args, **kwargs)

        monkeypatch.setattr(importutil, "find_spec", fake_find_spec)

        result = runner.invoke(app, ["gridded", "merge", "tests/test_config.toml"])
        assert result.exit_code == 1
        assert "conduit[geo]" in result.output
        assert "rioxarray" in result.output


class TestMissingTyperExtra:
    """Without the extra, `conduit` must explain itself, not traceback.

    The import boundary itself is checked in ``test_layout.py``.
    """

    def test_entry_point_hints_at_the_extra(self, monkeypatch, capsys):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "typer" or name.startswith("typer."):
                raise ModuleNotFoundError("No module named 'typer'", name="typer")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "conduit.cli.app", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
        assert "conduit[cli]" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_exits_zero(self, config_toml):
        result = runner.invoke(app, ["run", str(config_toml)])
        assert result.exit_code == 0, result.output

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["run", str(tmp_path / "nonexistent.toml")])
        assert result.exit_code != 0

    def test_run_without_outputs_prints_notice(self, tmp_path, synthetic_data_dir):
        # Previously exited 0 with no output and no message, which looked like a
        # successful run that had produced files somewhere.
        cfg = tmp_path / "no_outputs.toml"
        cfg.write_text(
            f"""\
[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]
"""
        )
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == 0, result.output
        assert "nothing to execute" in result.output

    @pytest.fixture
    def writing_config(self, tmp_path, synthetic_data_dir):
        """A config that actually writes a file, so the run has something to report."""
        cfg = tmp_path / "writes.toml"
        cfg.write_text(
            f"""\
[[node]]
name = "warmth_daily"
inputs = ["temperature_daily"]
expression = "temperature_daily * 2"

[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[outputs.daily]
path = "{tmp_path / "out.nc"}"
vars = ["warmth"]
"""
        )
        return cfg

    def test_reports_what_it_wrote(self, writing_config):
        """A run that writes files says so: silence looked the same as doing nothing."""
        result = runner.invoke(app, ["run", str(writing_config)])
        assert result.exit_code == 0, result.output
        assert "inputs loaded:" in result.output
        assert "wrote" in result.output
        assert "1 variable(s)" in result.output
        assert "Run completed in" in result.output

    def test_written_paths_are_relative_to_the_working_directory(
        self, writing_config, monkeypatch
    ):
        """Output paths resolve against the config's directory, so they arrive absolute."""
        monkeypatch.chdir(writing_config.parent)
        result = runner.invoke(app, ["run", str(writing_config)])
        assert result.exit_code == 0, result.output
        assert "wrote out.nc" in result.output

    def test_failing_pipeline_exits_non_zero(self, tmp_path, synthetic_data_dir):
        """A hard failure from the library must reach the shell as an exit code."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            f"""\
[inputs.daily]
path = "{synthetic_data_dir / "daily.nc"}"
vars = ["temperature"]

[outputs.daily]
path = "{tmp_path / "missing" / "out.nc"}"
vars = ["temperature"]
"""
        )
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code != 0
        assert isinstance(result.exception, FileNotFoundError)


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


class TestGraphCommand:
    """The command's own job: where the file goes and in which format."""

    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_generates_dot_file(self, config_toml, tmp_path):
        out = tmp_path / "pipeline"
        result = runner.invoke(app, ["graph", str(config_toml), "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.with_suffix(".dot").exists()
        assert "mean_temperature_weekly" in out.with_suffix(".dot").read_text()

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["graph", str(tmp_path / "no.toml")])
        assert result.exit_code != 0


class TestGraphRendering:
    """--png/--pdf render through the graphviz API, and failures are surfaced."""

    @pytest.mark.skipif(not shutil.which("dot"), reason="graphviz not installed")
    def test_png_is_written(self, config_toml, tmp_path):
        out = tmp_path / "pipeline"
        result = runner.invoke(
            app, ["graph", str(config_toml), "--output", str(out), "--png"]
        )
        assert result.exit_code == 0, result.output
        png = out.with_suffix(".png")
        assert png.exists()
        assert png.read_bytes().startswith(b"\x89PNG")

    def test_graph_png_reports_missing_dot(self, config_toml, tmp_path, monkeypatch):
        # Previously subprocess.run(["dot", ...]) ran without check=True, so a
        # missing binary produced no output, no error and a zero exit code.
        import graphviz

        def boom(*args, **kwargs):
            raise graphviz.ExecutableNotFound(["dot"])

        monkeypatch.setattr(graphviz.Digraph, "pipe", boom)

        out = tmp_path / "pipeline"
        result = runner.invoke(
            app, ["graph", str(config_toml), "--output", str(out), "--png"]
        )
        assert result.exit_code != 0
        assert "graphviz" in result.output.lower()
        assert not out.with_suffix(".png").exists()


class TestWorkingDirectoryImports:
    """The CLI appends the working directory so `_import_path` can resolve locally."""

    def test_cwd_is_appended_not_prepended(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "path", ["/first", "/second"])
        _prepare_import_path()
        assert sys.path[-1] == str(tmp_path)

    def test_already_present_cwd_is_not_duplicated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "path", [str(tmp_path), "/other"])
        _prepare_import_path()
        assert sys.path.count(str(tmp_path)) == 1

    def test_safe_path_disables_it(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "path", ["/only"])
        monkeypatch.setattr(sys, "flags", SimpleNamespace(safe_path=True))
        _prepare_import_path()
        assert sys.path == ["/only"]

    def test_local_module_resolves_through_the_cli(self, tmp_path, monkeypatch):
        """A module beside the config resolves when it is the working directory."""
        (tmp_path / "local_nodes.py").write_text(
            "def doubled(scalar: float) -> float:\n    return 2 * scalar\n"
        )
        (tmp_path / "config.toml").write_text('[local]\n_import_path = "local_nodes"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["graph", "config.toml", "--output", "graph"])
        assert result.exit_code == 0, result.output


class TestErrorRendering:
    """`main` prints a ConduitError alone; anything else keeps its traceback."""

    def test_conduit_error_prints_message_without_traceback(self, monkeypatch, capsys):
        def _raise():
            raise ConduitValueError("something the user can fix")

        monkeypatch.setattr("conduit.cli.app.app", _raise)
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error: something the user can fix" in captured.err
        assert "Traceback" not in captured.err

    def test_other_exceptions_propagate(self, monkeypatch):
        """A bug must keep its frames, so `main` must not swallow it."""

        def _raise():
            raise TypeError("a bug, not a bad input")

        monkeypatch.setattr("conduit.cli.app.app", _raise)
        with pytest.raises(TypeError, match="a bug"):
            main()

    def test_input_check_error_is_a_conduit_error(self):
        assert issubclass(InputCheckError, ConduitError)


class TestErrorTypes:
    """Concrete errors keep the stdlib type a library caller would catch."""

    @pytest.mark.parametrize(
        ("error", "stdlib"),
        [
            (ConduitValueError, ValueError),
            (ConduitFileNotFoundError, FileNotFoundError),
            (ConduitPermissionError, PermissionError),
        ],
    )
    def test_inherits_stdlib_type(self, error, stdlib):
        assert issubclass(error, stdlib)
        assert issubclass(error, ConduitError)

    def test_base_is_not_a_value_error(self):
        """`except ValueError` must not catch a missing-file error by accident."""
        assert not issubclass(ConduitError, ValueError)
