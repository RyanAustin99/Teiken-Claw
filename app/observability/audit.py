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
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import json
import uuid

from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import get_db_session
from app.config.settings import settings

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


class AppEvent(Base):
    """Database model for application events (audit log)."""
    __tablename__ = "app_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    details = Column(Text, nullable=True)
    session_id = Column(Integer, nullable=True, index=True)
    thread_id = Column(Integer, nullable=True, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    component = Column(String(100), nullable=True, index=True)
    trace_id = Column(String(36), nullable=True, index=True)
    
    __table_args__ = (
        Index("ix_app_events_type_timestamp", "event_type", "timestamp"),
        Index("ix_app_events_session_timestamp", "session_id", "timestamp"),
    )


class AuditLogger:
    """
    Audit logger for tracking system events.
    
    Provides structured logging of important system events to the database
    for auditing and debugging purposes.
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the audit logger.
        
        Args:
            enabled: Whether audit logging is enabled
        """
        self._enabled = enabled and settings.AUDIT_ENABLED
        logger.info(f"AuditLogger initialized (enabled={self._enabled})")
    
    @property
    def is_enabled(self) -> bool:
        """Check if audit logging is enabled."""
        return self._enabled
    
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
        """
        Log an audit event.
        
        Args:
            event_type: Type of the event
            details: Additional event details
            session_id: Associated session ID
            thread_id: Associated thread ID
            user_id: Associated user ID
            component: Component that generated the event
            trace_id: Distributed trace ID
            
        Returns:
            Event ID if logged, None if disabled
        """
        if not self._enabled:
            return None
        
        try:
            event_id = str(uuid.uuid4())
            
            # Serialize details to JSON
            details_json = None
            if details:
                details_json = json.dumps(details, default=str)
            
            # Create event record
            event = AppEvent(
                event_type=event_type.value,
                event_id=event_id,
                timestamp=datetime.utcnow(),
                details=details_json,
                session_id=session_id,
                thread_id=thread_id,
                user_id=user_id,
                component=component,
                trace_id=trace_id,
            )
            
            # Save to database
            with get_db_session() as db:
                db.add(event)
                db.commit()
            
            logger.debug(
                f"Audit event logged: {event_type.value}",
                extra={
                    "event_type": event_type.value,
                    "event_id": event_id,
                    "component": component,
                }
            )
            
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}", exc_info=True)
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
        """Log a tool call event."""
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
        """Log a sub-agent spawn event."""
        return self.log_event(
            event_type=AuditEventType.SUBAGENT_SPAWN,
            details={
                "subagent_type": subagent_type,
            },
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
        """Log a scheduler change event."""
        event_details = {"action": action}
        if job_id:
            event_details["job_id"] = job_id
        if details:
            event_details.update(details)
        
        return self.log_event(
            event_type=AuditEventType.SCHEDULER_CHANGE,
            details=event_details,
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
        """Log a memory write event."""
        return self.log_event(
            event_type=AuditEventType.MEMORY_WRITE,
            details={
                "memory_id": memory_id,
                "memory_type": memory_type,
            },
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
        """Log a memory delete event."""
        return self.log_event(
            event_type=AuditEventType.MEMORY_DELETE,
            details={
                "memory_id": memory_id,
                "reason": reason,
            },
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
        """Log a pause mode change event."""
        return self.log_event(
            event_type=AuditEventType.PAUSE_MODE_CHANGE,
            details={
                "paused": paused,
                "reason": reason,
            },
            user_id=user_id,
            component="control",
        )
    
    def log_job_queued(
        self,
        job_id: str,
        job_type: str,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """Log a job queued event."""
        return self.log_event(
            event_type=AuditEventType.JOB_QUEUED,
            details={
                "job_id": job_id,
                "job_type": job_type,
            },
            component="queue",
            trace_id=trace_id,
        )
    
    def log_job_completed(
        self,
        job_id: str,
        duration_ms: float,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """Log a job completed event."""
        return self.log_event(
            event_type=AuditEventType.JOB_COMPLETED,
            details={
                "job_id": job_id,
                "duration_ms": duration_ms,
            },
            component="queue",
            trace_id=trace_id,
        )
    
    def log_job_failed(
        self,
        job_id: str,
        error: str,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """Log a job failed event."""
        return self.log_event(
            event_type=AuditEventType.JOB_FAILED,
            details={
                "job_id": job_id,
                "error": error,
            },
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
        """
        Query audit events.
        
        Args:
            event_type: Filter by event type
            session_id: Filter by session ID
            limit: Maximum number of events to return
            offset: Number of events to skip
            
        Returns:
            List of event dictionaries
        """
        with get_db_session() as db:
            query = db.query(AppEvent)
            
            if event_type:
                query = query.filter(AppEvent.event_type == event_type.value)
            if session_id:
                query = query.filter(AppEvent.session_id == session_id)
            
            events = query.order_by(AppEvent.timestamp.desc()).offset(offset).limit(limit).all()
            
            return [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "details": json.loads(e.details) if e.details else None,
                    "session_id": e.session_id,
                    "thread_id": e.thread_id,
                    "user_id": e.user_id,
                    "component": e.component,
                    "trace_id": e.trace_id,
                }
                for e in events
            ]


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def set_audit_logger(logger: AuditLogger) -> None:
    """Set the global audit logger instance."""
    global _audit_logger
    _audit_logger = logger


__all__ = [
    "AuditLogger",
    "AuditEventType",
    "AppEvent",
    "get_audit_logger",
    "set_audit_logger",
]
