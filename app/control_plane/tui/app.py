"""Textual TUI for Teiken control plane."""

from __future__ import annotations

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from app.control_plane.bootstrap import ControlPlaneContext


class HomeScreen(Screen):
    """Main dashboard."""

    BINDINGS = [("q", "app.quit", "Quit")]

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context
        self.output = Static("", id="cp-output")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container():
            yield Static("Teiken Control Plane", id="cp-title")
            with Horizontal():
                yield Button("Status", id="status")
                yield Button("Doctor", id="doctor")
                yield Button("Models", id="models")
                yield Button("Agents", id="agents")
                yield Button("Config", id="config")
                yield Button("Logs", id="logs")
            yield Static(
                f"Data directory (advanced): {self.context.paths.base_dir}",
                id="cp-data-dir",
            )
            yield self.output
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "status":
            snapshot = self.context.runtime_supervisor.snapshot()
            self.output.update(
                "\n".join(
                    [
                        f"Dev server: {'running' if snapshot.dev_server_running else 'stopped'}",
                        f"URL: {snapshot.dev_server_url or 'n/a'}",
                        f"Global inflight Ollama: {snapshot.global_inflight_ollama}/{snapshot.max_inflight_ollama}",
                        f"Runtimes: {len(snapshot.runtimes)}",
                    ]
                )
            )
        elif button_id == "doctor":
            report = await self.context.doctor_service.run_checks()
            lines = [f"Doctor: {report.overall_status.value.upper()}"]
            for check in report.checks:
                lines.append(f"- [{check.status.value}] {check.name}: {check.summary}")
            self.output.update("\n".join(lines))
        elif button_id == "models":
            try:
                models = await self.context.model_service.list_models()
                default_model = self.context.config_service.load().values.default_model
                self.output.update(f"Installed models ({len(models)}): {', '.join(models) or 'none'}\nDefault: {default_model}")
            except Exception as exc:
                self.output.update(f"Models check failed: {exc}")
        elif button_id == "agents":
            agents = self.context.agent_service.list_agents()
            if not agents:
                self.output.update("No agents yet. Use `teiken hatch`.")
            else:
                self.output.update(
                    "\n".join(
                        f"- {agent.name} [{agent.status.value}] model={agent.model or '(default)'}"
                        for agent in agents
                    )
                )
        elif button_id == "config":
            effective = self.context.config_service.load()
            cfg = effective.values
            self.output.update(
                "\n".join(
                    [
                        f"Ollama endpoint: {cfg.ollama_endpoint}",
                        f"Default model: {cfg.default_model}",
                        f"Dev server: {cfg.dev_server_host}:{cfg.dev_server_port}",
                        f"Queue limits: inflight={cfg.max_inflight_ollama_requests}, per-agent={cfg.max_agent_queue_depth}",
                        f"Data directory (advanced): {self.context.paths.base_dir}",
                    ]
                )
            )
        elif button_id == "logs":
            lines = self.context.log_service.query(limit=20)
            self.output.update("\n".join(lines) if lines else "No logs available yet.")


class TeikenControlPlaneApp(App):
    """Textual application wrapper."""

    CSS = """
    #cp-title { text-style: bold; margin: 1 0; }
    #cp-data-dir { margin: 1 0; color: cyan; }
    #cp-output { margin: 1 0; height: 1fr; border: round #666; padding: 1; overflow: auto; }
    """

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(context=self.context))

