"""
Audit logging for Teiken Claw.

This module provides audit event logging for tracking system events:
- Tool executions
- Sub-agent spawns
- Scheduler modifications
- Memory operations
- Pause mode changes
"""

import logging
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.db.models import AppEvent
from app.db.session import get_db_session

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events."""

    TOOL_CALL = "TOOL_CALL"
    SUBAGENT_SPAWN = "SUBAGENT_SPAWN"
    SCHEDULER_CHANGE = "SCHEDULER_CHANGE"
    MEMORY_WRITE = "MEMORY_WRITE"
    MEMORY_DELETE = "MEMORY_DELETE"
    PAUSE_MODE_CHANGE = "PAUSE_MODE_CHANGE"
    JOB_QUEUED = "JOB_QUEUED"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"


class AuditLogger:
    """
    Audit logger for tracking system events.

    Persists structured audit records where possible. If a compatible
    synchronous session context is not available, logging degrades safely.
    """

    def __init__(self, enabled: bool = True):
        self._enabled = enabled and settings.AUDIT_ENABLED
        logger.info(f"AuditLogger initialized (enabled={self._enabled})")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _with_session(self):
        """Return a sync context manager session if available, else None."""
        try:
            session_ctx = get_db_session()
        except Exception:
            return None

        # Sync context manager expected by this module.
        if hasattr(session_ctx, "__enter__") and hasattr(session_ctx, "__exit__"):
            return session_ctx
        return None

    def log_event(
        self,
        event_type: AuditEventType,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        user_id: Optional[str] = None,
        component: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self._enabled:
            return None

        event_id = str(uuid.uuid4())

        event_data = {
            "event_id": event_id,
            "details": details or {},
            "session_id": session_id,
            "thread_id": thread_id,
            "user_id": user_id,
            "component": component,
            "trace_id": trace_id,
        }

        session_ctx = self._with_session()
        if not session_ctx:
            logger.debug("Audit session context unavailable; event not persisted")
            return None

        try:
            event = AppEvent(
                event_type=event_type.value,
                event_data=event_data,
            )
            with session_ctx as db:
                db.add(event)
                db.commit()
            return event_id
        except Exception as exc:
            logger.error(f"Failed to log audit event: {exc}", exc_info=True)
            return None

    def log_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None,
        session_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.TOOL_CALL,
            details={
                "tool_name": tool_name,
                "success": success,
                "duration_ms": duration_ms,
                "error": error,
            },
            session_id=session_id,
            thread_id=thread_id,
            component="tools",
            trace_id=trace_id,
        )

    def log_subagent_spawn(
        self,
        subagent_type: str,
        session_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.SUBAGENT_SPAWN,
            details={"subagent_type": subagent_type},
            session_id=session_id,
            thread_id=thread_id,
            component="subagents",
            trace_id=trace_id,
        )

    def log_scheduler_change(
        self,
        action: str,
        job_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        payload = {"action": action}
        if job_id:
            payload["job_id"] = job_id
        if details:
            payload.update(details)
        return self.log_event(
            event_type=AuditEventType.SCHEDULER_CHANGE,
            details=payload,
            component="scheduler",
            trace_id=trace_id,
        )

    def log_memory_write(
        self,
        memory_id: int,
        memory_type: str,
        session_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.MEMORY_WRITE,
            details={"memory_id": memory_id, "memory_type": memory_type},
            session_id=session_id,
            component="memory",
            trace_id=trace_id,
        )

    def log_memory_delete(
        self,
        memory_id: int,
        reason: Optional[str] = None,
        session_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.MEMORY_DELETE,
            details={"memory_id": memory_id, "reason": reason},
            session_id=session_id,
            component="memory",
            trace_id=trace_id,
        )

    def log_pause_mode_change(
        self,
        paused: bool,
        reason: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.PAUSE_MODE_CHANGE,
            details={"paused": paused, "reason": reason},
            user_id=user_id,
            component="control",
        )

    def log_job_queued(
        self,
        job_id: str,
        job_type: str,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.JOB_QUEUED,
            details={"job_id": job_id, "job_type": job_type},
            component="queue",
            trace_id=trace_id,
        )

    def log_job_completed(
        self,
        job_id: str,
        duration_ms: float,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.JOB_COMPLETED,
            details={"job_id": job_id, "duration_ms": duration_ms},
            component="queue",
            trace_id=trace_id,
        )

    def log_job_failed(
        self,
        job_id: str,
        error: str,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        return self.log_event(
            event_type=AuditEventType.JOB_FAILED,
            details={"job_id": job_id, "error": error},
            component="queue",
            trace_id=trace_id,
        )

    def get_events(
        self,
        event_type: Optional[AuditEventType] = None,
        session_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        session_ctx = self._with_session()
        if not session_ctx:
            return []

        with session_ctx as db:
            query = db.query(AppEvent)

            if event_type:
                query = query.filter(AppEvent.event_type == event_type.value)

            if session_id is not None:
                query = query.filter(AppEvent.event_data["session_id"].as_integer() == session_id)

            events = query.order_by(AppEvent.created_at.desc()).offset(offset).limit(limit).all()

        records: list[Dict[str, Any]] = []
        for e in events:
            data = e.event_data or {}
            records.append(
                {
                    "event_id": data.get("event_id"),
                    "event_type": e.event_type,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "details": data.get("details"),
                    "session_id": data.get("session_id"),
                    "thread_id": data.get("thread_id"),
                    "user_id": data.get("user_id"),
                    "component": data.get("component"),
                    "trace_id": data.get("trace_id"),
                }
            )
        return records


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def set_audit_logger(logger_instance: AuditLogger) -> None:
    global _audit_logger
    _audit_logger = logger_instance


__all__ = [
    "AuditLogger",
    "AuditEventType",
    "AppEvent",
    "get_audit_logger",
    "set_audit_logger",
]
