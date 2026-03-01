"""
Core database models for Teiken Claw.

This module defines all SQLAlchemy ORM models for the application:
- Session management (Session, Thread, SessionMessage, ThreadSummary)
- Memory system (MemoryRecord, MemoryAudit, EmbeddingRecord)
- Job queue (JobDeadLetter)
- Scheduler (SchedulerJobMeta, SchedulerJobRun)
- Audit & observability (ToolAudit, SubagentRun)
- Control & idempotency (ControlState, IdempotencyKey)
- Events (AppEvent)
"""

from datetime import datetime
from typing import Optional, List
import json

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float,
    ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.sqlite import JSON

from app.db.base import Base


# =============================================================================
# Session Management Models
# =============================================================================

class Session(Base):
    """
    User session model for tracking conversation sessions.
    
    A session represents a single conversation with the AI agent,
    potentially spanning multiple threads.
    """
    __tablename__ = "sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(50), default="default", nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # Relationships
    threads: Mapped[List["Thread"]] = relationship(
        "Thread", back_populates="session", cascade="all, delete-orphan"
    )
    tool_audits: Mapped[List["ToolAudit"]] = relationship(
        "ToolAudit", back_populates="session"
    )
    subagent_runs: Mapped[List["SubagentRun"]] = relationship(
        "SubagentRun", back_populates="parent_session"
    )
    
    __table_args__ = (
        Index("ix_sessions_chat_id_created", "chat_id", "created_at"),
    )


class Thread(Base):
    """
    Conversation thread model.
    
    A thread represents a single conversation flow within a session.
    Each thread can have multiple messages and a summary.
    """
    __tablename__ = "threads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    public_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True, unique=True, index=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_mode: Mapped[str] = mapped_column(String(64), default="builder@1.5.0", nullable=False, index=True)
    active_soul: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    mode_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    topic_fingerprint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="threads")
    messages: Mapped[List["SessionMessage"]] = relationship(
        "SessionMessage", back_populates="thread", cascade="all, delete-orphan"
    )
    thread_summaries: Mapped[List["ThreadSummary"]] = relationship(
        "ThreadSummary", back_populates="thread", cascade="all, delete-orphan"
    )
    tool_audits: Mapped[List["ToolAudit"]] = relationship(
        "ToolAudit", back_populates="thread"
    )
    
    __table_args__ = (
        Index("ix_threads_session_id_created", "session_id", "created_at"),
    )


class SessionMessage(Base):
    """
    Individual message within a thread.
    
    Stores the conversation history with role (user/assistant/system)
    and content.
    """
    __tablename__ = "session_messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # Relationships
    thread: Mapped["Thread"] = relationship("Thread", back_populates="messages")
    
    __table_args__ = (
        Index("ix_session_messages_thread_id_created", "thread_id", "created_at"),
        CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_message_role"),
    )


class ThreadSummary(Base):
    """
    Summary of a conversation thread.
    
    Supports versioned summaries for long-running threads.
    """
    __tablename__ = "thread_summaries"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    thread: Mapped["Thread"] = relationship("Thread", back_populates="thread_summaries")
    
    __table_args__ = (
        Index("ix_thread_summaries_thread_id_version", "thread_id", "version"),
    )


# =============================================================================
# Memory System Models
# =============================================================================

class MemoryRecord(Base):
    """
    Memory record for the AI agent's long-term memory.
    
    Supports different memory types (episodic, semantic, procedural)
    with tags, scope, and confidence scoring.
    """
    __tablename__ = "memory_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    scope: Mapped[str] = mapped_column(String(50), default="global", nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="USER", nullable=False)
    key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    audits: Mapped[List["MemoryAudit"]] = relationship(
        "MemoryAudit", back_populates="memory", cascade="all, delete-orphan"
    )
    embeddings: Mapped[List["EmbeddingRecord"]] = relationship(
        "EmbeddingRecord", back_populates="memory"
    )
    
    __table_args__ = (
        Index("ix_memory_records_type_scope", "memory_type", "scope"),
        Index("ix_memory_records_scope_source", "scope", "source"),
        Index("ix_memory_records_created", "created_at"),
        CheckConstraint(
            "memory_type IN ('episodic', 'semantic', 'procedural', 'working')",
            name="ck_memory_type"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_confidence_range"),
    )


class MemoryAudit(Base):
    """
    Audit trail for memory operations.
    
    Tracks all changes to memory records for debugging and accountability.
    """
    __tablename__ = "memory_audits"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memory_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    memory: Mapped["MemoryRecord"] = relationship("MemoryRecord", back_populates="audits")
    
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete', 'archive', 'restore')",
            name="ck_audit_action"
        ),
    )


class MemoryItem(Base):
    """
    Thread-bound deterministic memory card.
    """

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(26), nullable=False, unique=True, index=True)
    thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("session_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_item_confidence_range"),
        Index("ix_memory_items_thread_category_key", "thread_id", "category", "key"),
    )


class MemoryAuditEvent(Base):
    """
    Audit trail for thread-bound memory operations.
    """

    __tablename__ = "memory_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("session_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    op: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    memory_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "op IN ('add', 'update', 'delete', 'pause', 'resume', 'blocked')",
            name="ck_memory_audit_event_op",
        ),
        CheckConstraint("status IN ('ok', 'blocked', 'error')", name="ck_memory_audit_event_status"),
        Index("ix_memory_audit_events_thread_ts", "thread_id", "ts"),
    )


