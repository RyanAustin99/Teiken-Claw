"""Logs screen with filtering, follow, export, and copy helpers."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, RichLog, Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen


class LogsScreen(BaseControlScreen):
    ROUTE = Route.LOGS
    SUBTITLE = "Filter, follow, export, and copy diagnostic logs"
    PRIMARY_ACTIONS = (
        ("Refresh", "logs-refresh"),
        ("Toggle Follow", "logs-follow"),
        ("Export", "logs-export"),
        ("Copy Last 50", "logs-copy"),
    )

    def __init__(self, context):
        super().__init__(context)
        self.component_input = Input(placeholder="Filter by component (server/agent/model/db)", id="logs-component")
        self.log_view = RichLog(id="logs-view", highlight=False, markup=False, wrap=True, auto_scroll=True)
        self.status = Static(classes="cp-muted")
        self._follow_task: asyncio.Task | None = None
        self._following = False
        self._last_lines: list[str] = []

    def compose_body(self) -> ComposeResult:
        with Horizontal(classes="cp-row"):
            yield Static("Filter:")
            yield self.component_input
        yield self.log_view
        yield self.status

    def on_mount(self) -> None:
        self.run_worker(self.refresh_data(), group="logs-refresh", exclusive=True)

    def on_unmount(self) -> None:
        if self._follow_task and not self._follow_task.done():
            self._follow_task.cancel()

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "logs-refresh":
            await self.refresh_data()
        elif action_id == "logs-follow":
            await self._toggle_follow()
        elif action_id == "logs-export":
            await self._export_logs()
        elif action_id == "logs-copy":
            await self._copy_last_lines()

    async def refresh_data(self) -> None:
        component = self.component_input.value.strip() or None
        lines = self.context.log_service.query(component=component, limit=200)
        self._last_lines = list(reversed(lines))
        self.log_view.clear()
        if not self._last_lines:
            self.log_view.write("No logs found.")
        for line in self._last_lines:
            self.log_view.write(line)
        self.status.update(f"Lines: {len(self._last_lines)} | Follow: {'on' if self._following else 'off'}")

    async def _toggle_follow(self) -> None:
        if self._following:
            self._following = False
            if self._follow_task and not self._follow_task.done():
                self._follow_task.cancel()
            self.status.update("Follow mode disabled.")
            return

        self._following = True
        component = self.component_input.value.strip() or None
        self.status.update("Follow mode enabled.")

        async def _follow() -> None:
            async for line in self.context.log_service.follow(component=component):
                if not self._following:
                    break
                self.log_view.write(line)

        self._follow_task = asyncio.create_task(_follow())

    async def _export_logs(self) -> None:
        export_path = self.context.paths.exports_dir / "logs_export.txt"
        lines = self._last_lines or self.context.log_service.query(limit=200)
        self.context.log_service.export(export_path, lines)
        self.status.update(f"Exported: {export_path}")

    async def _copy_last_lines(self) -> None:
        payload = "\n".join((self._last_lines or [])[:50])
        self.app.copy_to_clipboard(payload)
        self.status.update("Copied last 50 lines to clipboard.")

