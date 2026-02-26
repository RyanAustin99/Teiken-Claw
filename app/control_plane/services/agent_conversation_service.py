"""Agent-aware conversation flow for control-plane chat."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import OnboardingStatus
from app.control_plane.services.agent_prompt_template_service import AgentPromptTemplateService
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.session_service import SessionService


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
    "safe": ["echo", "time", "status", "files.read", "web.search"],
    "balanced": ["echo", "time", "status", "files.read", "files.write", "web.search", "exec"],
    "dangerous": ["all-registered-tools"],
}


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
            return onboarding_response

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

        return await self.model_service.chat_messages(messages=messages, model=agent.model)

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