class EmbeddingRecord(Base):
    """
    Embedding vector storage for semantic search.
    
    Stores embedding vectors for memory records and other content.
    """
    __tablename__ = "embedding_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Optional relationship to memory
    memory_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("memory_records.id", ondelete="SET NULL"), nullable=True
    )
    memory: Mapped[Optional["MemoryRecord"]] = relationship(
        "MemoryRecord", back_populates="embeddings"
    )
    
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "embedding_model", name="uq_embedding_source"),
        Index("ix_embedding_records_hash", "content_hash"),
    )


# =============================================================================
# Job Queue Models
# =============================================================================

class JobDeadLetter(Base):
    """
    Dead letter queue for failed jobs.
    
    Stores information about jobs that failed after maximum retries.
    """
    __tablename__ = "job_dead_letters"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_job_dead_letters_created", "created_at"),
    )


# =============================================================================
# Scheduler Models
# =============================================================================

class SchedulerJobMeta(Base):
    """
    Metadata for scheduled jobs.
    
    Stores job configuration and scheduling information.
    """
    __tablename__ = "scheduler_job_metas"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    runs: Mapped[List["SchedulerJobRun"]] = relationship(
        "SchedulerJobRun", back_populates="job_meta", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('interval', 'cron', 'date', 'once')",
            name="ck_trigger_type"
        ),
    )


class SchedulerJobRun(Base):
    """
    Execution history for scheduled jobs.
    
    Tracks each run of a scheduled job with status and timing.
    """
    __tablename__ = "scheduler_job_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("scheduler_job_metas.job_id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    job_meta: Mapped["SchedulerJobMeta"] = relationship("SchedulerJobMeta", back_populates="runs")
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_job_run_status"
        ),
        Index("ix_scheduler_job_runs_started", "started_at"),
    )


# =============================================================================
# Audit & Observability Models
# =============================================================================

class ToolAudit(Base):
    """
    Audit trail for tool executions.
    
    Tracks all tool invocations with arguments and results.
    """
    __tablename__ = "tool_audits"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    args: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="SET NULL"), nullable=True
    )
    
    # Relationships
    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="tool_audits")
    thread: Mapped[Optional["Thread"]] = relationship("Thread", back_populates="tool_audits")
    
    __table_args__ = (
        Index("ix_tool_audits_created", "created_at"),
        Index("ix_tool_audits_session_tool", "session_id", "tool_name"),
    )


class FileOpAudit(Base):
    """
    Audit trail for filesystem operations.

    Stores normalized workspace-relative paths and operation outcomes.
    """

    __tablename__ = "file_op_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    agent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    op: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    path_rel: Mapped[str] = mapped_column(String(2048), nullable=False)
    bytes_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    __table_args__ = (
        CheckConstraint("status IN ('success', 'failure')", name="ck_file_op_audit_status"),
        Index("ix_file_op_audits_ts", "ts"),
        Index("ix_file_op_audits_session_ts", "session_id", "ts"),
    )


class PersonaAuditEvent(Base):
    """
    Audit trail for soul/mode configuration changes.
    """

    __tablename__ = "persona_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    op: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    previous_value: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("scope_type IN ('thread', 'session', 'agent')", name="ck_persona_audit_scope"),
        CheckConstraint(
            "op IN ('soul_set', 'mode_set', 'mode_lock', 'mode_unlock')",
            name="ck_persona_audit_op",
        ),
        CheckConstraint("status IN ('ok', 'error')", name="ck_persona_audit_status"),
        Index("ix_persona_audit_scope_ts", "scope_type", "ts"),
    )


class SubagentRun(Base):
    """
    Subagent execution tracking.
    
    Records when subagents are spawned and their results.
    """
    __tablename__ = "subagent_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    parent_session: Mapped["Session"] = relationship("Session", back_populates="subagent_runs")
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_subagent_status"
        ),
    )


# =============================================================================
# Control & Idempotency Models
# =============================================================================

class ControlState(Base):
    """
    Application control state storage.
    
    Stores key-value pairs for application state management.
    """
    __tablename__ = "control_states"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    __table_args__ = (
        Index("ix_control_states_key", "key"),
    )


class IdempotencyKey(Base):
    """
    Idempotency key tracking for deduplication.
    
    Ensures operations are not duplicated within a time window.
    """
    __tablename__ = "idempotency_keys"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    __table_args__ = (
        Index("ix_idempotency_keys_expires", "expires_at"),
    )


# =============================================================================
# Event Models
# =============================================================================

class AppEvent(Base):
    """
    Application event log.
    
    Records significant application events for monitoring and analysis.
    """
    __tablename__ = "app_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_app_events_type_created", "event_type", "created_at"),
    )


# =============================================================================
# Model Registry
# =============================================================================

# All models for Alembic autogenerate support
ALL_MODELS = [
    Session,
    Thread,
    SessionMessage,
    ThreadSummary,
    MemoryRecord,
    MemoryAudit,
    MemoryItem,
    MemoryAuditEvent,
    EmbeddingRecord,
    JobDeadLetter,
    SchedulerJobMeta,
    SchedulerJobRun,
    ToolAudit,
    FileOpAudit,
    PersonaAuditEvent,
    SubagentRun,
    ControlState,
    IdempotencyKey,
    AppEvent,
]


# Export all models
__all__ = [
    "Session",
    "Thread",
    "SessionMessage",
    "ThreadSummary",
    "MemoryRecord",
    "MemoryAudit",
    "MemoryItem",
    "MemoryAuditEvent",
    "EmbeddingRecord",
    "JobDeadLetter",
    "SchedulerJobMeta",
    "SchedulerJobRun",
    "ToolAudit",
    "FileOpAudit",
    "PersonaAuditEvent",
    "SubagentRun",
    "ControlState",
    "IdempotencyKey",
    "AppEvent",
    "ALL_MODELS",
]
