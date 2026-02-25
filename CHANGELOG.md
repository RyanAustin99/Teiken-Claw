# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-25

### Added - Phase 2: Queue, Workers, Throttles, and Dead-Letter

#### Job Queue System
- `app/queue/jobs.py` - Job model with Pydantic validation
  - JobPriority enum (INTERACTIVE=10, SUBAGENT=20, SCHEDULED=30, MAINTENANCE=40)
  - JobSource enum (TELEGRAM, CLI, API, SCHEDULER, SUBAGENT, INTERNAL)
  - JobType enum (CHAT_MESSAGE, SCHEDULED_TASK, SUBAGENT_TASK, etc.)
  - create_job() factory function
  - Priority comparison operators for queue ordering

#### Priority Dispatcher
- `app/queue/dispatcher.py` - Priority-based job dispatcher
  - asyncio.PriorityQueue for job ordering
  - Idempotency key deduplication with TTL
  - Queue backpressure handling (max size)
  - Pending job tracking
  - Dead-letter queue integration
  - Graceful shutdown support

#### Worker Pool
- `app/queue/workers.py` - Async worker pool
  - Configurable number of workers
  - Ollama concurrency semaphore
  - Per-chat lock enforcement
  - Job handler registration
  - Worker status tracking
  - Graceful shutdown with timeout

#### Lock Management
- `app/queue/locks.py` - Per-chat and per-session locks
  - Async context managers for lock acquisition
  - Configurable lock timeout
  - Lock expiration tracking
  - Deadlock prevention via timeout

#### Rate Limiting & Outbound Queue
- `app/queue/throttles.py` - Rate limiting and outbound messaging
  - RateLimiter with aiolimiter (token bucket algorithm)
  - Global rate limiting (default: 30 msg/sec)
  - Per-chat rate limiting (default: 1 msg/sec per chat)
  - OutboundQueue for Telegram messages
  - Retry logic for 429 (rate limit) errors
  - Exponential backoff for transient errors
  - Dead-letter integration for failed messages

#### Dead-Letter Queue
- `app/queue/dead_letter.py` - Failed job management
  - Database persistence via JobDeadLetter model
  - List, get, replay, delete operations
  - Error type summary
  - Admin clear functionality

#### Configuration
- New queue settings in `app/config/settings.py`:
  - QUEUE_MAX_SIZE (default: 1000)
  - WORKER_COUNT (default: 3)
  - OLLAMA_MAX_CONCURRENCY (default: 2)
  - TELEGRAM_GLOBAL_MSG_PER_SEC (default: 30.0)
  - TELEGRAM_PER_CHAT_MSG_PER_SEC (default: 1.0)
  - JOB_MAX_ATTEMPTS (default: 3)
  - LOCK_TIMEOUT_SEC (default: 300)
  - IDEMPOTENCY_TTL_SEC (default: 3600)

#### Application Integration
- Updated `app/main.py` with queue lifecycle:
  - Initialize queue components on startup
  - Start workers and outbound sender
  - Stop gracefully on shutdown
  - Queue status in health check
  - New API endpoints:
    - GET /api/v1/queue/status
    - GET /api/v1/queue/dead-letter

#### Tests
- `tests/test_queue.py` - Comprehensive queue tests
  - Job model tests
  - Dispatcher tests (priority, idempotency, backpressure)
  - Lock manager tests
  - Worker pool tests
  - Rate limiter tests
  - Dead-letter queue tests
  - Integration tests

---

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
- aiolimiter>=1.0.0 (optional, for rate limiting)

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
- Phase 3: Core Agent Implementation (planned)
- Phase 4: Interface Layer (planned)
- Phase 5: Testing & Documentation (planned)
