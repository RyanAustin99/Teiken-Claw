"""
Session message persistence for Memory v1.5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as SQLAlchemySession

from app.db.session import get_db_session
from app.memory.models import SessionMessage


class MessageStore:
    """Store for thread transcript messages."""

    def __init__(self, session: Optional[SQLAlchemySession] = None):
        self._session = session or get_db_session()

    def append_message(
        self,
        thread_id: int,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        token_estimate: Optional[int] = None,
    ) -> SessionMessage:
        message = SessionMessage(
            thread_id=thread_id,
            role=role,
            content=content,
            metadata_=metadata or {},
            token_estimate=token_estimate,
            created_at=datetime.utcnow(),
        )
        self._session.add(message)
        self._session.commit()
        self._session.refresh(message)
        return message

    def get_recent_messages(self, thread_id: int, limit: int) -> List[SessionMessage]:
        rows = (
            self._session.query(SessionMessage)
            .filter(SessionMessage.thread_id == thread_id)
            .order_by(SessionMessage.created_at.desc(), SessionMessage.id.desc())
            .limit(max(1, limit))
            .all()
        )
        rows.reverse()
        return rows
