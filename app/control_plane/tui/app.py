"""Textual TUI for Teiken control plane."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.domain.errors import ControlPlaneError
from app.control_plane.tui.command_router import TuiCommandRouter


class HomeScreen(Screen):
    """Main dashboard."""

    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("ctrl+p", "focus_command", "Command"),
        ("ctrl+k", "focus_command", "Command"),
        ("ctrl+l", "clear_output", "Clear"),
    ]

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context
        self.router = TuiCommandRouter(context=context)
        self.output = RichLog(id="cp-output", auto_scroll=True, highlight=False, markup=False, wrap=True)
        self.prompt = Static(self.router.current_prompt(), id="cp-prompt")
        self.command_input = Input(
            placeholder="Type `teiken status`, `hatch --name claw`, or `chat start <agent>`",
            id="cp-command",
        )

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
                yield Button("Help", id="help")
            yield Static(
                f"Data directory (advanced): {self.context.paths.base_dir}",
                id="cp-data-dir",
            )
            yield self.output
            with Horizontal(id="cp-command-row"):
                yield self.prompt
                yield self.command_input
        yield Footer()

    def on_mount(self) -> None:
        self.command_input.focus()
        self.output.write("Teiken command bar ready. Type `help` for available commands.")

    def action_focus_command(self) -> None:
        self.command_input.focus()

    def action_clear_output(self) -> None:
        self.output.clear()
        self.output.write("Output cleared.")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        await self._run_command(command)

    async def _run_command(self, command: str, *, echo: bool = True) -> None:
        if echo:
            self.output.write(f"{self.router.current_prompt()} {command}")
        try:
            result = await self.router.execute(command)
        except ControlPlaneError as exc:
            self.output.write(f"error: {exc.user_message}")
            if exc.details:
                self.output.write(f"details: {exc.details}")
            self._refresh_prompt()
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.output.write(f"error: unexpected failure ({exc})")
            self._refresh_prompt()
            return

        if result.clear_output:
            self.output.clear()
        if result.output:
            for line in result.output.splitlines():
                self.output.write(line)
        if result.exit_app:
            self.app.exit()
            return
        self._refresh_prompt()

    def _refresh_prompt(self) -> None:
        self.prompt.update(self.router.current_prompt())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        mapping = {
            "status": "status",
            "doctor": "doctor",
            "models": "models list",
            "agents": "agents list",
            "config": "config",
            "logs": "logs --limit 20",
            "help": "help",
        }
        command = mapping.get(button_id)
        if command:
            await self._run_command(command, echo=False)


class TeikenControlPlaneApp(App):
    """Textual application wrapper."""

    CSS = """
    #cp-title { text-style: bold; margin: 1 0; }
    #cp-data-dir { margin: 1 0; color: cyan; }
    #cp-output { margin: 1 0; height: 1fr; border: round #666; padding: 1; }
    #cp-command-row { height: auto; margin: 1 0 0 0; }
    #cp-prompt { width: 20; content-align: center middle; color: cyan; }
    #cp-command { width: 1fr; }
    """

    def __init__(self, context: ControlPlaneContext) -> None:
        super().__init__()
        self.context = context

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(context=self.context))

