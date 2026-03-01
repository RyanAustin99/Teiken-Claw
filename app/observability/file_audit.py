"""Filesystem operation audit logging and runtime context propagation."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

from app.config.settings import settings
from app.db.models import FileOpAudit
from app.db.session import get_db_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileAuditContext:
    """Context attached to filesystem operations initiated by tool runtime."""

    agent_id: Optional[str] = None
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None


_RUNTIME_FILE_AUDIT_CONTEXT: ContextVar[Optional[FileAuditContext]] = ContextVar(
    "runtime_file_audit_context",
    default=None,
)


@contextmanager
def runtime_file_audit_context(context: Optional[FileAuditContext]):
    """Temporarily bind file-audit identity context for tool execution."""
    token = _RUNTIME_FILE_AUDIT_CONTEXT.set(context)
    try:
        yield
    finally:
        _RUNTIME_FILE_AUDIT_CONTEXT.reset(token)


def get_runtime_file_audit_context() -> Optional[FileAuditContext]:
    """Return runtime-bound file audit context if present."""
    return _RUNTIME_FILE_AUDIT_CONTEXT.get()


class FileAuditLogger:
    """Best-effort persistent logger for file operation events."""

    def __init__(self, enabled: bool = True):
        self._enabled = bool(enabled and settings.AUDIT_ENABLED)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def log_event(
        self,
        *,
        op: str,
        path_rel: Optional[str],
        status: str,
        bytes_in: int = 0,
        bytes_out: int = 0,
        error_code: Optional[str] = None,
        latency_ms: int = 0,
        agent_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        if not self._enabled:
            return

        runtime_ctx = get_runtime_file_audit_context()
        resolved_agent_id = str(agent_id) if agent_id is not None else (str(runtime_ctx.agent_id) if runtime_ctx and runtime_ctx.agent_id is not None else None)
        resolved_thread_id = str(thread_id) if thread_id is not None else (str(runtime_ctx.thread_id) if runtime_ctx and runtime_ctx.thread_id is not None else None)
        resolved_session_id = str(session_id) if session_id is not None else (str(runtime_ctx.session_id) if runtime_ctx and runtime_ctx.session_id is not None else None)
        resolved_correlation_id = correlation_id or (runtime_ctx.correlation_id if runtime_ctx else None)

        try:
            event = FileOpAudit(
                ts=datetime.now(UTC).replace(tzinfo=None),
                agent_id=resolved_agent_id,
                thread_id=resolved_thread_id,
                session_id=resolved_session_id,
                op=op,
                path_rel=path_rel or "",
                bytes_in=max(0, int(bytes_in)),
                bytes_out=max(0, int(bytes_out)),
                status=status,
                error_code=error_code,
                latency_ms=max(0, int(latency_ms)),
                correlation_id=resolved_correlation_id,
            )
            with get_db_session() as session:
                session.add(event)
                session.commit()
        except Exception:
            # Audit must never break tool execution.
            logger.debug("file audit persistence failed", exc_info=True)


_file_audit_logger: Optional[FileAuditLogger] = None


def get_file_audit_logger() -> FileAuditLogger:
    """Return global file audit logger instance."""
    global _file_audit_logger
    if _file_audit_logger is None:
        _file_audit_logger = FileAuditLogger()
    return _file_audit_logger


def set_file_audit_logger(logger_instance: FileAuditLogger) -> None:
    """Override global file audit logger instance."""
    global _file_audit_logger
    _file_audit_logger = logger_instance


__all__ = [
    "FileAuditContext",
    "FileAuditLogger",
    "runtime_file_audit_context",
    "get_runtime_file_audit_context",
    "get_file_audit_logger",
    "set_file_audit_logger",
]

