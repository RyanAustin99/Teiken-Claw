"""Agent-aware conversation flow for control-plane chat."""

from __future__ import annotations

import json
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.config.logging import get_logger
from app.config.settings import settings
from app.agent.prompt_assembler import PromptAssembler
from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentOnboardingState, AgentRecord, OnboardingStatus
from app.interfaces.tc_profile_strip import extract_tc_profile
from app.memory.onboarding_extractor import (
    extract_onboarding_prefs,
    parse_llm_onboarding_json_with_confidence,
)
from app.memory.store import get_memory_store
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
from app.persona.resolve import resolve_persona

logger = get_logger(__name__)


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
    "safe": ["echo", "time", "status", "files.read", "files.list", "files.exists", "web"],
    "balanced": ["echo", "time", "status", "files.read", "files.list", "files.exists", "files.write", "web", "exec"],
    "dangerous": ["all-registered-tools"],
}

RESPONSE_META_BANLIST = [
    "operational identity",
    "as an ai",
    "language model",
    "teiken claw agent",
    "keep it respectful",
    "keep it clean and professional",
]

LLM_ONBOARDING_CONFIDENCE_THRESHOLD = 0.8

ONBOARDING_PENDING_BLOCK = (
    "Onboarding is still in progress. "
    "Do not assign yourself a name. "
    "Ask the user what to call them and what they want to call you. "
    "If the user is casual and doesn't answer yet, respond casually but include one short onboarding follow-up question."
)


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
        self.memory_store = get_memory_store()
        self.tool_registry = get_tool_registry()
        self.prompt_assembler = PromptAssembler()
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

        await self._maybe_process_onboarding_reply(agent=agent, session=session, message=user_message)
        agent = self.agent_service.get_agent(agent.id) or agent

        cfg = self.config_service.load().values
        capability_lines = TOOL_PROFILE_CAPABILITIES.get(agent.tool_profile, TOOL_PROFILE_CAPABILITIES["safe"])
        tool_lines = self._resolve_tools(agent.tool_profile)
        style_lines = self._resolve_style_lines(agent)
        skill_lines = self._resolve_skills()
        template_system_prompt = self.prompt_template_service.render(
            agent,
            default_model=cfg.default_model,
            capability_lines=capability_lines,
            tool_lines=tool_lines,
            style_lines=style_lines,
            skill_lines=skill_lines,
        )

        mode_ref = session.active_mode or agent.default_mode or getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0")
        soul_ref = session.active_soul or agent.default_soul or getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")
        base_file_policy = {
            "max_read_bytes": int(getattr(settings, "FILES_MAX_READ_BYTES", 1_048_576)),
            "max_write_bytes": int(getattr(settings, "FILES_MAX_WRITE_BYTES", 262_144)),
            "allowed_extensions": list(getattr(settings, "FILES_ALLOWED_WRITE_EXTENSIONS", [".md", ".txt", ".json", ".yaml", ".yml", ".log"])),
        }
        persona = resolve_persona(
            mode_ref=mode_ref,
            soul_ref=soul_ref,
            tool_profile=agent.tool_profile,
            base_file_policy=base_file_policy,
        )

        transcript = self.session_service.get_transcript(session_id)
        history = transcript[-30:]
        transcript_items = [{"id": str(item.id), "role": item.role, "content": item.content} for item in history]
        bundle = self.prompt_assembler.assemble(
            resolved_soul_ref=persona.resolved_soul_ref,
            resolved_mode_ref=persona.resolved_mode_ref,
            soul_hash=persona.soul.sha256,
            mode_hash=persona.mode.sha256,
            soul_prompt=persona.soul.definition.system_prompt,
            soul_principles=persona.soul.definition.principles,
            mode_overlay_prompt=persona.mode.definition.overlay_prompt,
            mode_output_requirements=persona.mode.definition.output_shape.model_dump(mode="json"),
            memory_items=[],
            transcript_messages=transcript_items,
            effective_tool_policy={
                "allowed_tools": sorted(persona.effective_allowed_tools) if persona.effective_allowed_tools is not None else ["*"],
                "max_tool_turns": persona.max_tool_turns,
            },
            effective_file_policy=persona.effective_file_policy,
            platform_policy_version=str(getattr(settings, "APP_VERSION", "0.0.0")),
        )
        system_prompt = f"{bundle.system_prompt}\n\n# Control Plane Context\n{template_system_prompt}"
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if agent.onboarding_state == AgentOnboardingState.WAITING_USER_PREFS:
            messages.append({"role": "system", "content": ONBOARDING_PENDING_BLOCK})
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
            allowed_tools=set(persona.effective_allowed_tools) if persona.effective_allowed_tools is not None else None,
            file_policy_override=persona.effective_file_policy,
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
            max_tool_turns_per_request=max(1, min(cfg.max_tool_turns_per_request, persona.max_tool_turns or cfg.max_tool_turns_per_request)),
        )
        visible_response = loop_result.final_response or ""
        _, stripped, _ = extract_tc_profile(visible_response)
        visible_response = stripped.strip() or visible_response
        visible_response = await self._enforce_first_person(visible_response, model=agent.model)
        visible_response = await self._enforce_output_guardrails(visible_response, model=agent.model)
        return ConversationResponse(response=visible_response, tool_events=loop_result.tool_events)

    async def _maybe_process_onboarding_reply(self, *, agent: AgentRecord, session, message: str) -> None:
        if agent.onboarding_state != AgentOnboardingState.WAITING_USER_PREFS:
            return
        user_text = (message or "").strip()
        if not user_text:
            return

        transcript = self.session_service.get_transcript(session.id)
        last_assistant = ""
        for item in reversed(transcript):
            if item.role == "assistant":
                last_assistant = item.content
                break

        deterministic = extract_onboarding_prefs(
            user_text=user_text,
            last_assistant_text=last_assistant,
            agent_profile_json=agent.profile_json,
        )
        extracted = dict(deterministic)
        source = "USER" if any(value for value in deterministic.values()) else "LLM_EXTRACTOR"
        if not self._has_onboarding_value(extracted):
            fallback = await self._llm_extract_onboarding_prefs(
                user_text=user_text,
                last_assistant_text=last_assistant,
                model=agent.model,
            )
            for key, value in fallback.items():
                if not extracted.get(key) and value:
                    extracted[key] = value

        if not self._has_onboarding_value(extracted):
            return

        logger.info(
            "Onboarding preferences extracted",
            extra={
                "event": "onboarding_extracted",
                "agent_id": agent.id,
                "fields": sorted([key for key, value in extracted.items() if value]),
            },
        )

        try:
            for key, value in extracted.items():
                if not value:
                    continue
                self.memory_store.create_memory(
                    memory_type="semantic",
                    content=value,
                    scope=f"agent:{agent.id}",
                    source=source,
                    key=key,
                    confidence=0.9 if source == "USER" else 0.8,
                    metadata={"scope": "USER_PREFS", "session_id": session.id},
                )
            # Backward-compatible aggregate card.
            self.memory_store.create_memory(
                memory_type="semantic",
                content=json.dumps(extracted, ensure_ascii=False),
                scope=f"agent:{agent.id}",
                source=source,
                key="user_prefs",
                confidence=0.8,
                metadata={"scope": "USER_PREFS", "session_id": session.id},
            )
        except Exception:
            logger.exception(
                "Failed to persist onboarding prefs memory",
                extra={"agent_id": agent.id, "session_id": session.id},
            )

        profile_json = dict(agent.profile_json or {})
        patch: Dict[str, object] = {}
        user_name = extracted.get("user_preferred_name")
        agent_name = extracted.get("agent_name_preference")
        purpose = extracted.get("agent_purpose")
        tone = extracted.get("tone_preference")
        profanity_level = self._normalize_profanity_level(extracted.get("profanity_level"))

        if user_name:
            patch["agent_profile_user_name"] = user_name
        if agent_name:
            patch["agent_profile_agent_name"] = agent_name
            profile_json["agent_display_name"] = agent_name
        if purpose:
            patch["agent_profile_purpose"] = purpose
        if tone:
            profile_json["tone_preference"] = tone
        if profanity_level:
            profile_json["profanity_level"] = profanity_level
        if profile_json:
            patch["profile_json"] = profile_json

        if user_name or agent_name or purpose:
            patch["is_fresh"] = False
            patch["onboarding_state"] = AgentOnboardingState.ACTIVE
            patch["onboarding_complete"] = True
            patch["onboarding_updated_at"] = datetime.utcnow().isoformat()
            self.session_service.update_onboarding(session.id, OnboardingStatus.COMPLETE, step=3)
        else:
            patch["onboarding_complete"] = False
            patch["onboarding_updated_at"] = datetime.utcnow().isoformat()
            self.session_service.update_onboarding(session.id, OnboardingStatus.IN_PROGRESS, step=1)

        if patch:
            try:
                self.agent_service.update_agent(agent.id, patch)
            except Exception:
                logger.exception("Failed to update agent onboarding prefs", extra={"agent_id": agent.id})

    async def _llm_extract_onboarding_prefs(
        self,
        *,
        user_text: str,
        last_assistant_text: str,
        model: Optional[str],
    ) -> Dict[str, Optional[str]]:
        prompt = (
            "Extract onboarding preferences from the user message. "
            "Return JSON only with keys: user_preferred_name, agent_name_preference, agent_purpose, tone_preference, profanity_level, confidence. "
            "confidence must be an object with the same keys and 0..1 numeric scores. "
            "profanity_level must be one of: none, light, allowed, or null. "
            "Use null when uncertain."
        )
        try:
            raw = await self.model_service.chat_messages(
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Assistant message:\n{last_assistant_text}\n\n"
                            f"User message:\n{user_text}\n"
                        ),
                    },
                ],
                model=model,
            )
            parsed, confidences = parse_llm_onboarding_json_with_confidence(raw)
            gated: Dict[str, Optional[str]] = {}
            for key, value in parsed.items():
                if not value:
                    gated[key] = None
                    continue
                score = float(confidences.get(key, 0.0))
                gated[key] = value if score >= LLM_ONBOARDING_CONFIDENCE_THRESHOLD else None
            return gated
        except Exception:
            return {
                "user_preferred_name": None,
                "agent_name_preference": None,
                "agent_purpose": None,
                "tone_preference": None,
                "profanity_level": None,
            }

    async def _enforce_first_person(self, text: str, *, model: Optional[str]) -> str:
        if "this agent" not in (text or "").lower():
            return text
        try:
            rewritten = await self.model_service.chat_messages(
                messages=[
                    {
                        "role": "system",
                        "content": "Rewrite in first person. Replace any third-person self-reference ('this agent') with 'I/me'.",
                    },
                    {"role": "user", "content": text},
                ],
                model=model,
            )
            if rewritten and "this agent" not in rewritten.lower():
                return rewritten
        except Exception:
            pass
        return text.replace("this agent", "I").replace("This agent", "I")

    @staticmethod
    def _has_onboarding_value(payload: Dict[str, Optional[str]]) -> bool:
        return bool(
            payload.get("user_preferred_name")
            or payload.get("agent_name_preference")
            or payload.get("agent_purpose")
            or payload.get("tone_preference")
            or payload.get("profanity_level")
        )

    @staticmethod
    def _normalize_profanity_level(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = str(value).strip().lower()
        aliases = {
            "no": "none",
            "none": "none",
            "clean": "none",
            "light": "light",
            "some": "light",
            "mild": "light",
            "allowed": "allowed",
            "yes": "allowed",
            "full": "allowed",
            "profanity_ok": "allowed",
        }
        return aliases.get(normalized)

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

    @staticmethod
    def _resolve_style_lines(agent: AgentRecord) -> List[str]:
        profile = agent.profile_json if isinstance(agent.profile_json, dict) else {}
        tone = str(profile.get("tone_preference") or "neutral").strip()
        profanity = str(profile.get("profanity_level") or "light").strip().lower()
        if profanity not in {"none", "light", "allowed"}:
            profanity = "light"
        profanity_rule = {
            "none": "No profanity.",
            "light": "Light profanity is acceptable when user tone indicates it.",
            "allowed": "Profanity is allowed when user requests it; never use harassment or hate speech.",
        }[profanity]
        return [
            f"Tone preference: {tone}",
            f"Profanity level: {profanity}",
            profanity_rule,
            "Never force 'respectful/professional' admonitions when the user is casually swearing.",
            "Never claim an operational identity or real-world persona.",
        ]

    async def _enforce_output_guardrails(self, text: str, *, model: Optional[str]) -> str:
        normalized = (text or "").strip()
        lowered = normalized.lower()
        if not normalized:
            return normalized
        if not any(phrase in lowered for phrase in RESPONSE_META_BANLIST):
            return normalized
        try:
            rewritten = await self.model_service.chat_messages(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Rewrite naturally in first person. Remove meta identity claims, "
                            "remove 'as an AI/language model/operational identity' phrasing, "
                            "and remove scripted tone-policing lines like 'keep it respectful/clean'. "
                            "Keep the same intent and constraints."
                        ),
                    },
                    {"role": "user", "content": normalized},
                ],
                model=model,
            )
            candidate = (rewritten or "").strip()
            if candidate and not any(phrase in candidate.lower() for phrase in RESPONSE_META_BANLIST):
                return candidate
        except Exception:
            pass
        fallback = normalized.replace("operational identity", "name")
        fallback = fallback.replace("As an AI", "").replace("as an AI", "")
        fallback = fallback.replace("language model", "assistant")
        return fallback.strip()

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
