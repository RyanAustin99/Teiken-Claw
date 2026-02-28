import pytest

pytest.importorskip("textual")

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.dom import NoScreen
from textual.screen import Screen
from textual.widgets import Static

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


@pytest.mark.asyncio
async def test_safe_header_survives_rapid_screen_switches():
    class _ScreenA(Screen):
        def compose(self) -> ComposeResult:
            yield SafeHeader(show_clock=True)
            yield Static("A")

    class _ScreenB(Screen):
        def compose(self) -> ComposeResult:
            yield SafeHeader(show_clock=True)
            yield Static("B")

    class _App(App[None]):
        CSS = ""

        def on_mount(self) -> None:
            self.push_screen(_ScreenA())

    app = _App()
    async with app.run_test() as pilot:
        await pilot.pause()
        for _ in range(120):
            app.switch_screen(_ScreenB())
            app.switch_screen(_ScreenA())
        await pilot.pause()
