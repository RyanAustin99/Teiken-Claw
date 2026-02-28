import pytest

pytest.importorskip("textual")

from textual.css.query import NoMatches
from textual.dom import NoScreen

from app.control_plane.tui.safe_header import SafeHeader


def _raise(exc: Exception):
    raise exc


class _TitleNode:
    def update(self, _content) -> None:
        return None


def test_update_title_ignores_missing_title_node(monkeypatch):
    header = SafeHeader()
    monkeypatch.setattr(header, "query_one", lambda *_args, **_kwargs: _raise(NoMatches("missing title")))

    header._update_title()


def test_update_title_ignores_no_screen(monkeypatch):
    header = SafeHeader()
    monkeypatch.setattr(header, "query_one", lambda *_args, **_kwargs: _TitleNode())
    monkeypatch.setattr(header, "format_title", lambda: _raise(NoScreen()))

    header._update_title()
