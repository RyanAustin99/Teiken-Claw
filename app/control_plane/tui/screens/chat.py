"""Terminal chat screen."""

from __future__ import annotations

import asyncio
import time

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, RichLog, Static

from app.control_plane.domain.errors import ValidationError
from app.control_plane.tui.navigation import Route
from app.control_plane.tui.screens.base import BaseControlScreen
from app.control_plane.tui.uikit import sanitize_terminal_text
from app.tools.protocol import extract_tool_results


class ChatScreen(BaseControlScreen):
    ROUTE = Route.CHAT
    SUBTITLE = "Interactive chat sessions with your selected agent"
    PRIMARY_ACTIONS = (
        ("New Session", "chat-new"),
        ("Resume Last", "chat-resume"),
        ("Sessions", "chat-sessions"),
        ("Rename Session", "chat-rename"),
        ("Delete Session", "chat-delete"),
    )

    def __init__(self, context, initial_agent_id: str | None = None):
        super().__init__(context)
        self.initial_agent_id = initial_agent_id
        self.agent_input = Input(placeholder="Agent id or name", id="chat-agent")
        self.transcript = RichLog(id="chat-transcript", highlight=False, markup=False, wrap=True, auto_scroll=True)
        self.message_input = Input(placeholder="Type message or /help command", id="chat-input")
        self.state_line = Static("No active session", classes="cp-muted")
        self.active_agent_id: str | None = None
        self.active_session_id: str | None = None
        self._pending_task: asyncio.Task | None = None
        self._verbose_receipts = False

    def compose_body(self) -> ComposeResult:
        with Horizontal(classes="cp-row"):
            yield Static("Agent:")
            yield self.agent_input
            yield Button("Start", id="chat-start")
        yield self.state_line
        yield self.transcript
        yield self.message_input

    def on_mount(self) -> None:
        if self.initial_agent_id:
            self.agent_input.value = self.initial_agent_id
        self.message_input.focus()
        self.transcript.write(
            sanitize_terminal_text("Chat commands: /help /exit /new /status /model /tools /receipts /verbose /clear")
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        try:
            await self._handle_input(text)
        except Exception as exc:
            self.show_error(exc)
            self.state_line.update("[WARN] Input failed. Use Doctor/Config if issue persists.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "chat-start":
            await self._start_chat_session(new=False)
            return
        await super().on_button_pressed(event)

    async def handle_primary_action(self, action_id: str) -> None:
        try:
            if action_id == "chat-new":
                await self._start_chat_session(new=True)
            elif action_id == "chat-resume":
                await self._resume_latest()
            elif action_id == "chat-sessions":
                self._list_sessions()
            elif action_id == "chat-rename":
                await self._rename_session()
            elif action_id == "chat-delete":
                await self._delete_session()
        except Exception as exc:
            self.show_error(exc)
            self.state_line.update("[WARN] Action failed.")

    async def refresh_data(self) -> None:
        if self.active_agent_id and self.active_session_id:
            self.state_line.update(f"Agent: {self.active_agent_id} | Session: {self.active_session_id}")
        else:
            self.state_line.update("No active session")

    async def _handle_input(self, text: str) -> None:
        if self._pending_task and not self._pending_task.done():
            self.transcript.write("assistant> Still working on the previous message. Please wait.")
            return
        if text.startswith("/"):
            await self._handle_command(text.lower())
            return
        if not self.active_agent_id or not self.active_session_id:
            await self._start_chat_session(new=False)
        if not self.active_agent_id or not self.active_session_id:
            raise ValidationError("No active chat session.")
        self.transcript.write(sanitize_terminal_text(f"you> {text}"))
        start = time.perf_counter()
        self.state_line.update("[WAIT] Agent is thinking...")

        async def _run_message() -> None:
            try:
                response = await self.context.runtime_supervisor.chat(
                    agent_id=self.active_agent_id,
                    session_id=self.active_session_id,
                    message=text,
                )
                elapsed = (time.perf_counter() - start) * 1000
                self._load_transcript()
                self.state_line.update(f"[OK] Responded in {elapsed:.0f} ms")
            except Exception as exc:
                self.show_error(exc)
                self.state_line.update("[WARN] Message failed. Use Doctor/Config if issue persists.")

        self._pending_task = asyncio.create_task(_run_message())

    async def _handle_command(self, command: str) -> None:
        if command in {"/exit", "/quit"}:
            self.jump(Route.DASHBOARD)
            return
        if command == "/help":
            self.transcript.write(
                sanitize_terminal_text("/help /exit /new /status /model /tools /receipts /verbose /clear")
            )
            return
        if command == "/new":
            await self._start_chat_session(new=True)
            return
        if command == "/status":
            snapshot = await self.context.runtime_supervisor.snapshot_async()
            self.transcript.write(
                sanitize_terminal_text(
                    f"status> runtimes={len(snapshot.runtimes)} inflight={snapshot.global_inflight_ollama}/{snapshot.max_inflight_ollama}"
                )
            )
            return
        if command == "/model":
            if not self.active_agent_id:
                self.transcript.write("model> no active agent")
            else:
                agent = self.context.agent_service.get_agent(self.active_agent_id)
                cfg = self.context.config_service.load().values
                self.transcript.write(
                    sanitize_terminal_text(f"model> {agent.model if agent and agent.model else cfg.default_model}")
                )
            return
        if command == "/tools":
            if not self.active_agent_id:
                self.transcript.write("tools> no active agent")
            else:
                agent = self.context.agent_service.get_agent(self.active_agent_id)
                self.transcript.write(sanitize_terminal_text(f"tools> {agent.tool_profile if agent else 'safe'}"))
            return
        if command.startswith("/receipts"):
            limit = 10
            parts = command.split()
            if len(parts) > 1 and parts[1].isdigit():
                limit = max(1, min(100, int(parts[1])))
            await self._show_receipts(limit=limit)
            return
        if command == "/verbose":
            self._verbose_receipts = not self._verbose_receipts
            mode = "on" if self._verbose_receipts else "off"
            self.transcript.write(sanitize_terminal_text(f"receipts verbose {mode}"))
            return
        if command == "/clear":
            self.transcript.clear()
            return
        self.transcript.write(sanitize_terminal_text(f"Unknown command: {command}"))

    async def _start_chat_session(self, new: bool) -> None:
        agent = self._resolve_agent()
        await self.context.runtime_supervisor.start_agent(agent.id)
        self.active_agent_id = agent.id
        if new:
            session = self.context.session_service.new_session(agent.id, title=f"{agent.name} chat")
        else:
            sessions = self.context.session_service.list_sessions(agent.id, limit=1)
            session = sessions[0] if sessions else self.context.session_service.new_session(agent.id, title=f"{agent.name} chat")
        self.active_session_id = session.id
        onboarding_note = ""
        if session.onboarding_status.value != "complete":
            onboarding_note = " | onboarding in progress"
        self.state_line.update(sanitize_terminal_text(f"Chat ready: {agent.name} ({session.id}){onboarding_note}"))
        self._load_transcript()

    async def _resume_latest(self) -> None:
        await self._start_chat_session(new=False)

    def _list_sessions(self) -> None:
        if not self.active_agent_id:
            agent = self._resolve_agent(optional=True)
            if not agent:
                self.transcript.write("sessions> select an agent first")
                return
            agent_id = agent.id
        else:
            agent_id = self.active_agent_id
        sessions = self.context.session_service.list_sessions(agent_id, limit=10)
        if not sessions:
            self.transcript.write("sessions> no sessions")
            return
        self.transcript.write("sessions>")
        for session in sessions:
            self.transcript.write(sanitize_terminal_text(f"- {session.id} ({session.updated_at.isoformat()})"))

    async def _rename_session(self) -> None:
        if not self.active_session_id:
            self.transcript.write("rename> no active session")
            return
        new_title = f"session-{self.active_session_id[:8]}"
        self.context.session_service.rename_session(self.active_session_id, new_title)
        self.transcript.write(sanitize_terminal_text(f"rename> updated title to {new_title}"))

    async def _delete_session(self) -> None:
        if not self.active_session_id:
            self.transcript.write("delete> no active session")
            return
        deleted = self.context.session_service.delete_session(self.active_session_id)
        self.transcript.write("delete> session removed" if deleted else "delete> session not found")
        self.active_session_id = None

    def _load_transcript(self) -> None:
        if not self.active_session_id:
            return
        self.transcript.clear()
        for item in self.context.session_service.get_transcript(self.active_session_id):
            if item.tool_name:
                envelopes = extract_tool_results(item.content)
                if envelopes:
                    for envelope in envelopes:
                        self.transcript.write(sanitize_terminal_text(self._render_tool_line(envelope)))
                        if self._verbose_receipts:
                            self.transcript.write(sanitize_terminal_text(f"  receipt> {envelope.model_dump_json()}"))
                else:
                    outcome = "OK" if item.tool_ok else "DENIED"
                    elapsed = f" {item.tool_elapsed_ms}ms" if item.tool_elapsed_ms is not None else ""
                    self.transcript.write(sanitize_terminal_text(f"[TOOL] {item.tool_name} {outcome}{elapsed}"))
                    if self._verbose_receipts:
                        self.transcript.write(sanitize_terminal_text(f"{item.role}> {item.content}"))
                continue
            self.transcript.write(sanitize_terminal_text(f"{item.role}> {item.content}"))

    async def _show_receipts(self, limit: int) -> None:
        if not self.active_session_id:
            self.transcript.write("receipts> no active session")
            return
        receipts = self.context.session_service.get_tool_receipts(self.active_session_id, limit=limit)
        if not receipts:
            self.transcript.write("receipts> none")
            return
        self.transcript.write(f"receipts> showing {len(receipts)}")
        for receipt in receipts:
            self.transcript.write(sanitize_terminal_text(self._render_tool_line(receipt)))
            if self._verbose_receipts:
                self.transcript.write(sanitize_terminal_text(f"  receipt> {receipt.model_dump_json()}"))

    @staticmethod
    def _render_tool_line(envelope) -> str:
        if envelope.ok:
            result = envelope.result or {}
            path = result.get("path") if isinstance(result, dict) else None
            bytes_written = result.get("bytes") if isinstance(result, dict) else None
            sha = result.get("sha256") if isinstance(result, dict) else None
            suffix = ""
            if path:
                suffix += f" -> {path}"
            if bytes_written is not None:
                suffix += f" ({bytes_written} bytes"
                if sha:
                    suffix += f", sha256={sha[:12]}..."
                suffix += ")"
            return f"[TOOL] {envelope.tool} OK{suffix}"
        error = envelope.error or {}
        reason = error.get("message", "failed") if isinstance(error, dict) else "failed"
        return f"[TOOL] {envelope.tool} DENIED -> {reason}"

    def _resolve_agent(self, optional: bool = False):
        ref = self.agent_input.value.strip()
        if not ref:
            agents = self.context.agent_service.list_agents()
            agent = next((item for item in agents if item.is_default), agents[0] if agents else None)
            if agent:
                return agent
            if optional:
                return None
            raise ValidationError("No agents available. Hatch one first.")
        agent = self.context.agent_service.get_agent(ref)
        if agent:
            return agent
        for item in self.context.agent_service.list_agents():
            if item.id.startswith(ref) or item.name == ref:
                return item
        if optional:
            return None
        raise ValidationError(f"Unknown agent: {ref}")
