"""Setup wizard screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Static

from app.control_plane.domain.errors import ValidationError
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import sanitize_terminal_text


class SetupWizardScreen(BaseControlScreen):
    ROUTE = Route.WIZARD
    SUBTITLE = "Guided setup without manual file edits"
    PRIMARY_ACTIONS = (("Cancel", "wizard-cancel"),)

    def __init__(self, context):
        super().__init__(context)
        cfg = context.config_service.load().values
        self.step_index = 0
        self.step_title = Static()
        self.step_description = Static(classes="cp-muted")
        self.step_status = Static("")
        self.step_counter = Static("")
        self.data_dir_input = Input(value=str(self.context.paths.base_dir), placeholder="Data directory", id="wiz-data-dir")
        self.endpoint_input = Input(value=cfg.ollama_endpoint, placeholder="Ollama endpoint", id="wiz-endpoint")
        self.model_input = Input(value=cfg.default_model, placeholder="Default model", id="wiz-model")
        self.back_button = Button("Back", id="wizard-back")
        self.next_button = Button("Next", id="wizard-next")
        self.test_button = Button("Test Step", id="wizard-test")

    def compose_body(self) -> ComposeResult:
        yield self.step_counter
        yield self.step_title
        yield self.step_description
        yield self.step_status
        yield self.data_dir_input
        yield self.endpoint_input
        yield self.model_input
        with Horizontal(classes="cp-row"):
            yield self.back_button
            yield self.test_button
            yield self.next_button

    def on_mount(self) -> None:
        self._render_step()

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "wizard-cancel":
            self.jump(Route.DASHBOARD)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "wizard-back":
            self.step_index = max(0, self.step_index - 1)
            self._render_step()
            return
        if button_id == "wizard-next":
            await self._next_step()
            return
        if button_id == "wizard-test":
            await self._test_current_step()
            return
        await super().on_button_pressed(event)

    async def _next_step(self) -> None:
        if self.step_index == 5:
            await self._finish()
            return
        if self.step_index == 2:
            await self._test_endpoint()
        if self.step_index == 4:
            await self._test_validation()
        self.step_index = min(5, self.step_index + 1)
        self._render_step()

    async def _test_current_step(self) -> None:
        self.clear_error()
        if self.step_index == 1:
            await self._test_data_dir()
        elif self.step_index == 2:
            await self._test_endpoint()
        elif self.step_index == 3:
            await self._test_models()
        elif self.step_index == 4:
            await self._test_validation()
        else:
            self.step_status.update("No explicit test for this step.")

    async def _test_data_dir(self) -> None:
        try:
            base = self.data_dir_input.value.strip()
            if not base:
                raise ValidationError("Data directory is required.")
            self.step_status.update(sanitize_terminal_text(f"[OK] Data directory resolved: {base}"))
        except Exception as exc:
            self.show_error(exc)

    async def _test_endpoint(self) -> None:
        try:
            endpoint = self.endpoint_input.value.strip()
            if not endpoint:
                raise ValidationError("Ollama endpoint is required.")
            self.context.config_service.save_patch({"ollama_endpoint": endpoint})
            result = await self.context.model_service.detect_endpoint()
            icon = "[OK]" if result["ok"] else "[FAIL]"
            self.step_status.update(
                sanitize_terminal_text(f"{icon} Ollama endpoint: {result['endpoint']} ({result['latency_ms']} ms)")
            )
        except Exception as exc:
            self.show_error(exc)

    async def _test_models(self) -> None:
        try:
            models = await self.context.model_service.list_models()
            model = self.model_input.value.strip()
            if model and model in models:
                self.step_status.update(sanitize_terminal_text(f"[OK] Default model is installed: {model}"))
            elif models:
                self.step_status.update(
                    sanitize_terminal_text(f"[WARN] Model {model} not found. Installed: {', '.join(models[:6])}")
                )
            else:
                self.step_status.update("[WARN] No models installed yet. Use Models screen to pull one.")
        except Exception as exc:
            self.show_error(exc)

    async def _test_validation(self) -> None:
        try:
            model = self.model_input.value.strip() or None
            result = await self.context.model_service.validate_model(model)
            icon = "[OK]" if result["ok"] else "[FAIL]"
            self.step_status.update(f"{icon} Validation latency: {result['latency_ms']} ms")
        except Exception as exc:
            self.show_error(exc)

    async def _finish(self) -> None:
        try:
            patch = {
                "data_dir": self.data_dir_input.value.strip() or None,
                "ollama_endpoint": self.endpoint_input.value.strip(),
                "default_model": self.model_input.value.strip() or self.context.config_service.load().values.default_model,
                "configured": True,
            }
            self.context.config_service.save_patch(patch)
            self.step_status.update("[OK] Setup complete. Next: hatch your first agent.")
            self.jump(Route.HATCH)
        except Exception as exc:
            self.show_error(exc)

    async def save_current(self) -> None:
        await self._finish()

    def _render_step(self) -> None:
        titles = [
            ("Welcome", "This wizard will configure Teiken for terminal-first usage."),
            ("Data Directory", "Confirm storage path and permissions."),
            ("Ollama Endpoint", "Detect and test endpoint availability."),
            ("Model Selection", "Pick default model or plan to pull one."),
            ("Validation", "Run a short sanity prompt."),
            ("Finish", "Save configuration and move to hatch."),
        ]
        title, desc = titles[self.step_index]
        self.step_counter.update(f"Step {self.step_index + 1} of 6")
        self.step_title.update(title)
        self.step_description.update(desc)
        self.data_dir_input.display = self.step_index == 1
        self.endpoint_input.display = self.step_index == 2
        self.model_input.display = self.step_index in {3, 4}
        self.back_button.disabled = self.step_index == 0
        self.next_button.label = "Finish" if self.step_index == 5 else "Next"
