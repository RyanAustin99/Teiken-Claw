"""Session persistence service."""

from __future__ import annotations

from typing import List, Optional

from app.control_plane.domain.models import OnboardingStatus, SessionMessageRecord, SessionRecord
from app.control_plane.infra.session_repo import SessionRepository
from app.tools.protocol import ToolResultEnvelope, extract_tool_results


class SessionService:
    """Manage chat sessions and transcript persistence."""

    def __init__(self, repo: SessionRepository) -> None:
        self.repo = repo

    def new_session(self, agent_id: str, title: Optional[str] = None) -> SessionRecord:
        return self.repo.new_session(agent_id=agent_id, title=title)

    def list_sessions(self, agent_id: str, limit: int = 50) -> List[SessionRecord]:
        return self.repo.list_sessions(agent_id=agent_id, limit=limit)

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        return self.repo.get_session(session_id)

    def rename_session(self, session_id: str, title: str) -> Optional[SessionRecord]:
        return self.repo.rename_session(session_id=session_id, title=title)

    def update_onboarding(self, session_id: str, status: OnboardingStatus, step: int) -> Optional[SessionRecord]:
        return self.repo.update_onboarding(session_id=session_id, status=status, step=step)

    def delete_session(self, session_id: str) -> bool:
        return self.repo.delete_session(session_id=session_id)

    def delete_sessions_for_agent(self, agent_id: str) -> int:
        return self.repo.delete_sessions_for_agent(agent_id=agent_id)

    def append_user_message(self, session_id: str, content: str) -> SessionMessageRecord:
        return self.repo.append_message(session_id=session_id, role="user", content=content)

    def append_assistant_message(
        self,
        session_id: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_ok: Optional[bool] = None,
        tool_elapsed_ms: Optional[int] = None,
    ) -> SessionMessageRecord:
        return self.repo.append_message(
            session_id=session_id,
            role="assistant",
            content=content,
            tool_name=tool_name,
            tool_ok=tool_ok,
            tool_elapsed_ms=tool_elapsed_ms,
        )

    def get_transcript(self, session_id: str) -> List[SessionMessageRecord]:
        return self.repo.list_messages(session_id=session_id)

    def get_tool_receipts(self, session_id: str, limit: int = 20) -> List[ToolResultEnvelope]:
        receipts: List[ToolResultEnvelope] = []
        for message in self.repo.list_tool_messages(session_id=session_id, limit=limit):
            parsed = extract_tool_results(message.content)
            if parsed:
                receipts.extend(parsed)
                continue
            if message.tool_name:
                receipts.append(
                    ToolResultEnvelope(
                        id=f"msg-{message.id}",
                        tool=message.tool_name,
                        ok=bool(message.tool_ok),
                        result={"content": message.content} if message.tool_ok else None,
                        error={"type": "unknown", "message": message.content} if message.tool_ok is False else None,
                        elapsed_ms=message.tool_elapsed_ms or 0,
                    )
                )
        return receipts

