"""Textual TUI application shell for Teiken control plane."""

from __future__ import annotations

from functools import partial
import logging
from typing import Iterable

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen, Screen
from textual.worker import Worker, WorkerState
from textual.widgets import Button, Static

from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.palette import PaletteCommand, TeikenCommandProvider
from app.control_plane.tui.screens import (
    AgentsScreen,
    BootScreen,
    ChatScreen,
    DashboardScreen,
    DoctorScreen,
    HatchScreen,
    HelpScreen,
    LogsScreen,
    ModelsScreen,
    SetupWizardScreen,
    StatusScreen,
)


class QuitConfirmModal(ModalScreen[bool]):
    """Confirmation modal shown when quitting with active runtimes."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Static("Active runtimes detected. Quit and stop them gracefully?", classes="cp-card")
        with Horizontal(classes="cp-row"):
            yield Button("Cancel", id="quit-cancel")
            yield Button("Quit", id="quit-confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)


class TeikenControlPlaneApp(App):
    """Multi-screen control-plane application with command palette and key standards."""

    CSS_PATH = "theme.tcss"
    COMMANDS = App.COMMANDS | {TeikenCommandProvider}
    BINDINGS = [
        Binding("f1", "open_help", "Help"),
        Binding("escape", "back", "Back"),
        Binding("ctrl+k", "command_palette", "Command Palette"),
        Binding("ctrl+s", "save_context", "Save"),
        Binding("ctrl+r", "refresh_screen", "Refresh"),
        Binding("ctrl+l", "focus_logs", "Logs"),
        Binding("ctrl+q", "request_quit", "Quit"),
        # Compatibility alias.
        Binding("ctrl+p", "command_palette", show=False),
    ]

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context
        # Keep Textual's internal `_logger` untouched.
        self._python_logger = logging.getLogger(__name__)

    def on_mount(self) -> None:
        cfg = self.context.config_service.load().values
        if cfg.configured:
            self.push_screen(self._build_screen(Route.DASHBOARD))
        else:
            self.push_screen(self._build_screen(Route.WIZARD))

    def _build_screen(self, route: Route, *, agent_id: str | None = None) -> Screen:
        if route == Route.BOOT:
            return BootScreen(self.context)
        if route == Route.DASHBOARD:
            return DashboardScreen(self.context)
        if route == Route.WIZARD:
            return SetupWizardScreen(self.context)
        if route == Route.MODELS:
            return ModelsScreen(self.context)
        if route == Route.AGENTS:
            return AgentsScreen(self.context)
        if route == Route.HATCH:
            return HatchScreen(self.context)
        if route == Route.CHAT:
            return ChatScreen(self.context, initial_agent_id=agent_id)
        if route == Route.STATUS:
            return StatusScreen(self.context)
        if route == Route.DOCTOR:
            return DoctorScreen(self.context)
        if route == Route.LOGS:
            return LogsScreen(self.context)
        if route == Route.HELP:
            return HelpScreen(self.context)
        raise ValueError(f"Unsupported route: {route}")

    def replace_root(self, route: Route) -> None:
        self.switch_screen(self._build_screen(route))

    def open_route(self, route: Route) -> None:
        if route == Route.DASHBOARD and self.screen_stack:
            self.switch_screen(self._build_screen(Route.DASHBOARD))
            return
        self.push_screen(self._build_screen(route))

    def open_chat(self, agent_id: str | None = None) -> None:
        self.push_screen(self._build_screen(Route.CHAT, agent_id=agent_id))

    def action_open_help(self) -> None:
        self.push_screen(self._build_screen(Route.HELP))

    def action_back(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_refresh_screen(self) -> None:
        current = self.screen
        refresh_fn = getattr(current, "refresh_data", None)
        if callable(refresh_fn):
            self.run_worker(self._run_screen_task(refresh_fn), group="screen-refresh", exclusive=True)

    def action_focus_logs(self) -> None:
        self.open_route(Route.LOGS)

    def action_save_context(self) -> None:
        current = self.screen
        saver = getattr(current, "save_current", None)
        if callable(saver):
            self.run_worker(self._run_screen_task(saver), group="screen-save", exclusive=True)

    def action_request_quit(self) -> None:
        snapshot = self.context.runtime_supervisor.snapshot()
        if snapshot.runtimes:
            self.push_screen(QuitConfirmModal(), callback=self._handle_quit_decision)
            return
        self.exit()

    def on_error(self, event: events.Error) -> None:
        error = getattr(event, "error", RuntimeError("Unknown TUI error"))
        self._python_logger.error(
            "Unhandled TUI error",
            exc_info=(type(error), error, getattr(error, "__traceback__", None)),
        )
        current = self.screen
        show_error = getattr(current, "show_error", None)
        if callable(show_error):
            show_error(error)
        event.stop()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.ERROR:
            return
        error = event.worker.error or RuntimeError("Background task failed")
        self._python_logger.error(
            "Worker error in TUI action",
            exc_info=(type(error), error, getattr(error, "__traceback__", None)),
        )
        current = self.screen
        show_error = getattr(current, "show_error", None)
        if callable(show_error):
            show_error(error)
        event.stop()

    def _handle_quit_decision(self, should_quit: bool) -> None:
        if not should_quit:
            return

        async def _shutdown_then_exit() -> None:
            await self.context.runtime_supervisor.shutdown_gracefully()
            self.exit()

        self.run_worker(_shutdown_then_exit(), group="graceful-shutdown", exclusive=True)

    def get_palette_commands(self) -> Iterable[PaletteCommand]:
        commands: list[PaletteCommand] = [
            PaletteCommand("Go to Dashboard", "Navigation", partial(self.open_route, Route.DASHBOARD), "Open home screen"),
            PaletteCommand("Setup Wizard", "Navigation", partial(self.open_route, Route.WIZARD), "Run guided setup"),
            PaletteCommand("Models", "Navigation", partial(self.open_route, Route.MODELS), "Manage Ollama models"),
            PaletteCommand("Agents", "Navigation", partial(self.open_route, Route.AGENTS), "Manage agent registry"),
            PaletteCommand("Hatch", "Navigation", partial(self.open_route, Route.HATCH), "Create/start agent"),
            PaletteCommand("Chat", "Navigation", partial(self.open_route, Route.CHAT), "Open chat screen"),
            PaletteCommand("Status", "Diagnostics", partial(self.open_route, Route.STATUS), "Detailed health board"),
            PaletteCommand("Doctor", "Diagnostics", partial(self.open_route, Route.DOCTOR), "Run checks and fixes"),
            PaletteCommand("Logs", "Diagnostics", partial(self.open_route, Route.LOGS), "View and follow logs", key_hint="Ctrl+L"),
            PaletteCommand("Refresh Current Screen", "Runtime", self.action_refresh_screen, "Refresh active view", key_hint="Ctrl+R"),
            PaletteCommand("Save Current Screen", "Runtime", self.action_save_context, "Save current form if supported", key_hint="Ctrl+S"),
            PaletteCommand("Start Dev Server", "Runtime", self._start_server, "Start server process"),
            PaletteCommand("Stop Dev Server", "Runtime", self._stop_server, "Stop server process"),
            PaletteCommand("Restart Dev Server", "Runtime", self._restart_server, "Restart server process"),
            PaletteCommand("Help", "Navigation", self.action_open_help, "Show keybindings", key_hint="F1"),
            PaletteCommand("Back", "Navigation", self.action_back, "Go back one screen", key_hint="Esc"),
            PaletteCommand("Quit", "Runtime", self.action_request_quit, "Exit safely", key_hint="Ctrl+Q"),
        ]

        try:
            current = self.screen
        except Exception:
            current = None
        primary_actions = getattr(current, "PRIMARY_ACTIONS", ())
        handle_action = getattr(current, "handle_primary_action", None)
        if primary_actions and callable(handle_action):
            for label, action_id in primary_actions:
                commands.append(
                    PaletteCommand(
                        title=label,
                        group="Actions",
                        callback=partial(self._run_screen_action, action_id),
                        help_text=f"Run action: {label}",
                    )
                )
        return commands

    def _run_screen_action(self, action_id: str) -> None:
        current = self.screen
        handler = getattr(current, "handle_primary_action", None)
        if callable(handler):
            self.run_worker(
                self._run_screen_task(lambda: handler(action_id)),
                group=f"action-{action_id}",
                exclusive=False,
            )

    def _start_server(self) -> None:
        self.context.runtime_supervisor.start_dev_server()
        self.action_refresh_screen()

    def _stop_server(self) -> None:
        self.context.runtime_supervisor.stop_dev_server()
        self.action_refresh_screen()

    def _restart_server(self) -> None:
        self.context.runtime_supervisor.restart_dev_server()
        self.action_refresh_screen()

    async def _run_screen_task(self, task_factory) -> None:
        """Run a screen coroutine with deterministic UI error mapping."""
        try:
            await task_factory()
        except Exception as error:
            current = self.screen
            show_error = getattr(current, "show_error", None)
            if callable(show_error):
                show_error(error)
            return
