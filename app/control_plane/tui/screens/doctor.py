"""Doctor diagnostics screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import sanitize_terminal_text


class DoctorScreen(BaseControlScreen):
    ROUTE = Route.DOCTOR
    SUBTITLE = "Run deterministic checks and apply fix actions"
    PRIMARY_ACTIONS = (("Run Checks", "doctor-run"), ("Export Report", "doctor-export"), ("Run Fix", "doctor-fix"))

    def __init__(self, context):
        super().__init__(context)
        self.summary = Static(classes="cp-card")
        self.table = DataTable(id="doctor-table", zebra_stripes=True)
        self._last_report_lines: list[str] = []
        self._last_fix_actions: list[str] = []

    def compose_body(self) -> ComposeResult:
        yield self.summary
        yield self.table
        with Horizontal(classes="cp-row"):
            yield Button("Open Config", id="doctor-open-config")
            yield Button("Open Models", id="doctor-open-models")
            yield Button("Restart Server", id="doctor-restart-server")

    def on_mount(self) -> None:
        self.table.add_columns("Status", "Check", "Summary", "Fix")
        self.run_worker(self.refresh_data(), group="doctor-run", exclusive=True)

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "doctor-run":
            await self.refresh_data()
        elif action_id == "doctor-export":
            if not self._last_report_lines:
                await self.refresh_data()
            export_path = self.context.paths.exports_dir / "doctor_report.txt"
            self.context.log_service.export(export_path, self._last_report_lines)
            self.summary.update(f"Doctor report exported: {export_path}")
        elif action_id == "doctor-fix":
            await self._run_selected_fix()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "doctor-open-config":
            self.jump(Route.WIZARD)
            return
        if button_id == "doctor-open-models":
            self.jump(Route.MODELS)
            return
        if button_id == "doctor-restart-server":
            self.context.runtime_supervisor.restart_dev_server()
            await self.refresh_data()
            return
        await super().on_button_pressed(event)

    async def refresh_data(self) -> None:
        self.clear_error()
        try:
            report = await self.context.doctor_service.run_checks()
            self.table.clear()
            self._last_report_lines = [f"Doctor overall: {report.overall_status.value}"]
            self._last_fix_actions = []
            for check in report.checks:
                icon = {"pass": "[OK]", "warn": "[WARN]", "fail": "[FAIL]"}.get(check.status.value, "[INFO]")
                fix = check.fix_action or "-"
                self.table.add_row(
                    icon,
                    sanitize_terminal_text(check.name),
                    sanitize_terminal_text(check.summary),
                    sanitize_terminal_text(fix),
                )
                line = sanitize_terminal_text(f"[{check.status.value}] {check.name}: {check.summary}")
                if check.suggestion:
                    line += sanitize_terminal_text(f" | fix: {check.suggestion}")
                self._last_report_lines.append(line)
                self._last_fix_actions.append(fix)
            self.summary.update(f"Doctor overall: {report.overall_status.value.upper()} ({len(report.checks)} checks)")
        except Exception as exc:
            self.show_error(exc)

    async def _run_selected_fix(self) -> None:
        if self.table.row_count <= 0:
            return
        row = self.table.cursor_row
        if row is None:
            return
        fix = self._last_fix_actions[row] if row < len(self._last_fix_actions) else "-"
        if fix == "open_config":
            self.jump(Route.WIZARD)
            return
        if fix == "open_models":
            self.jump(Route.MODELS)
            return
        if fix == "restart_server":
            self.context.runtime_supervisor.restart_dev_server()
            await self.refresh_data()
            return
        self.summary.update("No automatic fix action for selected check.")

