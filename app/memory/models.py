"""
Memory database models for Teiken Claw.

This module defines the database schema for the memory system, including:
- Session management
- Thread tracking
- Message persistence
- Memory records with audit trails
- Embedding storage
- Control state management
- Idempotency keys
- Application events
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, 
    Boolean, Float, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Session(Base):
    """Session model for tracking conversation sessions."""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    mode = Column(String(50), nullable=False, default="default")
    metadata = Column(JSON, nullable=True)
    
    # Relationships
    threads = relationship("Thread", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Session(id={self.id}, chat_id={self.chat_id}, mode={self.mode})>"


class Thread(Base):
    """Thread model for tracking conversation threads within sessions."""
    __tablename__ = "threads"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    summary = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    # Relationships
    session = relationship("Session", back_populates="threads")
    messages = relationship("SessionMessage", back_populates="thread", cascade="all, delete-orphan")
    summaries = relationship("ThreadSummary", back_populates="thread", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Thread(id={self.id}, session_id={self.session_id})>"


class SessionMessage(Base):
    """Model for storing individual messages within threads."""
    __tablename__ = "session_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata = Column(JSON, nullable=True)
    
    # Relationships
    thread = relationship("Thread", back_populates="messages")
    
    def __repr__(self) -> str:
        return f"<SessionMessage(id={self.id}, thread_id={self.thread_id}, role={self.role})>"


class ThreadSummary(Base):
    """Model for storing thread summaries."""
    __tablename__ = "thread_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    version = Column(Integer, nullable=False, default=1)
    
    # Relationships
    thread = relationship("Thread", back_populates="summaries")
    
    def __repr__(self) -> str:
        return f"<ThreadSummary(id={self.id}, thread_id={self.thread_id}, version={self.version})>"


class MemoryRecord(Base):
    """Model for storing memory records."""
    __tablename__ = "memory_records"
    
    id = Column(Integer, primary_key=True, index=True)
    memory_type = Column(String(50), nullable=False, index=True)  # "preference", "project", "workflow", etc.
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)  # List of tags
    scope = Column(String(50), nullable=False, index=True)  # "user", "global", "session"
    confidence = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    audits = relationship("MemoryAudit", back_populates="memory", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<MemoryRecord(id={self.id}, type={self.memory_type}, scope={self.scope})>"


class MemoryAudit(Base):
    """Model for tracking memory record changes."""
    __tablename__ = "memory_audits"
    
    id = Column(Integer, primary_key=True, index=True)
    memory_id = Column(Integer, ForeignKey("memory_records.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # "created", "updated", "deleted", "reviewed"
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    memory = relationship("MemoryRecord", back_populates="audits")
    
    def __repr__(self) -> str:
        return f"<MemoryAudit(id={self.id}, memory_id={self.memory_id}, action={self.action})>"


class EmbeddingRecord(Base):
    """Model for storing embeddings."""
    __tablename__ = "embedding_records"
    
    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), nullable=False, index=True)  # "memory", "message", "document"
    source_id = Column(Integer, nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hash of content
    embedding_model = Column(String(100), nullable=False)
    vector_dim = Column(Integer, nullable=False)
    embedding = Column(JSON, nullable=False)  # List of floats
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "embedding_model", name="uq_source_embedding"),
    )
    
    def __repr__(self) -> str:
        return f"<EmbeddingRecord(id={self.id}, source_type={self.source_type}, source_id={self.source_id})>"


class ControlState(Base):
    """Model for storing control state and configuration."""
    __tablename__ = "control_states"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<ControlState(key={self.key})>"


class IdempotencyKey(Base):
    """Model for handling idempotency keys."""
    __tablename__ = "idempotency_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    def __repr__(self) -> str:
        return f"<IdempotencyKey(key={self.key})>"


class AppEvent(Base):
    """Model for storing application events."""
    __tablename__ = "app_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    event_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<AppEvent(id={self.id}, type={self.event_type})>"