"""Agent-aware conversation flow for control-plane chat."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentRecord, OnboardingStatus
from app.control_plane.services.agent_prompt_template_service import AgentPromptTemplateService
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.session_service import SessionService

TOOL_CALL_TAG_PATTERN = re.compile(
    r"<TEIKEN_TOOL_CALL>\s*(.*?)\s*</TEIKEN_TOOL_CALL>",
    re.IGNORECASE | re.DOTALL,
)
TOOL_RESULT_OPEN = "<TEIKEN_TOOL_RESULT>"
TOOL_RESULT_CLOSE = "</TEIKEN_TOOL_RESULT>"
MAX_TOOL_EXECUTION_TURNS = 4
MAX_READ_PREVIEW_CHARS = 8000
MAX_LIST_ITEMS = 200


TOOL_PROFILE_CAPABILITIES: Dict[str, List[str]] = {
    "safe": [
        "General reasoning and planning",
        "Safe-by-default task execution",
        "Non-destructive guidance and analysis",
    ],
    "balanced": [
        "General reasoning and planning",
        "Expanded operational actions within guarded limits",
        "Troubleshooting and workflow orchestration",
    ],
    "dangerous": [
        "Full operational control of available tools",
        "High-impact execution with explicit user confirmation",
        "Advanced automation and environment changes",
    ],
}


TOOL_PROFILE_DEFAULT_TOOLS: Dict[str, List[str]] = {
    "safe": ["echo", "time", "status", "files.read", "files.list", "files.exists", "web.search"],
    "balanced": ["echo", "time", "status", "files.read", "files.list", "files.exists", "files.write", "web.search", "exec"],
    "dangerous": ["all-registered-tools"],
}


@dataclass
class ToolExecutionEvent:
    call_id: str
    tool: str
    ok: bool
    elapsed_ms: int
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def receipt(self) -> str:
        payload: Dict[str, Any] = {
            "id": self.call_id,
            "ok": self.ok,
            "tool": self.tool,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.ok:
            payload["result"] = self.result
        else:
            payload["error"] = self.error or "tool execution failed"
        return f"{TOOL_RESULT_OPEN}\n{json.dumps(payload, ensure_ascii=False)}\n{TOOL_RESULT_CLOSE}"


@dataclass
class ConversationResponse:
    response: str
    tool_events: List[ToolExecutionEvent] = field(default_factory=list)


class AgentConversationService:
    """Builds contextual agent messages and enforces onboarding flow."""

    def __init__(
        self,
        config_service: ConfigService,
        model_service: ModelService,
        agent_service: AgentService,
        session_service: SessionService,
        prompt_template_service: AgentPromptTemplateService,
    ) -> None:
        self.config_service = config_service
        self.model_service = model_service
        self.agent_service = agent_service
        self.session_service = session_service
        self.prompt_template_service = prompt_template_service

    async def generate_response(self, agent_id: str, session_id: str, user_message: str) -> str:
        result = await self.generate_response_with_tools(agent_id=agent_id, session_id=session_id, user_message=user_message)
        return result.response

    async def generate_response_with_tools(self, agent_id: str, session_id: str, user_message: str) -> ConversationResponse:
        agent = self.agent_service.get_agent(agent_id)
        if not agent:
            raise ValidationError("Unknown agent for chat request.", details={"agent_id": agent_id})
        session = self.session_service.get_session(session_id)
        if not session:
            raise ValidationError("Unknown chat session.", details={"session_id": session_id})
        if session.agent_id != agent.id:
            raise ValidationError(
                "Session is not attached to this agent.",
                details={"session_id": session_id, "agent_id": agent.id},
            )

        onboarding_response = self._handle_onboarding(agent_id=agent.id, session_id=session.id, message=user_message)
        if onboarding_response is not None:
            return ConversationResponse(response=onboarding_response)

        cfg = self.config_service.load().values
        capability_lines = TOOL_PROFILE_CAPABILITIES.get(agent.tool_profile, TOOL_PROFILE_CAPABILITIES["safe"])
        tool_lines = self._resolve_tools(agent.tool_profile)
        skill_lines = self._resolve_skills()
        system_prompt = self.prompt_template_service.render(
            agent,
            default_model=cfg.default_model,
            capability_lines=capability_lines,
            tool_lines=tool_lines,
            skill_lines=skill_lines,
        )

        transcript = self.session_service.get_transcript(session_id)
        history = transcript[-30:]
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in history:
            if item.role not in {"user", "assistant"}:
                continue
            messages.append({"role": item.role, "content": item.content})

        tool_events: List[ToolExecutionEvent] = []
        for _ in range(MAX_TOOL_EXECUTION_TURNS):
            assistant_output = await self.model_service.chat_messages(messages=messages, model=agent.model)
            calls, parse_errors = self._extract_tool_calls(assistant_output)
            if parse_errors:
                tool_events.extend(parse_errors)

            if not calls:
                return ConversationResponse(response=assistant_output, tool_events=tool_events)

            messages.append({"role": "assistant", "content": assistant_output})
            turn_events: List[ToolExecutionEvent] = []
            for call in calls:
                turn_events.append(self._execute_tool_call(agent, call))
            tool_events.extend(turn_events)

            receipt_lines = [event.receipt() for event in turn_events]
            if parse_errors:
                receipt_lines.extend(event.receipt() for event in parse_errors)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Tool execution receipts:\n"
                        + "\n".join(receipt_lines)
                        + "\nUse receipts above. If more actions are needed, emit TEIKEN_TOOL_CALL blocks only. "
                        "Otherwise provide the final response for the user."
                    ),
                }
            )

        return ConversationResponse(
            response=(
                "I reached the maximum tool execution turns for this request. "
                "Please narrow the scope and try again."
            ),
            tool_events=tool_events,
        )

    def _handle_onboarding(self, agent_id: str, session_id: str, message: str) -> Optional[str]:
        agent = self.agent_service.get_agent(agent_id)
        session = self.session_service.get_session(session_id)
        if not agent or not session:
            return None

        if agent.onboarding_complete:
            if session.onboarding_status != OnboardingStatus.COMPLETE:
                self.session_service.update_onboarding(session_id, OnboardingStatus.COMPLETE, step=3)
            return None

        if session.onboarding_status == OnboardingStatus.PENDING:
            self.session_service.update_onboarding(session_id, OnboardingStatus.IN_PROGRESS, step=1)
            return "Before we continue: what name should I call you?"

        if session.onboarding_status != OnboardingStatus.IN_PROGRESS:
            self.session_service.update_onboarding(session_id, OnboardingStatus.IN_PROGRESS, step=1)
            return "Let us finish setup first. What name should I call you?"

        answer = message.strip()
        if not answer:
            return "I did not catch that. Please provide a short answer."

        step = session.onboarding_step
        if step <= 1:
            self.agent_service.update_onboarding_profile(agent_id, user_name=answer, complete=False)
            self.session_service.update_onboarding(session_id, OnboardingStatus.IN_PROGRESS, step=2)
            return f"Great, {answer}. What would you like this agent to be called?"

        if step == 2:
            patch: Dict[str, object] = {"agent_profile_agent_name": answer}
            # Keep display name aligned if user renames the hatched agent.
            if answer and answer != agent.name:
                patch["name"] = answer
            self.agent_service.update_agent(agent_id, patch)
            self.session_service.update_onboarding(session_id, OnboardingStatus.IN_PROGRESS, step=3)
            return "Got it. What is my primary purpose for you? (one short paragraph)"

        # Final onboarding step.
        self.agent_service.update_onboarding_profile(agent_id, purpose=answer, complete=True)
        self.session_service.update_onboarding(session_id, OnboardingStatus.COMPLETE, step=3)
        return (
            "Onboarding complete. I understand my role, workspace, tools, and skills context. "
            "Tell me the first task you want me to execute."
        )

    @staticmethod
    def _resolve_tools(tool_profile: str) -> List[str]:
        try:
            from app.tools.registry import get_tool_registry

            registered = get_tool_registry().list_tools()
        except Exception:
            registered = []

        if tool_profile == "dangerous":
            return registered or TOOL_PROFILE_DEFAULT_TOOLS["dangerous"]
        if not registered:
            return TOOL_PROFILE_DEFAULT_TOOLS.get(tool_profile, TOOL_PROFILE_DEFAULT_TOOLS["safe"])
        if tool_profile == "safe":
            return [name for name in registered if "exec" not in name.lower() and "shell" not in name.lower()]
        return registered

    @staticmethod
    def _resolve_skills() -> List[str]:
        try:
            from app.skills.loader import get_skill_loader

            return sorted(get_skill_loader().list_skills())
        except Exception:
            return []

    @staticmethod
    def _extract_tool_calls(model_output: str) -> tuple[List[Dict[str, Any]], List[ToolExecutionEvent]]:
        calls: List[Dict[str, Any]] = []
        errors: List[ToolExecutionEvent] = []
        matches = list(TOOL_CALL_TAG_PATTERN.finditer(model_output))
        if not matches:
            return calls, errors

        for index, match in enumerate(matches, start=1):
            call_id = f"tc_parse_{index}"
            block = (match.group(1) or "").strip()
            try:
                payload = json.loads(block)
                if not isinstance(payload, dict):
                    raise ValueError("tool call payload must be an object")
                tool_name = str(payload.get("tool", "")).strip()
                if not tool_name:
                    raise ValueError("missing 'tool' field")
                args = payload.get("args", {})
                if args is None:
                    args = {}
                if not isinstance(args, dict):
                    raise ValueError("'args' must be an object")
                payload["id"] = str(payload.get("id") or call_id)
                payload["tool"] = tool_name
                payload["args"] = args
                calls.append(payload)
            except Exception as exc:
                errors.append(
                    ToolExecutionEvent(
                        call_id=call_id,
                        tool="invalid",
                        ok=False,
                        elapsed_ms=0,
                        error=f"invalid tool envelope: {exc}",
                    )
                )
        return calls, errors

    def _execute_tool_call(self, agent: AgentRecord, payload: Dict[str, Any]) -> ToolExecutionEvent:
        call_id = str(payload.get("id") or f"tc_{int(time.time() * 1000)}")
        tool_name = str(payload.get("tool", "invalid"))
        args = payload.get("args", {})
        started = time.perf_counter()
        try:
            result = self._run_tool(agent, tool_name, args if isinstance(args, dict) else {})
            elapsed = int((time.perf_counter() - started) * 1000)
            return ToolExecutionEvent(
                call_id=call_id,
                tool=tool_name,
                ok=True,
                elapsed_ms=elapsed,
                result=result,
            )
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ToolExecutionEvent(
                call_id=call_id,
                tool=tool_name,
                ok=False,
                elapsed_ms=elapsed,
                error=str(exc),
            )

    def _run_tool(self, agent: AgentRecord, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        allowed_tools = self._allowed_tools_for_profile(agent.tool_profile)
        if tool_name not in allowed_tools:
            raise ValidationError(
                f"Tool '{tool_name}' is not allowed for profile '{agent.tool_profile}'.",
                details={"allowed_tools": sorted(allowed_tools)},
            )

        workspace_root = Path(agent.workspace_path).expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        if tool_name == "files.write":
            path = str(args.get("path", "")).strip()
            content = args.get("content", "")
            if not path:
                raise ValidationError("files.write requires 'path'.")
            if not isinstance(content, str):
                content = str(content)
            target = self._resolve_workspace_path(workspace_root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return {"path": path.replace("\\", "/"), "bytes": len(content.encode("utf-8")), "sha256": digest}

        if tool_name == "files.read":
            path = str(args.get("path", "")).strip()
            if not path:
                raise ValidationError("files.read requires 'path'.")
            target = self._resolve_workspace_path(workspace_root, path)
            if not target.exists() or not target.is_file():
                raise ValidationError(f"File not found: {path}")
            content = target.read_text(encoding="utf-8")
            preview = content[:MAX_READ_PREVIEW_CHARS]
            return {
                "path": path.replace("\\", "/"),
                "bytes": len(content.encode("utf-8")),
                "content": preview,
                "truncated": len(preview) < len(content),
            }

        if tool_name == "files.list":
            dir_path = str(args.get("dir", ".")).strip() or "."
            target = self._resolve_workspace_path(workspace_root, dir_path)
            if not target.exists() or not target.is_dir():
                raise ValidationError(f"Directory not found: {dir_path}")
            entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            items = []
            for item in entries[:MAX_LIST_ITEMS]:
                items.append(
                    {
                        "name": item.name,
                        "kind": "dir" if item.is_dir() else "file",
                    }
                )
            return {
                "dir": dir_path.replace("\\", "/"),
                "count": len(entries),
                "items": items,
                "truncated": len(entries) > MAX_LIST_ITEMS,
            }

        if tool_name == "files.exists":
            path = str(args.get("path", "")).strip()
            if not path:
                raise ValidationError("files.exists requires 'path'.")
            target = self._resolve_workspace_path(workspace_root, path)
            return {
                "path": path.replace("\\", "/"),
                "exists": target.exists(),
                "kind": "dir" if target.is_dir() else ("file" if target.is_file() else "missing"),
            }

        raise ValidationError(f"Unsupported tool: {tool_name}")

    @staticmethod
    def _allowed_tools_for_profile(tool_profile: str) -> set[str]:
        if tool_profile == "dangerous":
            return {"files.write", "files.read", "files.list", "files.exists"}
        if tool_profile == "balanced":
            return {"files.write", "files.read", "files.list", "files.exists"}
        return {"files.read", "files.list", "files.exists"}

    @staticmethod
    def _resolve_workspace_path(workspace_root: Path, relative_path: str) -> Path:
        path_obj = Path(relative_path)
        if path_obj.is_absolute():
            raise ValidationError("Absolute paths are not allowed. Use paths relative to agent workspace.")
        if any(part == ".." for part in path_obj.parts):
            raise ValidationError("Path traversal is blocked. Use workspace-relative paths only.")
        resolved = (workspace_root / path_obj).resolve()
        try:
            resolved.relative_to(workspace_root)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValidationError("Resolved path escapes workspace.") from exc
        return resolved
