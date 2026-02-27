"""Fresh hatch boot generation and onboarding bootstrap persistence."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.agent.boot_linter import lint_boot_message
from app.config.logging import get_logger
from app.config.settings import settings
from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentOnboardingState, OnboardingStatus
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.session_service import SessionService
from app.interfaces.tc_profile_strip import extract_tc_profile
from app.memory.store import MemoryStore, get_memory_store
from app.soul.boot_policy import get_boot_directives

logger = get_logger(__name__)


FRESH_BOOT_SYSTEM_BLOCK = """
You are speaking directly to the user. Speak in first person ("I/me").
Never say: "this agent", "as an AI", "language model", "system prompt", or anything meta about prompts/instructions.
Your first message must feel natural and human, not scripted.
Do not use headings, numbered lists, bullet points, or questionnaire formatting.
Ask at most 1-2 short questions total. Prefer combining related questions into one sentence.
You must learn: what to call the user, and what they want to call you. If it fits naturally, also ask what your purpose should be.
Match the user's tone as it appears; if unknown, be calm, direct, and friendly.
""".strip()

OUTPUT_FORMAT_BLOCK = """
Output must start with: <tc_profile>{JSON}</tc_profile>
JSON must be valid and match:
{
  "agent_display_name": "string",
  "agent_voice": ["string", "string"],
  "agent_principles": ["string", "string", "string"],
  "onboarding_intent": {
    "ask_user_name": true,
    "ask_agent_name": true,
    "ask_purpose": true,
    "ask_tone": false
  }
}
After </tc_profile>, output a blank line and then the user-visible message only.
""".strip()


class HatchBootService:
    """Generates proactive first message for newly hatched agents."""

    def __init__(
        self,
        model_service: ModelService,
        agent_service: AgentService,
        session_service: SessionService,
        memory_store: Optional[MemoryStore] = None,
    ) -> None:
        self.model_service = model_service
        self.agent_service = agent_service
        self.session_service = session_service
        self.memory_store = memory_store or get_memory_store()

    async def run_boot(
        self,
        *,
        agent_id: str,
        session_id: str,
        user_metadata: Optional[Dict[str, str]] = None,
        overwrite_profile: bool = True,
    ) -> str:
        agent = self.agent_service.get_agent(agent_id)
        if not agent:
            raise ValidationError("Unknown agent for hatch boot", details={"agent_id": agent_id})
        session = self.session_service.get_session(session_id)
        if not session:
            raise ValidationError("Unknown session for hatch boot", details={"session_id": session_id})

        logger.info(
            "Boot generation started",
            extra={"event": "boot_generation_started", "agent_id": agent.id, "session_id": session.id},
        )

        profile_payload: Optional[Dict[str, Any]] = None
        visible_message = ""
        last_error: Optional[str] = None
        generation_attempts = 2

        for attempt in range(1, generation_attempts + 1):
            raw = await self.model_service.chat_messages(
                messages=self._build_boot_messages(agent=agent, user_metadata=user_metadata),
                model=agent.model,
            )
            parsed_profile, stripped, parse_error = extract_tc_profile(raw)
            if parse_error:
                last_error = parse_error
                logger.warning(
                    "Boot profile parse failed",
                    extra={
                        "event": "boot_profile_parse_failed",
                        "agent_id": agent.id,
                        "attempt": attempt,
                        "error": parse_error,
                    },
                )
            if parsed_profile:
                profile_payload = parsed_profile
                logger.info(
                    "Boot profile parsed",
                    extra={
                        "event": "boot_profile_parsed",
                        "agent_id": agent.id,
                        "keys": sorted(parsed_profile.keys()),
                    },
                )
            visible_message = stripped.strip()
            if profile_payload and visible_message:
                break

        if not profile_payload:
            if not overwrite_profile and isinstance(agent.profile_json, dict):
                profile_payload = dict(agent.profile_json)
            else:
                self._mark_degraded(agent.id, reason=last_error or "boot profile missing")
                raise ValidationError("Boot profile generation failed", details={"agent_id": agent.id, "error": last_error})

        lint_problems = lint_boot_message(visible_message, settings)
        if lint_problems:
            logger.warning(
                "Boot lint failed",
                extra={"event": "boot_lint_failed", "agent_id": agent.id, "problems": lint_problems},
            )
            retry_budget = max(0, int(getattr(settings, "TC_BOOT_RETRY_ON_LINT_FAIL", 1) or 0))
            if retry_budget > 0:
                logger.info(
                    "Boot rewrite attempt",
                    extra={"event": "boot_rewrite_attempt", "agent_id": agent.id, "attempt": 1},
                )
                rewritten = await self._rewrite_boot_message(agent_id=agent.id, model=agent.model, previous=visible_message)
                rewritten = rewritten.strip()
                rewritten_problems = lint_boot_message(rewritten, settings)
                if not rewritten_problems:
                    visible_message = rewritten
                    lint_problems = []
                else:
                    lint_problems = rewritten_problems
                    logger.warning(
                        "Boot rewrite lint failed",
                        extra={"event": "boot_lint_failed", "agent_id": agent.id, "problems": lint_problems},
                    )

        if lint_problems or not visible_message:
            reason = "; ".join(lint_problems) if lint_problems else "empty boot message"
            self._mark_degraded(agent.id, reason=reason)
            raise ValidationError("Boot message failed lint", details={"agent_id": agent.id, "problems": lint_problems})

        persisted_profile = profile_payload if overwrite_profile or not agent.profile_json else dict(agent.profile_json)
        if overwrite_profile or not agent.profile_json:
            self._persist_boot_identity(agent_id=agent.id, profile=persisted_profile)

        self.agent_service.update_agent(
            agent.id,
            {
                "profile_json": persisted_profile,
                "is_fresh": True,
                "onboarding_state": AgentOnboardingState.WAITING_USER_PREFS,
                "degraded_reason": None,
            },
        )
        self.session_service.append_assistant_message(session.id, visible_message)
        self.session_service.update_onboarding(session.id, status=OnboardingStatus.IN_PROGRESS, step=1)

        logger.info(
            "Boot completed",
            extra={
                "event": "boot_completed",
                "agent_id": agent.id,
                "session_id": session.id,
                "words": len([w for w in visible_message.split() if w]),
                "questions": visible_message.count("?"),
            },
        )
        return visible_message

    def _persist_boot_identity(self, *, agent_id: str, profile: Dict[str, Any]) -> None:
        identity = {
            "agent_display_name": profile.get("agent_display_name"),
            "agent_voice": profile.get("agent_voice") or [],
            "agent_principles": profile.get("agent_principles") or [],
        }
        self.memory_store.create_memory(
            memory_type="semantic",
            content=json.dumps(identity, ensure_ascii=False),
            scope=f"agent:{agent_id}",
            source="BOOT",
            key="identity",
            confidence=1.0,
            metadata={"scope": "AGENT_SELF"},
        )

    async def _rewrite_boot_message(self, *, agent_id: str, model: Optional[str], previous: str) -> str:
        prompt = (
            "Rewrite this opening message naturally. "
            "Constraints: first person only, no lists/headings, no forbidden meta phrasing, "
            f"max {settings.TC_BOOT_MAX_WORDS} words, max {settings.TC_BOOT_MAX_QUESTIONS} question marks."
        )
        return await self.model_service.chat_messages(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": previous},
            ],
            model=model,
        )

    def _build_boot_messages(self, *, agent: Any, user_metadata: Optional[Dict[str, str]]) -> list[dict[str, str]]:
        directives = get_boot_directives(agent, settings)
        personalization = ""
        if user_metadata:
            username = (user_metadata.get("username") or "").strip()
            display_name = (user_metadata.get("display_name") or "").strip()
            if username or display_name:
                personalization = (
                    "Known user metadata: "
                    f"username={username or 'unknown'}, display_name={display_name or 'unknown'}."
                )
        return [
            {"role": "system", "content": FRESH_BOOT_SYSTEM_BLOCK},
            {"role": "system", "content": directives},
            {"role": "system", "content": OUTPUT_FORMAT_BLOCK},
            {
                "role": "user",
                "content": (
                    "You've just been hatched. Send your first message to the user now."
                    + (f"\n{personalization}" if personalization else "")
                ),
            },
        ]

    def _mark_degraded(self, agent_id: str, *, reason: str) -> None:
        try:
            self.agent_service.update_agent(
                agent_id,
                {
                    "degraded_reason": reason,
                    "status": "degraded",
                },
            )
        except Exception:
            logger.exception("Failed to mark agent degraded", extra={"agent_id": agent_id, "reason": reason})


__all__ = [
    "HatchBootService",
    "FRESH_BOOT_SYSTEM_BLOCK",
    "OUTPUT_FORMAT_BLOCK",
]
