"""Persona audit logging persistence for soul/mode switches."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.config.logging import get_logger
from app.db.models import PersonaAuditEvent
from app.db.session import get_db_session

logger = get_logger(__name__)


class PersonaAuditLogger:
    def __init__(self, session=None) -> None:
        self._session = session or get_db_session()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Best-effort schema bootstrap for environments without migrations."""
        try:
            bind = self._session.get_bind()
            PersonaAuditEvent.__table__.create(bind=bind, checkfirst=True)
        except Exception:
            # Keep runtime resilient if schema management is external.
            logger.debug(
                "Persona audit schema bootstrap skipped",
                extra={"event": "persona_audit_schema_bootstrap_skipped"},
            )

    def log_event(
        self,
        *,
        scope_type: str,
        thread_id: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        op: str,
        previous_value: Optional[str],
        new_value: Optional[str],
        prompt_fingerprint: Optional[str] = None,
        status: str = "ok",
        reason_code: Optional[str] = None,
        details_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        row = PersonaAuditEvent(
            ts=datetime.utcnow(),
            scope_type=scope_type,
            thread_id=thread_id,
            session_id=session_id,
            agent_id=agent_id,
            op=op,
            previous_value=previous_value,
            new_value=new_value,
            prompt_fingerprint=prompt_fingerprint,
            status=status,
            reason_code=reason_code,
            details_json=details_json or {},
        )
        self._session.add(row)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            logger.warning(
                "Persona audit event write failed",
                extra={"event": "persona_audit_write_failed"},
            )


_persona_audit_logger: Optional[PersonaAuditLogger] = None


def get_persona_audit_logger() -> PersonaAuditLogger:
    global _persona_audit_logger
    if _persona_audit_logger is None:
        _persona_audit_logger = PersonaAuditLogger()
    return _persona_audit_logger


def set_persona_audit_logger(logger: PersonaAuditLogger) -> None:
    global _persona_audit_logger
    _persona_audit_logger = logger
