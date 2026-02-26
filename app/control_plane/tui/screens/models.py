"""Models management screen."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, RichLog, Static

from app.control_plane.domain.errors import ValidationError
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import format_size


class ModelsScreen(BaseControlScreen):
    ROUTE = Route.MODELS
    SUBTITLE = "Discover, pull, validate, and select Ollama models"
    PRIMARY_ACTIONS = (
        ("Refresh", "models-refresh"),
        ("Pull Model", "models-pull"),
        ("Validate", "models-validate"),
        ("Set Default", "models-default"),
        ("Endpoint Config", "models-config"),
    )

    def __init__(self, context):
        super().__init__(context)
        self.summary = Static(classes="cp-card")
        self.table = DataTable(id="models-table", zebra_stripes=True)
        self.model_input = Input(placeholder="Model name (for pull/select)", id="models-input")
        self.progress = RichLog(id="models-progress", highlight=False, markup=False, wrap=True)
        self._pull_task: asyncio.Task | None = None

    def compose_body(self) -> ComposeResult:
        yield self.summary
        with Horizontal(classes="cp-row"):
            yield Static("Model:")
            yield self.model_input
            yield Button("Cancel Pull", id="models-cancel-pull")
        yield self.table
        yield self.progress

    def on_mount(self) -> None:
        self.table.add_columns("Name", "Size", "Installed", "Default", "Modified")
        self.run_worker(self.refresh_data(), group="models-refresh", exclusive=True)

    async def refresh_data(self) -> None:
        self.clear_error()
        try:
            cfg = self.context.config_service.load().values
            endpoint = await self.context.model_service.detect_endpoint()
            rows = await self.context.model_service.list_models_detailed()
            self.summary.update(
                "\n".join(
                    [
                        f"Endpoint: {cfg.ollama_endpoint}",
                        f"Latency: {endpoint.get('latency_ms', '-') } ms",
                        f"Default model: {cfg.default_model}",
                        f"Detected models: {len(rows)}",
                    ]
                )
            )
            self.table.clear()
            for row in rows:
                self.table.add_row(
                    row["name"],
                    format_size(row.get("size")),
                    "yes" if row.get("installed") else "no",
                    "yes" if row.get("is_default") else "no",
                    row.get("modified_at") or "-",
                )
        except Exception as exc:
            self.show_error(exc)

    async def handle_primary_action(self, action_id: str) -> None:
        mapping = {
            "models-refresh": self._refresh_action,
            "models-pull": self._pull_action,
            "models-validate": self._validate_action,
            "models-default": self._set_default_action,
            "models-config": self._open_config_action,
        }
        handler = mapping.get(action_id)
        if handler:
            await handler()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "models-cancel-pull":
            if self._pull_task and not self._pull_task.done():
                self._pull_task.cancel()
                self.progress.write("⚠️ Pull cancelled.")
            return
        await super().on_button_pressed(event)

    async def _refresh_action(self) -> None:
        self.run_worker(self.refresh_data(), group="models-refresh", exclusive=True)

    async def _pull_action(self) -> None:
        model = self._selected_or_input_model()
        if not model:
            raise ValidationError("Enter or select a model name before pull.")
        self.progress.clear()
        self.progress.write(f"⏳ Pulling model: {model}")

        async def _run_pull() -> None:
            try:
                await self.context.model_service.pull_model(model_name=model, progress_cb=lambda msg: self.progress.write(msg))
                self.progress.write("✅ Pull complete.")
                self.progress.write("Tip: use Set Default to activate this model.")
                await self.refresh_data()
            except asyncio.CancelledError:
                self.progress.write("⚠️ Pull task cancelled.")
            except Exception as exc:
                self.show_error(exc)

        self._pull_task = asyncio.create_task(_run_pull())

    async def _validate_action(self) -> None:
        model = self._selected_or_input_model()
        try:
            result = await self.context.model_service.validate_model(model)
            self.progress.write(f"✅ Validation ok={result['ok']} latency={result['latency_ms']} ms")
            self.progress.write(result.get("response_preview") or "<empty>")
        except Exception as exc:
            self.show_error(exc)

    async def _set_default_action(self) -> None:
        model = self._selected_or_input_model()
        if not model:
            raise ValidationError("Select a model first.")
        self.context.model_service.select_default_model(model)
        self.context.audit_service.log("model.select_default", target=model, details={}, actor="tui")
        self.progress.write(f"✅ Default model set: {model}")
        await self.refresh_data()

    async def _open_config_action(self) -> None:
        self.jump(Route.WIZARD)

    def _selected_or_input_model(self) -> str | None:
        value = self.model_input.value.strip()
        if value:
            return value
        if self.table.row_count <= 0:
            return None
        row = self.table.cursor_row
        if row is None:
            return None
        row_data = self.table.get_row_at(row)
        if not row_data:
            return None
        return str(row_data[0])

