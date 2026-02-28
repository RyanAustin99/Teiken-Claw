"""Dashboard home screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import HealthState, format_health


class DashboardScreen(BaseControlScreen):
    ROUTE = Route.DASHBOARD
    SUBTITLE = "Control plane overview and next actions"
    PRIMARY_ACTIONS = (
        ("H Hatch", "go-hatch"),
        ("A Agents", "go-agents"),
        ("M Models", "go-models"),
        ("C Config", "go-wizard"),
        ("X Doctor", "go-doctor"),
        ("S Status", "go-status"),
        ("T Chat", "go-chat"),
    )

    def __init__(self, context):
        super().__init__(context)
        self.system_card = Static(classes="cp-card")
        self.agents_card = Static(classes="cp-card")
        self.next_action_card = Static(classes="cp-card")
        self._refresh_handle = None

    def compose_body(self) -> ComposeResult:
        with Horizontal(classes="cp-card-grid"):
            yield self.system_card
            yield self.agents_card
            yield self.next_action_card

    def on_mount(self) -> None:
        self.run_worker(self.refresh_data(), group="dashboard-refresh", exclusive=True)
        self._refresh_handle = self.set_interval(2.0, self._queue_refresh)

    def on_unmount(self) -> None:
        if self._refresh_handle is not None:
            self._refresh_handle.stop()

    def _queue_refresh(self) -> None:
        self.run_worker(self.refresh_data(), group="dashboard-refresh", exclusive=True)

    async def refresh_data(self) -> None:
        self.clear_error()
        try:
            cfg = self.context.config_service.load().values
            snapshot = await self.context.runtime_supervisor.snapshot_async()
            endpoint = await self.context.model_service.detect_endpoint()
            models = await self.context.model_service.list_models()
            agents = self.context.agent_service.list_agents()

            server_state = HealthState.HEALTHY if snapshot.dev_server_running else HealthState.DEGRADED
            ollama_state = HealthState.HEALTHY if endpoint.get("ok") else HealthState.FAILED
            model_state = HealthState.HEALTHY if cfg.default_model in models else HealthState.DEGRADED
            storage_state = HealthState.HEALTHY if self.context.paths.control_plane_db.exists() else HealthState.LOADING

            self.system_card.update(
                "\n".join(
                    [
                        "System Health",
                        format_health("Dev server", server_state, snapshot.dev_server_url or "stopped"),
                        format_health("Ollama", ollama_state, f"{cfg.ollama_endpoint} ({endpoint.get('latency_ms', '-') } ms)"),
                        format_health("Default model", model_state, cfg.default_model),
                        format_health("Storage", storage_state, str(self.context.paths.control_plane_db)),
                        f"Last updated: {self.format_time()}",
                    ]
                )
            )

            running = [agent for agent in agents if agent.status.value == "running"]
            default_agent = next((agent for agent in agents if agent.is_default), None)
            self.agents_card.update(
                "\n".join(
                    [
                        "Agents",
                        f"Total: {len(agents)}",
                        f"Running: {len(running)}",
                        f"Default: {default_agent.name if default_agent else '-'}",
                        "Quick: Start/Stop/Restart in Agents screen",
                    ]
                )
            )

            self.next_action_card.update(self._next_action(cfg.configured, models, agents))
        except Exception as exc:
            self.show_error(exc)

    async def handle_primary_action(self, action_id: str) -> None:
        mapping = {
            "go-hatch": Route.HATCH,
            "go-agents": Route.AGENTS,
            "go-models": Route.MODELS,
            "go-wizard": Route.WIZARD,
            "go-doctor": Route.DOCTOR,
            "go-status": Route.STATUS,
            "go-chat": Route.CHAT,
        }
        route = mapping.get(action_id)
        if route:
            self.jump(route)

    @staticmethod
    def _next_action(configured: bool, models: list[str], agents: list) -> str:
        if not configured:
            return "Next Action\nRun setup wizard to finish initial configuration."
        if not models:
            return "Next Action\nNo models installed. Open Models and pull one."
        if not agents:
            return "Next Action\nHatch your first agent."
        return "Next Action\nResume chat with your active/default agent."

