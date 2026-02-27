"""Help screen with visible keybindings and command guidance."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen


class HelpScreen(BaseControlScreen):
    ROUTE = Route.HELP
    SUBTITLE = "Global shortcuts and navigation hints"
    PRIMARY_ACTIONS = (("Back", "help-back"),)

    def compose_body(self) -> ComposeResult:
        yield Static(
            "\n".join(
                [
                    "Global Keys",
                    "F1 Help",
                    "Esc Back / close modal",
                    "Ctrl+K Command palette",
                    "Ctrl+R Refresh",
                    "Ctrl+L Logs",
                    "Ctrl+Q Quit",
                    "",
                    "Chat Commands",
                    "/help /exit /new /status /model /tools /clear",
                ]
            ),
            classes="cp-card",
        )

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "help-back":
            self.jump(Route.DASHBOARD)

