# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-25

### Added - Phase 1: DB + Config + Logging Foundation

#### Database (SQLAlchemy + SQLite)
- SQLAlchemy async engine with SQLite support
- WAL mode PRAGMAs for better concurrent performance
- Async session factory with dependency injection
- 15 core database models:
  - Session management: Session, Thread, SessionMessage, ThreadSummary
  - Memory system: MemoryRecord, MemoryAudit, EmbeddingRecord
  - Job queue: JobDeadLetter
  - Scheduler: SchedulerJobMeta, SchedulerJobRun
  - Audit: ToolAudit, SubagentRun
  - Control: ControlState, IdempotencyKey
  - Events: AppEvent
- FTS5 full-text search tables for messages and memory
- Database initialization with seed data

#### Alembic Migrations
- Alembic configuration for async migrations
- Initial migration with all tables and FTS5
- Migration template for future migrations

#### Logging System
- JSON structured logging with rotating file handler
- Console handler with color output
- Trace ID context management for request tracking
- Context variables for job_id, session_id, thread_id, component
- StructuredLogger with convenience methods

#### Configuration
- Enhanced settings with all required environment variables
- Application constants for job priorities, control states, etc.
- Updated .env.example with comprehensive documentation

#### Application
- Startup/shutdown lifecycle hooks
- Database initialization on startup
- Health check endpoints (/, /health, /health/ready, /health/live)
- CORS middleware configuration
- Global exception handler

#### Dependencies
- sqlalchemy[asyncio]>=2.0.0
- aiosqlite>=0.19.0
- alembic>=1.12.0
- pydantic-settings>=2.0.0
- python-dotenv>=1.0.0
- httpx>=0.25.0
- python-telegram-bot>=20.0
- ollama>=0.1.0

## [0.1.0] - 2026-02-25

### Added
- Initial project structure and repository setup
- FastAPI application skeleton with basic routes
- Pydantic settings configuration system
- Structured logging implementation
- Application constants and enums
- Virtual environment setup
- Core dependencies installation (FastAPI, Pydantic, Uvicorn)
- GitHub CI/CD workflow configuration
- Issue templates (bug report, feature request)
- Pull request template
- Contributing guidelines
- Environment variables template (.env.example)
- Comprehensive .gitignore for Python projects
- Project documentation (README, STATUS, FILES)
- All package directories with __init__.py files:
  - app/agent/
  - app/db/
  - app/interfaces/
  - app/memory/
  - app/observability/
  - app/queue/
  - app/scheduler/
  - app/skills/
  - app/soul/
  - app/subagents/
  - app/tools/
- Basic test structure

## [Unreleased]

### Added
- Phase 2: Memory & State Management (planned)
- Phase 3: Tool Integration (planned)
- Phase 4: Interface Layer (planned)
- Phase 5: Testing & Documentation (planned)
