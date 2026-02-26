"""Detailed status board screen."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import HealthState, format_health


class StatusScreen(BaseControlScreen):
    ROUTE = Route.STATUS
    SUBTITLE = "Detailed runtime and health board"
    PRIMARY_ACTIONS = (("Refresh", "status-refresh"), ("Restart Server", "status-restart-server"))

    def __init__(self, context):
        super().__init__(context)
        self.server_card = Static(classes="cp-card")
        self.runtime_card = Static(classes="cp-card")
        self.model_card = Static(classes="cp-card")
        self.updated = Static(classes="cp-muted")
        self._timer = None

    def compose_body(self) -> ComposeResult:
        with Horizontal(classes="cp-card-grid"):
            yield self.server_card
            yield self.runtime_card
            yield self.model_card
        yield self.updated

    def on_mount(self) -> None:
        self.run_worker(self.refresh_data(), group="status-refresh", exclusive=True)
        self._timer = self.set_interval(2.0, self._schedule_refresh)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def _schedule_refresh(self) -> None:
        self.run_worker(self.refresh_data(), group="status-refresh", exclusive=True)

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "status-refresh":
            await self.refresh_data()
        elif action_id == "status-restart-server":
            self.context.runtime_supervisor.restart_dev_server()
            await self.refresh_data()

    async def refresh_data(self) -> None:
        try:
            snapshot = await self.context.runtime_supervisor.snapshot_async()
            cfg = self.context.config_service.load().values
            endpoint = await self.context.model_service.detect_endpoint()
            self.server_card.update(
                "\n".join(
                    [
                        "Dev Server",
                        format_health(
                            "State",
                            HealthState.HEALTHY if snapshot.dev_server_running else HealthState.DEGRADED,
                            "running" if snapshot.dev_server_running else "stopped",
                        ),
                        f"URL: {snapshot.dev_server_url or '-'}",
                    ]
                )
            )
            runtime_lines = [
                "Supervisor",
                f"In-flight Ollama: {snapshot.global_inflight_ollama}/{snapshot.max_inflight_ollama}",
                f"Active runtimes: {len(snapshot.runtimes)}",
            ]
            for runtime in snapshot.runtimes[:10]:
                runtime_lines.append(
                    f"- {runtime.agent_id[:8]} {runtime.status.value} q={runtime.queued} overflow={runtime.overflow_count}"
                )
            self.runtime_card.update("\n".join(runtime_lines))
            self.model_card.update(
                "\n".join(
                    [
                        "Ollama + Model",
                        format_health("Endpoint", HealthState.HEALTHY if endpoint.get("ok") else HealthState.FAILED, cfg.ollama_endpoint),
                        f"Latency: {endpoint.get('latency_ms', '-')} ms",
                        format_health(
                            "Default model",
                            HealthState.HEALTHY if cfg.default_model in endpoint.get("details", {}).get("models", []) else HealthState.DEGRADED,
                            cfg.default_model,
                        ),
                    ]
                )
            )
            self.updated.update(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as exc:
            self.show_error(exc)
