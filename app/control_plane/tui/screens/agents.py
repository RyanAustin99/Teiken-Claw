"""Agents manager screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Static

from app.control_plane.domain.errors import ValidationError
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import sanitize_terminal_text


class AgentsScreen(BaseControlScreen):
    ROUTE = Route.AGENTS
    SUBTITLE = "Manage agent runtime lifecycle and configuration"
    PRIMARY_ACTIONS = (
        ("Create", "agents-create"),
        ("Start", "agents-start"),
        ("Stop", "agents-stop"),
        ("Restart", "agents-restart"),
        ("Set Default", "agents-default"),
        ("Delete", "agents-delete"),
    )

    def __init__(self, context):
        super().__init__(context)
        self.table = DataTable(id="agents-table", zebra_stripes=True)
        self.hint = Static(classes="cp-card")
        self.name_input = Input(placeholder="Edit name", id="agent-edit-name")
        self.model_input = Input(placeholder="Edit model", id="agent-edit-model")
        self.tool_input = Input(placeholder="Tool profile (safe|balanced|dangerous)", id="agent-edit-tool")
        self.save_button = Button("Save Edit", id="agents-save-edit")
        self._row_agent_ids: list[str] = []

    def compose_body(self) -> ComposeResult:
        yield self.hint
        yield self.table
        with Horizontal(classes="cp-row"):
            yield self.name_input
            yield self.model_input
            yield self.tool_input
            yield self.save_button

    def on_mount(self) -> None:
        self.table.add_columns("Name", "Status", "Model", "Tool", "Last seen", "Last error")
        self.run_worker(self.refresh_data(), group="agents-refresh", exclusive=True)

    async def refresh_data(self) -> None:
        self.clear_error()
        self.table.clear()
        self._row_agent_ids = []
        agents = self.context.agent_service.list_agents()
        status_icon = {
            "running": "[OK]",
            "degraded": "[WARN]",
            "crashed": "[FAIL]",
            "starting": "[WAIT]",
            "stopping": "[WAIT]",
            "stopped": "[IDLE]",
        }
        for agent in agents:
            last_error = (agent.last_error or "-")[:48]
            self.table.add_row(
                sanitize_terminal_text(agent.name),
                sanitize_terminal_text(f"{status_icon.get(agent.status.value, '[IDLE]')} {agent.status.value}"),
                sanitize_terminal_text(agent.model or "(default)"),
                sanitize_terminal_text(agent.tool_profile),
                sanitize_terminal_text(agent.last_seen_at.isoformat() if agent.last_seen_at else "-"),
                sanitize_terminal_text(last_error),
            )
            self._row_agent_ids.append(agent.id)
        self.hint.update(self._remediation_hint())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "agents-save-edit":
            await self._save_edit()
            return
        await super().on_button_pressed(event)

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "agents-create":
            self.jump(Route.HATCH)
            return
        selected_row = 0
        try:
            selected_row = max(0, int(self.table.cursor_row))
        except Exception:
            selected_row = 0
        agent = self._selected_agent()
        if not agent:
            raise ValidationError("Select an agent first.")
        if action_id == "agents-start":
            await self.context.runtime_supervisor.start_agent(agent.id)
            self.context.audit_service.log("agent.start", target=agent.id, details={}, actor="tui")
        elif action_id == "agents-stop":
            await self.context.runtime_supervisor.stop_agent(agent.id)
            self.context.audit_service.log("agent.stop", target=agent.id, details={}, actor="tui")
        elif action_id == "agents-restart":
            await self.context.runtime_supervisor.restart_agent(agent.id)
            self.context.audit_service.log("agent.restart", target=agent.id, details={}, actor="tui")
        elif action_id == "agents-default":
            self.context.agent_service.set_default_agent(agent.id)
            self.context.audit_service.log("agent.set_default", target=agent.id, details={}, actor="tui")
        elif action_id == "agents-delete":
            deleted = await self.context.runtime_supervisor.delete_agent(agent.id)
            cleanup_error = self.context.runtime_supervisor.get_last_error(agent.id)
            await self._safe_refresh(selected_row=selected_row)
            if cleanup_error:
                self.hint.update(sanitize_terminal_text(f"Delete completed with warnings: {cleanup_error[:180]}"))
            elif deleted:
                self.hint.update(sanitize_terminal_text(f"Deleted agent: {agent.name}"))
            else:
                self.hint.update(sanitize_terminal_text(f"Delete skipped; agent not found: {agent.name}"))
            return
        await self._safe_refresh(selected_row=selected_row)

    async def _save_edit(self) -> None:
        agent = self._selected_agent()
        if not agent:
            raise ValidationError("Select an agent before editing.")
        patch = {}
        if self.name_input.value.strip():
            patch["name"] = self.name_input.value.strip()
        if self.model_input.value.strip():
            patch["model"] = self.model_input.value.strip()
        if self.tool_input.value.strip():
            patch["tool_profile"] = self.tool_input.value.strip()
        if not patch:
            raise ValidationError("No edits entered.")
        patch["_allow_dangerous_override"] = patch.get("tool_profile") == "dangerous"
        self.context.agent_service.update_agent(agent.id, patch)
        self.context.audit_service.log("agent.edit", target=agent.id, details={"patch_keys": sorted(patch.keys())}, actor="tui")
        self.name_input.value = ""
        self.model_input.value = ""
        self.tool_input.value = ""
        await self.refresh_data()

    async def save_current(self) -> None:
        await self._save_edit()

    async def _safe_refresh(self, selected_row: int = 0) -> None:
        try:
            await self.refresh_data()
        except Exception as exc:
            # Keep the screen usable even if a refresh edge case occurs.
            self._row_agent_ids = []
            self.show_error(exc)
            return
        if self.table.row_count <= 0:
            return
        target_row = min(max(selected_row, 0), self.table.row_count - 1)
        try:
            self.table.move_cursor(row=target_row, column=0)
        except Exception:
            try:
                self.table.cursor_coordinate = (target_row, 0)
            except Exception:
                pass

    def _selected_agent(self):
        if self.table.row_count <= 0:
            return None
        try:
            row = self.table.cursor_row
        except Exception:
            row = 0
        if row is None:
            return None
        if row < 0 or row >= len(self._row_agent_ids):
            row = 0
            if row >= len(self._row_agent_ids):
                return None
        agent_id = self._row_agent_ids[row]
        return self.context.agent_service.get_agent(agent_id)

    def _remediation_hint(self) -> str:
        agents = self.context.agent_service.list_agents()
        for agent in agents:
            if agent.status.value in {"degraded", "crashed"}:
                if "model" in (agent.last_error or "").lower():
                    return "Hint: model issue detected -> go to Models"
                return "Hint: runtime degraded -> run Doctor"
        return "Hint: use Hatch to create or select an agent and run lifecycle actions."
