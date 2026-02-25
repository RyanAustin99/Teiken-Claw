"""
Database module for Teiken Claw.

This module provides:
- SQLAlchemy async engine and base
- Session factory and dependency injection
- SQLite PRAGMA configuration
- Core database models
- Database initialization utilities
"""

from app.db.base import (
    Base,
    create_engine,
    get_engine,
    dispose_engine,
    get_database_url,
)

from app.db.session import (
    get_db,
    get_db_context,
    create_session,
    get_session_factory,
)

from app.db.pragmas import (
    SQLITE_PRAGMAS,
    apply_pragmas,
    verify_pragmas,
    apply_pragmas_on_connect,
    checkpoint_wal,
    get_wal_checkpoint_command,
)

from app.db.models import (
    Session,
    Thread,
    SessionMessage,
    ThreadSummary,
    MemoryRecord,
    MemoryAudit,
    EmbeddingRecord,
    JobDeadLetter,
    SchedulerJobMeta,
    SchedulerJobRun,
    ToolAudit,
    SubagentRun,
    ControlState,
    IdempotencyKey,
    AppEvent,
    ALL_MODELS,
)

from app.db.init_db import (
    init_db,
    verify_db,
    reset_db,
    create_tables,
    create_fts5_tables,
    seed_control_states,
    DEFAULT_CONTROL_STATES,
)


__all__ = [
    # Base and engine
    "Base",
    "create_engine",
    "get_engine",
    "dispose_engine",
    "get_database_url",
    
    # Session management
    "get_db",
    "get_db_context",
    "create_session",
    "get_session_factory",
    
    # PRAGMAs
    "SQLITE_PRAGMAS",
    "apply_pragmas",
    "verify_pragmas",
    "apply_pragmas_on_connect",
    "checkpoint_wal",
    "get_wal_checkpoint_command",
    
    # Models
    "Session",
    "Thread",
    "SessionMessage",
    "ThreadSummary",
    "MemoryRecord",
    "MemoryAudit",
    "EmbeddingRecord",
    "JobDeadLetter",
    "SchedulerJobMeta",
    "SchedulerJobRun",
    "ToolAudit",
    "SubagentRun",
    "ControlState",
    "IdempotencyKey",
    "AppEvent",
    "ALL_MODELS",
    
    # Initialization
    "init_db",
    "verify_db",
    "reset_db",
    "create_tables",
    "create_fts5_tables",
    "seed_control_states",
    "DEFAULT_CONTROL_STATES",
]
