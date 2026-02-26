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
            deleted = self.context.agent_service.delete_agent(agent.id)
            if deleted:
                self.context.audit_service.log("agent.delete", target=agent.id, details={}, actor="tui")
        await self.refresh_data()

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

    def _selected_agent(self):
        if self.table.row_count <= 0:
            return None
        row = self.table.cursor_row
        if row is None:
            return None
        row_data = self.table.get_row_at(row)
        if not row_data:
            return None
        name = str(row_data[0])
        return self.context.agent_service.get_agent(name)

    def _remediation_hint(self) -> str:
        agents = self.context.agent_service.list_agents()
        for agent in agents:
            if agent.status.value in {"degraded", "crashed"}:
                if "model" in (agent.last_error or "").lower():
                    return "Hint: model issue detected -> go to Models"
                return "Hint: runtime degraded -> run Doctor"
        return "Hint: use Hatch to create or select an agent and run lifecycle actions."
