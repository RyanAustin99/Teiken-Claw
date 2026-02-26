"""Agent-aware conversation flow for control-plane chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentRecord, OnboardingStatus
from app.control_plane.services.agent_prompt_template_service import AgentPromptTemplateService
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.audit_service import AuditService
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.session_service import SessionService
from app.tools import register_production_tools
from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.loop import run_tool_loop
from app.tools.protocol import ToolResultEnvelope
from app.tools.registry import get_tool_registry


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
class ConversationResponse:
    response: str
    tool_events: List[ToolResultEnvelope] = field(default_factory=list)


class AgentConversationService:
    """Build contextual agent messages and enforce onboarding + tool protocol."""

    def __init__(
        self,
        config_service: ConfigService,
        model_service: ModelService,
        agent_service: AgentService,
        session_service: SessionService,
        prompt_template_service: AgentPromptTemplateService,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self.config_service = config_service
        self.model_service = model_service
        self.agent_service = agent_service
        self.session_service = session_service
        self.prompt_template_service = prompt_template_service
        self.audit_service = audit_service
        self.tool_registry = get_tool_registry()
        existing_tools = set(self.tool_registry.list_tools())
        required = {"files.write", "files.read", "files.list", "files.exists"}
        if not required.issubset(existing_tools):
            register_production_tools(self.tool_registry)
        self.tool_executor = ToolExecutor(self.tool_registry)

    async def generate_response(self, agent_id: str, session_id: str, user_message: str) -> str:
        result = await self.generate_response_with_tools(
            agent_id=agent_id,
            session_id=session_id,
            user_message=user_message,
        )
        return result.response

    async def generate_response_with_tools(
        self,
        agent_id: str,
        session_id: str,
        user_message: str,
    ) -> ConversationResponse:
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

        context = ToolExecutionContext(
            agent_id=agent.id,
            session_id=session.id,
            chat_id=f"cp:{agent.id}",
            is_admin=agent.tool_profile == "dangerous",
            tool_profile=agent.tool_profile,
            workspace_root=Path(agent.workspace_path).expanduser().resolve(),
            actor="control_plane",
            correlation_id=f"cp-{session.id}",
            max_calls_per_message=max(1, cfg.max_tool_calls_per_message),
            timeout_sec=max(1.0, float(cfg.tool_call_timeout_sec)),
            audit_log=self._audit_log,
        )

        async def _model_call(loop_messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, object]]]:
            output = await self.model_service.chat_messages(messages=loop_messages, model=agent.model)
            return output, []

        loop_result = await run_tool_loop(
            initial_messages=messages,
            model_call=_model_call,
            executor=self.tool_executor,
            execution_context=context,
            max_tool_turns_per_request=max(1, cfg.max_tool_turns_per_request),
        )
        return ConversationResponse(
            response=loop_result.final_response,
            tool_events=loop_result.tool_events,
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
            if answer and answer != agent.name:
                patch["name"] = answer
            self.agent_service.update_agent(agent_id, patch)
            self.session_service.update_onboarding(session_id, OnboardingStatus.IN_PROGRESS, step=3)
            return "Got it. What is my primary purpose for you? (one short paragraph)"

        self.agent_service.update_onboarding_profile(agent_id, purpose=answer, complete=True)
        self.session_service.update_onboarding(session_id, OnboardingStatus.COMPLETE, step=3)
        return (
            "Onboarding complete. I understand my role, workspace, tools, and skills context. "
            "Tell me the first task you want me to execute."
        )

    def _resolve_tools(self, tool_profile: str) -> List[str]:
        try:
            registered = self.tool_registry.list_tools()
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

    def _audit_log(
        self,
        action: str,
        target: Optional[str],
        details: Optional[Dict[str, object]],
        actor: str,
    ) -> None:
        if not self.audit_service:
            return
        self.audit_service.log(action=action, target=target, details=details, actor=actor)
