"""Checks that the hand-written API page keeps up with the package."""

import importlib
import pathlib
import re

import pytest

DOCS = pathlib.Path(__file__).parent.parent / "docs"
API_PAGE = DOCS / "reference" / "python-api.md"
MODULES_DIR = DOCS / "reference" / "modules"

OVERVIEW = API_PAGE.read_text().partition("## Everything else")[0]
OVERVIEW_NAMES = sorted(set(re.findall(r"\| \[`(\w+)`\]", OVERVIEW)))


class TestPythonApiPage:
    """``docs/reference/python-api.md`` is hand-written, and nothing regenerates it.

    It names a subset of the API in its overview table and maps every module in
    the section below, so both halves can drift out of step with the package.
    """

    @pytest.mark.parametrize("name", OVERVIEW_NAMES)
    def test_every_name_in_the_overview_exists(self, name):
        import conduit
        import conduit.config

        assert hasattr(conduit, name) or hasattr(conduit.config, name)

    def test_every_module_page_is_mapped(self):
        pages = sorted(
            p.relative_to(DOCS / "reference").as_posix()
            for p in MODULES_DIR.rglob("*.md")
        )
        text = API_PAGE.read_text()
        assert [p for p in pages if f"({p})" not in text] == []

    def test_every_mapped_module_is_importable(self):
        modules = sorted(
            set(re.findall(r"\| \[`(conduit[\w.]*)`\]", API_PAGE.read_text()))
        )
        assert modules
        for name in modules:
            importlib.import_module(name)

    def test_nothing_is_rendered_from_the_conduit_root(self):
        """A ``::: conduit`` block would re-render symbols the module pages own.

        Two renderings of one object produce two pages carrying the same anchor,
        so cross-references and search results land on an arbitrary one of them.
        The page links to the module pages instead.
        """
        blocks = re.findall(r"^::: (\S+)", API_PAGE.read_text(), flags=re.MULTILINE)
        assert not [b for b in blocks if b == "conduit" or b.startswith("conduit.")]
