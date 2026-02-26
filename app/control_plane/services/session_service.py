"""Session persistence service."""

from __future__ import annotations

from typing import List, Optional

from app.control_plane.domain.models import SessionMessageRecord, SessionRecord
from app.control_plane.infra.session_repo import SessionRepository


class SessionService:
    """Manage chat sessions and transcript persistence."""

    def __init__(self, repo: SessionRepository) -> None:
        self.repo = repo

    def new_session(self, agent_id: str, title: Optional[str] = None) -> SessionRecord:
        return self.repo.new_session(agent_id=agent_id, title=title)

    def list_sessions(self, agent_id: str, limit: int = 50) -> List[SessionRecord]:
        return self.repo.list_sessions(agent_id=agent_id, limit=limit)

    def rename_session(self, session_id: str, title: str) -> Optional[SessionRecord]:
        return self.repo.rename_session(session_id=session_id, title=title)

    def delete_session(self, session_id: str) -> bool:
        return self.repo.delete_session(session_id=session_id)

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

