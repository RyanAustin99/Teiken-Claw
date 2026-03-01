"""
Memory v1.5 audit persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session as SQLAlchemySession

from app.db.base import Base
from app.db.session import get_db_session
from app.memory.models import MemoryAuditEvent


class MemoryAuditStore:
    """Persist memory audit events."""

    def __init__(self, session: Optional[SQLAlchemySession] = None):
        self._session = session or get_db_session()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            bind = self._session.get_bind()
            if bind is None:
                return
            inspector = sa_inspect(bind)
            if "memory_audit_events" not in set(inspector.get_table_names()):
                Base.metadata.create_all(bind=bind)
        except Exception:
            self._session.rollback()

    def log_event(
        self,
        *,
        thread_id: Optional[int],
        agent_id: Optional[str],
        source_message_id: Optional[int],
        op: str,
        memory_id: Optional[int],
        category: Optional[str],
        key: Optional[str],
        status: str,
        reason_code: Optional[str] = None,
        details_json: Optional[Dict[str, Any]] = None,
    ) -> MemoryAuditEvent:
        event = MemoryAuditEvent(
            ts=datetime.utcnow(),
            thread_id=thread_id,
            agent_id=agent_id,
            source_message_id=source_message_id,
            op=op,
            memory_id=memory_id,
            category=category,
            key=key,
            status=status,
            reason_code=reason_code,
            details_json=details_json or {},
        )
        self._session.add(event)
        self._session.commit()
        self._session.refresh(event)
        return event
