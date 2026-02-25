# Project File Structure

## Overview

This document describes the high-level folder structure and what belongs where in the Teiken Claw project.

---

## Root Directory

```
Teiken-Claw/
├── .env.example          # Environment variables template
├── .gitignore            # Git ignore rules
├── alembic.ini           # Alembic migration configuration
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # Contribution guidelines
├── README.md             # Project overview
├── requirements.txt      # Python dependencies
├── teiken_claw_spec.md   # Technical specification
├── teiken_claw_implementation_plan.md  # Implementation plan
└── alembic/              # Database migrations
```

---

## Core Directories

### `/app` - Application Source Code

Main application package containing all source code.

```
app/
├── __init__.py           # Package initialization
├── main.py               # FastAPI application entry point
├── config/               # Configuration modules
│   ├── __init__.py
│   ├── settings.py       # Environment settings
│   ├── logging.py        # Structured logging
│   └── constants.py      # Application constants
├── db/                   # Database layer
│   ├── __init__.py
│   ├── base.py           # SQLAlchemy base and engine
│   ├── session.py        # Session factory
│   ├── pragmas.py        # SQLite PRAGMAs
│   ├── models.py         # ORM models
│   └── init_db.py        # Database initialization
├── queue/                # Job queue system (Phase 2)
│   ├── __init__.py       # Package exports
│   ├── jobs.py           # Job model and priorities
│   ├── dispatcher.py     # Priority queue dispatcher
│   ├── workers.py        # Async worker pool
│   ├── locks.py          # Per-chat/session locks
│   ├── throttles.py      # Rate limiting & outbound queue
│   └── dead_letter.py    # Dead-letter queue management
├── agent/                # Core agent logic
│   └── __init__.py
├── interfaces/           # Interface adapters
│   └── __init__.py
├── memory/               # Memory system
│   └── __init__.py
├── observability/        # Monitoring and metrics
│   └── __init__.py
├── scheduler/            # Job scheduling
│   └── __init__.py
├── skills/               # Agent skills
│   └── __init__.py
├── soul/                 # Agent personality
│   └── __init__.py
├── subagents/            # Subagent management
│   └── __init__.py
└── tools/                # Tool implementations
    └── __init__.py
```

### `/alembic` - Database Migrations

Alembic migration scripts and configuration.

```
alembic/
├── env.py                # Alembic environment
├── script.py.mako        # Migration template
└── versions/             # Migration versions
    └── 001_initial.py    # Initial migration
```

### `/data` - Runtime Data

Application data storage (git-ignored).

```
data/
├── teiken_claw.db        # SQLite database
├── teiken_claw.db-wal    # WAL file
├── teiken_claw.db-shm    # Shared memory file
├── vault.key             # Encryption key
├── workspace/            # User workspace
└── activity_logs/        # Activity logs
```

### `/docs` - Documentation

Project documentation.

```
docs/
├── ADR-001-initial-architecture.md  # Architecture decision record
├── FILES.md             # This file
├── STATUS.md            # Project status
├── PHASE0_DELIVERY_REPORT.md  # Phase 0 report
├── PHASE1_DELIVERY_REPORT.md  # Phase 1 report
└── PHASE2_DELIVERY_REPORT.md  # Phase 2 report (to be created)
```

### `/logs` - Application Logs

Log files (git-ignored).

```
logs/
├── app.log              # Plain text logs
└── app.json.log         # JSON structured logs
```

### `/tests` - Test Suite

Unit and integration tests.

```
tests/
├── __init__.py
├── test_app.py          # Basic app tests
└── test_queue.py        # Queue system tests (Phase 2)
```

### `/.github` - GitHub Configuration

GitHub-specific configuration.

```
.github/
├── workflows/
│   └── ci.yml           # CI/CD workflow
├── ISSUE_TEMPLATE/
│   ├── bug_report.md
│   └── feature_request.md
└── PULL_REQUEST_TEMPLATE.md
```

---

## Queue System Files (Phase 2)

| File | Purpose |
|------|---------|
| `app/queue/jobs.py` | Job model, priorities, sources, types |
| `app/queue/dispatcher.py` | Priority queue with idempotency |
| `app/queue/workers.py` | Async worker pool |
| `app/queue/locks.py` | Per-chat and per-session locks |
| `app/queue/throttles.py` | Rate limiting and outbound queue |
| `app/queue/dead_letter.py` | Dead-letter queue management |

---

## File Naming Conventions

- **Python modules**: `snake_case.py`
- **Test files**: `test_*.py`
- **Configuration**: `*.ini`, `*.yaml`, `*.json`
- **Documentation**: `UPPERCASE.md` or `lowercase.md`
- **Migrations**: `NNN_description.py`

---

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI application entry point |
| `app/config/settings.py` | Environment configuration |
| `app/db/models.py` | Database models |
| `app/queue/jobs.py` | Job model and priorities |
| `app/queue/dispatcher.py` | Job queue dispatcher |
| `app/queue/workers.py` | Worker pool |
| `alembic/env.py` | Migration environment |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment template |

---

## Data Flow

```
Request → FastAPI (app/main.py)
        → Queue System (app/queue/)
            → Dispatcher → Workers → Handlers
        → Agent (app/agent/)
        → Tools (app/tools/)
        → Memory (app/memory/)
        → Database (app/db/)
```

---

## Queue Data Flow

```
Job Sources (Telegram, CLI, API, Scheduler, Subagent)
    │
    ▼
JobDispatcher (Priority Queue + Idempotency)
    │
    ▼
WorkerPool (Workers with Locks + Semaphores)
    │
    ├─→ Job Handlers → Processing
    │
    └─→ OutboundQueue → Rate Limiter → Telegram API
    │
    ▼
Dead-Letter Queue (Failed Jobs)
```

---

## Adding New Components

1. **New model**: Add to `app/db/models.py`, create migration
2. **New tool**: Add to `app/tools/`
3. **New interface**: Add to `app/interfaces/`
4. **New configuration**: Add to `app/config/settings.py`
5. **New constant**: Add to `app/config/constants.py`
6. **New job type**: Add to `app/queue/jobs.py`, register handler in workers
7. **New queue component**: Add to `app/queue/`

---

## Configuration Reference

### Queue Settings (app/config/settings.py)

| Setting | Default | Description |
|---------|---------|-------------|
| `QUEUE_MAX_SIZE` | 1000 | Maximum jobs in queue |
| `WORKER_COUNT` | 3 | Number of worker tasks |
| `OLLAMA_MAX_CONCURRENCY` | 2 | Max concurrent Ollama calls |
| `TELEGRAM_GLOBAL_MSG_PER_SEC` | 30.0 | Global Telegram rate limit |
| `TELEGRAM_PER_CHAT_MSG_PER_SEC` | 1.0 | Per-chat rate limit |
| `JOB_MAX_ATTEMPTS` | 3 | Max retry attempts |
| `LOCK_TIMEOUT_SEC` | 300 | Lock timeout in seconds |
| `IDEMPOTENCY_TTL_SEC` | 3600 | Idempotency key TTL |
