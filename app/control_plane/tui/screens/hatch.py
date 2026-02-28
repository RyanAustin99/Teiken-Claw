"""Agent hatch flow screen."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from textual.app import ComposeResult
from textual.widgets import Static

from app.control_plane.domain.models import RunnerType, RuntimeStatus
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import ErrorPayload, sanitize_terminal_text


class HatchScreen(BaseControlScreen):
    ROUTE = Route.HATCH
    SUBTITLE = "One-click hatch, then define identity naturally in chat"
    PRIMARY_ACTIONS = (("Hatch Agent", "hatch-run"),)

    def __init__(self, context):
        super().__init__(context)
        self.info_box = Static(
            "Hatch creates an agent and opens chat immediately. "
            "Name, purpose, and style are set in conversation.",
            classes="cp-card",
        )
        self.status_box = Static(classes="cp-card")
        self.last_agent_id: str | None = None
        self._hatch_in_flight = False

    def compose_body(self) -> ComposeResult:
        yield self.info_box
        yield self.status_box

    async def handle_primary_action(self, action_id: str) -> None:
        if action_id == "hatch-run":
            await self._hatch()

    async def _hatch(self) -> None:
        if self._hatch_in_flight:
            self.status_box.update("Hatch already in progress. Please wait.")
            return
        self._hatch_in_flight = True
        self.clear_error()
        self.status_box.update("Hatching agent...")
        agent = None
        try:
            name = self._next_agent_name()
            tool_profile = "balanced"
            agent = self.context.agent_service.create_agent(
                name=name,
                description=None,
                model=None,
                workspace_path=None,
                tool_profile=tool_profile,
                runner_type=RunnerType.INPROCESS,
                allow_dangerous_override=False,
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
                sanitize_terminal_text(f"[OK] Agent hatched and chat is ready.\nSession: {session.id}")
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
        lines.append("Recovery actions: try Hatch again, or run Doctor/Config from the command palette.")
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

    def _next_agent_name(self) -> str:
        for _ in range(8):
            candidate = f"hatch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4]}"
            if not self.context.agent_service.get_agent(candidate):
                return candidate
        return f"hatch-{uuid4().hex}"
