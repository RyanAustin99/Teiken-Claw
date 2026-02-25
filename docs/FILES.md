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
├── agent/                # Core agent logic
│   └── __init__.py
├── interfaces/           # Interface adapters
│   └── __init__.py
├── memory/               # Memory system
│   └── __init__.py
├── observability/        # Monitoring and metrics
│   └── __init__.py
├── queue/                # Job queue
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
└── PHASE0_DELIVERY_REPORT.md  # Phase 0 report
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
└── test_app.py          # Basic app tests
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
| `alembic/env.py` | Migration environment |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment template |

---

## Data Flow

```
Request → FastAPI (app/main.py)
        → Agent (app/agent/)
        → Tools (app/tools/)
        → Memory (app/memory/)
        → Database (app/db/)
```

---

## Adding New Components

1. **New model**: Add to `app/db/models.py`, create migration
2. **New tool**: Add to `app/tools/`
3. **New interface**: Add to `app/interfaces/`
4. **New configuration**: Add to `app/config/settings.py`
5. **New constant**: Add to `app/config/constants.py`
