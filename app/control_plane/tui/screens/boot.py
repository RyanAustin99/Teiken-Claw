"""Boot report screen shown on control-plane startup."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from textual.app import ComposeResult
from textual.widgets import RichLog, Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen


class BootScreen(BaseControlScreen):
    ROUTE = Route.BOOT
    SUBTITLE = "Initializing control plane..."
    PRIMARY_ACTIONS = (("Skip", "boot-skip"),)

    def __init__(self, context):
        super().__init__(context)
        self.log = RichLog(highlight=False, markup=False, wrap=True, id="boot-log")
        self.status = Static("Starting...", id="boot-status")
        self._completed = False

    def compose_body(self) -> ComposeResult:
        yield self.log
        yield self.status

    def on_mount(self) -> None:
        self.run_worker(self._boot_sequence(), group="boot", exclusive=True)

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "boot-skip":
            await self._route_after_boot(force=True)

    async def _boot_sequence(self) -> None:
        steps: list[tuple[str, Callable[[], Awaitable[None]]]] = [
            ("Loading config", self._step_config),
            ("Resolving data directory", self._step_paths),
            ("Checking lock", self._step_lock),
            ("Loading DB", self._step_db),
            ("Checking Ollama endpoint", self._step_ollama),
            ("Starting supervisor", self._step_supervisor),
        ]
        for label, func in steps:
            self.log.write(f"⏳ {label}")
            self.status.update(label)
            try:
                await func()
                self.log.write(f"✅ {label}")
            except Exception as exc:
                self.log.write(f"❌ {label}: {exc}")
        self._completed = True
        self.status.update("Boot checks complete.")
        await asyncio.sleep(0.4)
        await self._route_after_boot()

    async def _route_after_boot(self, force: bool = False) -> None:
        if not self.app.is_running or (not self._completed and not force):
            return
        cfg = self.context.config_service.load().values
        if hasattr(self.app, "replace_root"):
            if cfg.configured:
                self.app.replace_root(Route.DASHBOARD)
            else:
                self.app.replace_root(Route.WIZARD)

    async def _step_config(self) -> None:
        self.context.config_service.load()
        await asyncio.sleep(0.05)

    async def _step_paths(self) -> None:
        _ = self.context.paths.base_dir
        await asyncio.sleep(0.05)

    async def _step_lock(self) -> None:
        # Lock is already acquired before TUI starts; validate its presence.
        _ = self.context.paths.lock_file
        await asyncio.sleep(0.05)

    async def _step_db(self) -> None:
        _ = self.context.agent_service.list_agents()
        await asyncio.sleep(0.05)

    async def _step_ollama(self) -> None:
        await self.context.model_service.detect_endpoint()

    async def _step_supervisor(self) -> None:
        await self.context.runtime_supervisor.snapshot_async()
        await asyncio.sleep(0.05)
