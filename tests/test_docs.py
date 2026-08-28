"""Checks that the hand-written API index keeps up with the package."""

import pathlib
import re

import pytest

import conduit

DOCS = pathlib.Path(__file__).parent.parent / "docs"
API_PAGE = DOCS / "reference" / "python-api.md"
MODULES_DIR = DOCS / "reference" / "modules"

PUBLIC_NAMES = [name for name in conduit.__all__ if not name.startswith("__")]


class TestPythonApiPage:
    """``docs/reference/python-api.md`` is a hand-written index of ``conduit.__all__``.

    Nothing regenerates it, so a name added to the package can silently go
    undocumented, and a name removed can leave a dead row behind.
    """

    @pytest.mark.parametrize("name", PUBLIC_NAMES)
    def test_every_public_name_is_indexed(self, name):
        assert re.search(rf"\b{name}\b", API_PAGE.read_text())

    def test_nothing_is_rendered_from_the_conduit_root(self):
        """A ``::: conduit`` block would re-render symbols the module pages own.

        Two renderings of one object produce two pages carrying the same anchor,
        so cross-references and search results land on an arbitrary one of them.
        The index links to the module pages instead.
        """
        blocks = re.findall(r"^::: (\S+)", API_PAGE.read_text(), flags=re.MULTILINE)
        assert not [b for b in blocks if b == "conduit" or b.startswith("conduit.")]


class TestModuleReferenceIndex:
    """``docs/reference/modules/index.md`` lists the module pages by hand."""

    def test_every_module_page_is_listed(self):
        index = MODULES_DIR / "index.md"
        pages = sorted(
            p.relative_to(MODULES_DIR).as_posix()
            for p in MODULES_DIR.rglob("*.md")
            if p != index
        )
        text = index.read_text()
        assert [p for p in pages if f"({p})" not in text] == []
