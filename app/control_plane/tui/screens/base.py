"""Base screen primitives for control-plane TUI."""

from __future__ import annotations

from typing import Iterable, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.domain.errors import ControlPlaneError
from app.control_plane.tui.navigation import Route, ROUTE_TITLES
from app.control_plane.tui.uikit import ErrorBanner, ErrorPayload


class BaseControlScreen(Screen):
    """Common shell for all control-plane screens."""

    ROUTE: Route = Route.DASHBOARD
    SUBTITLE = ""
    PRIMARY_ACTIONS: tuple[tuple[str, str], ...] = ()

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context
        self.error_banner = ErrorBanner()

    @property
    def screen_title(self) -> str:
        return ROUTE_TITLES[self.ROUTE]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="cp-screen-root"):
            yield Static(self.screen_title, classes="cp-screen-title")
            if self.SUBTITLE:
                yield Static(self.SUBTITLE, classes="cp-screen-subtitle")
            yield self.error_banner
            with Horizontal(classes="cp-primary-actions"):
                for label, action_id in self.PRIMARY_ACTIONS:
                    yield Button(label, id=action_id, classes="cp-primary-button")
            with Container(classes="cp-screen-body"):
                yield from self.compose_body()
            yield Static(self.key_hint_text(), classes="cp-key-hints")
        yield Footer()

    def compose_body(self) -> ComposeResult:
        yield Static("Not implemented")

    def key_hint_text(self) -> str:
        return "F1 Help  Esc Back  Ctrl+K Palette  Ctrl+R Refresh  Ctrl+L Logs  Ctrl+C Quit"

    async def refresh_data(self) -> None:
        """Screen-specific refresh hook."""
        return None

    async def handle_primary_action(self, action_id: str) -> None:
        """Screen-specific primary action hook."""
        return None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "error-banner":
            self.error_banner.toggle_details()
            return
        try:
            await self.handle_primary_action(event.button.id or "")
        except Exception as exc:
            self.show_error(exc)

    def clear_error(self) -> None:
        self.error_banner.clear()

    def show_error(self, error: Exception) -> None:
        if isinstance(error, ControlPlaneError):
            details = ", ".join(f"{k}={v}" for k, v in error.details.items()) if error.details else None
            payload = ErrorPayload(message=error.user_message, code=error.code, details=details)
        else:
            payload = ErrorPayload(message="Unexpected error", code="UNEXPECTED", details=str(error))
        self.error_banner.show_error(payload)

    def jump(self, route: Route) -> None:
        app = self.app
        if hasattr(app, "open_route"):
            app.open_route(route)

    def open_chat(self, agent_id: Optional[str] = None) -> None:
        app = self.app
        if hasattr(app, "open_chat"):
            app.open_chat(agent_id=agent_id)
