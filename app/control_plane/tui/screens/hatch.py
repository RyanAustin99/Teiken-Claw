"""Agent hatch flow screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Select, Static

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import RunnerType, RuntimeStatus
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import ErrorPayload, sanitize_terminal_text


class HatchScreen(BaseControlScreen):
    ROUTE = Route.HATCH
    SUBTITLE = "Create, configure, and start an agent runtime"
    PRIMARY_ACTIONS = (("Hatch", "hatch-run"), ("Start Chat", "hatch-chat"))

    def __init__(self, context):
        super().__init__(context)
        cfg = context.config_service.load().values
        self.name_input = Input(placeholder="Name (required, unique)", id="hatch-name")
        self.desc_input = Input(placeholder="Description", id="hatch-desc")
        self.model_input = Input(value=cfg.default_model, placeholder="Model override (optional)", id="hatch-model")
        self.workspace_input = Input(placeholder="Workspace path (optional)", id="hatch-workspace")
        self.tool_profile = Select(
            options=[("safe", "safe"), ("balanced", "balanced"), ("dangerous", "dangerous")],
            value="balanced",
            id="hatch-tool-profile",
        )
        self.status_box = Static(classes="cp-card")
        self.last_agent_id: str | None = None
        self._hatch_in_flight = False

    def compose_body(self) -> ComposeResult:
        yield self.name_input
        yield self.desc_input
        yield self.model_input
        yield self.workspace_input
        with Horizontal(classes="cp-row"):
            yield Static("Tool profile:")
            yield self.tool_profile
        with Horizontal(classes="cp-row"):
            yield Button("Open Config", id="hatch-config")
            yield Button("Run Doctor", id="hatch-doctor")
            yield Button("Go Models", id="hatch-models")
            yield Button("Retry Start", id="hatch-retry")
            yield Button("Edit Agent", id="hatch-edit")
        yield self.status_box

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "hatch-run":
            await self._hatch()
        elif action_id == "hatch-chat":
            if self.last_agent_id:
                self.open_chat(agent_id=self.last_agent_id)
            else:
                self.status_box.update("No hatched agent yet.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "hatch-config":
            self.jump(Route.WIZARD)
            return
        if button_id == "hatch-doctor":
            self.jump(Route.DOCTOR)
            return
        if button_id == "hatch-models":
            self.jump(Route.MODELS)
            return
        if button_id == "hatch-edit":
            self.jump(Route.AGENTS)
            return
        if button_id == "hatch-retry":
            if self.last_agent_id:
                try:
                    await self.context.runtime_supervisor.restart_agent(self.last_agent_id)
                    self.status_box.update("Retry start complete.")
                except Exception as exc:
                    payload = self.show_error_payload(exc)
                    self._safe_set_status(self.last_agent_id, RuntimeStatus.CRASHED, str(exc))
                    self.status_box.update(self._build_recovery_message("Retry start failed.", payload))
            else:
                self.status_box.update("No prior hatched agent to retry.")
            return
        await super().on_button_pressed(event)

    async def _hatch(self) -> None:
        if self._hatch_in_flight:
            self.status_box.update("Hatch already in progress. Please wait.")
            return
        self._hatch_in_flight = True
        self.clear_error()
        self.status_box.update("Hatching agent...")
        agent = None
        try:
            name = self.name_input.value.strip()
            if not name:
                raise ValidationError("Agent name is required.")
            tool_profile = str(self.tool_profile.value)
            existing = self.context.agent_service.get_agent(name)
            if existing:
                agent = existing
            else:
                agent = self.context.agent_service.create_agent(
                    name=name,
                    description=self.desc_input.value.strip() or None,
                    model=self.model_input.value.strip() or None,
                    workspace_path=self.workspace_input.value.strip() or None,
                    tool_profile=tool_profile,
                    runner_type=RunnerType.INPROCESS,
                    allow_dangerous_override=tool_profile == "dangerous",
                    prompt_template_version=self.context.config_service.load().values.agent_prompt_template_version,
                )
            self.last_agent_id = agent.id
        except Exception as exc:
            payload = self.show_error_payload(exc)
            self.status_box.update(self._build_recovery_message("Hatch failed before runtime start.", payload))
            self._hatch_in_flight = False
            return

        try:
            await self.context.runtime_supervisor.start_agent(agent.id)
        except Exception as exc:
            payload = self.show_error_payload(exc)
            self._safe_set_status(agent.id, RuntimeStatus.CRASHED, str(exc))
            self.status_box.update(self._build_recovery_message("Hatch failed while starting runtime.", payload))
            self._hatch_in_flight = False
            return

        try:
            session = self.context.session_service.new_session(agent.id, title=f"{agent.name} session")
        except Exception as exc:
            payload = self.show_error_payload(exc)
            self._safe_set_status(agent.id, RuntimeStatus.CRASHED, str(exc))
            self.status_box.update(self._build_recovery_message("Agent created, but session setup failed.", payload))
            self._hatch_in_flight = False
            return

        try:
            self.context.audit_service.log(
                "agent.hatch",
                target=agent.id,
                details={"name": agent.name, "tool_profile": tool_profile, "session_id": session.id},
                actor="tui",
            )
            try:
                await self.context.runtime_supervisor.trigger_hatch_boot(
                    agent_id=agent.id,
                    session_id=session.id,
                    user_metadata={},
                )
            except Exception as boot_exc:
                self._safe_set_status(agent.id, RuntimeStatus.DEGRADED, f"boot_failed: {boot_exc}")
                self.status_box.update("Agent started, but first-message boot failed. Check logs and retry.")
                self._hatch_in_flight = False
                return
            self.status_box.update(
                sanitize_terminal_text(f"[OK] Agent created + started: {agent.name}\nSession: {session.id}")
            )
            self.open_chat(agent_id=agent.id)
        except Exception as exc:
            payload = self.show_error_payload(exc)
            self.status_box.update(self._build_recovery_message("Hatch completed with UI handoff error.", payload))
        finally:
            self._hatch_in_flight = False

    async def save_current(self) -> None:
        await self._hatch()

    def _safe_set_status(self, agent_id: str, status: RuntimeStatus, last_error: str) -> None:
        try:
            self.context.agent_service.set_status(agent_id, status, last_error=last_error)
        except Exception:
            # If the agent no longer exists, keep UI alive and focus on recovery actions.
            pass

    @staticmethod
    def _build_recovery_message(summary: str, payload: ErrorPayload) -> str:
        lines = [summary]
        reason = (payload.message or "").strip()
        details = (payload.details or "").strip()
        if reason and reason.lower() != "unexpected error":
            lines.append(f"Reason: {reason}")
        elif details:
            lines.append(f"Reason: {details}")
        lines.append("Recovery actions: Open Config, Run Doctor, Go Models, Edit Agent, Retry Start.")
        meta: list[str] = []
        if payload.code:
            meta.append(f"code={payload.code}")
        if payload.correlation_id:
            meta.append(f"correlation_id={payload.correlation_id}")
        if payload.logs_path:
            meta.append(f"logs={payload.logs_path}")
        if meta:
            lines.append(" | ".join(meta))
        return sanitize_terminal_text("\n".join(lines))
