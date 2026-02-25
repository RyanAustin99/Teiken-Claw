# Teiken Claw v1.0 Specification

## Overview

Teiken Claw is a production-grade local-first AI agent platform designed for Windows environments. It provides a Telegram interface for interacting with AI agents that can perform various tasks including web search, file operations, code execution, and scheduled automation.

## Core Architecture

### Technology Stack
- **Language**: Python 3.11+
- **Database**: SQLite with SQLAlchemy ORM
- **Queue System**: Async priority queue with worker pool
- **AI Integration**: Ollama for LLM and embeddings
- **Interface**: Telegram Bot API
- **Scheduling**: APScheduler
- **Configuration**: Pydantic settings with environment variables

### Directory Structure
```
Teiken-Claw/
├── app/
│   ├── config/
│   ├── db/
│   ├── queue/
│   ├── agent/
│   ├── interfaces/
│   ├── memory/
│   ├── tools/
│   ├── scheduler/
│   ├── skills/
│   ├── subagents/
│   ├── soul/
│   └── observability/
├── scripts/
├── tests/
├── docs/
├── logs/
├── .github/
├── .gitignore
├── .env.example
├── requirements.txt
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

## Phase 0 - Architecture Lock + Spec Baseline

### 0.1 Create spec docs
- Create `teiken_claw_spec.md` (copy of specification)
- Create `README.md` baseline
- Create `.env.example` with all required settings

### 0.2 Initialize repo + dependencies
- Create `requirements.txt` with all Python dependencies
- Create basic package structure
- Set up pre-commit/linting (optional)

### 0.3 Acceptance criteria
- Repo builds cleanly
- App imports without errors
- Config loads from environment
- GitHub structure complete

## Phase 1 - DB + Config + Logging Foundation

### 1.1 SQLAlchemy + SQLite setup
- Implement `app/db/base.py` (SQLAlchemy base + engine)
- Implement `app/db/session.py` (session factory)
- Implement `app/db/pragmas.py` (WAL mode PRAGMAs)
- Implement `app/db/models.py` (core models)
- Implement `app/db/init_db.py` (bootstrap)

### 1.2 Alembic setup
- Initialize Alembic
- Create baseline migration
- Add required core tables

### 1.3 Logging system
- Implement `app/config/logging.py` (structured JSON logging)
- Implement `app/config/settings.py` (Pydantic settings)
- Implement `app/config/constants.py`

### 1.4 Acceptance criteria
- DB initializes cleanly with WAL mode
- Migration runs successfully
- Logs structured with trace IDs
- Settings load from `.env`

## Phase 2 - Queue, Workers, Throttles, Dead-Letter

### 2.1 Job models + dispatcher
- Implement `app/queue/jobs.py` (Job model + priorities)
- Implement `app/queue/dispatcher.py` (PriorityQueue + idempotency)

### 2.2 Worker pool
- Implement `app/queue/workers.py` (async workers)
- Implement `app/queue/locks.py` (per-chat locks)

### 2.3 Telegram outbound queue + throttles
- Implement `app/queue/throttles.py` (global + per-chat limits)
- Implement `app/queue/dead_letter.py` (dead-letter queue)

### 2.4 Acceptance criteria
- Simulated burst of jobs processed without overlap
- Failed jobs move to dead-letter
- Outbound throttling works
- Queue backpressure prevents overload

## Phase 3 - Ollama Client + Retry + Circuit Breaker

### 3.1 Ollama client
- Implement `app/agent/ollama_client.py` (chat + embeddings)
- Implement timeout handling
- Implement response validation

### 3.2 Retry utilities
- Implement `app/agent/retries.py` (exponential backoff + jitter)
- Implement retry policies per operation type

### 3.3 Circuit breaker
- Implement `app/agent/circuit_breaker.py` (state machine)
- Implement failure thresholds
- Implement half-open probe logic

### 3.4 Acceptance criteria
- Mocked timeouts trigger retries
- Breaker opens after repeated failures
- Breaker blocks calls while open
- Ollama client handles all error cases gracefully

## Phase 4 - Core Agent Loop (No Real Tools Yet, Then Tool Calling)

### 4.1 Minimal loop
- Implement `app/agent/runtime.py` (core loop skeleton)
- Implement message persistence
- Implement context placeholder
- Implement Ollama response to text

### 4.2 Tool registry + base tool
- Implement `app/tools/base.py` (Tool interface)
- Implement `app/tools/registry.py` (tool registry)
- Implement `app/tools/policies.py` (tool policies)
- Implement `app/tools/validators.py` (arg validation)

### 4.3 Tool-calling loop
- Implement tool call parsing
- Implement argument validation
- Implement tool execution
- Implement tool result appending
- Implement loop continuation logic

### 4.4 Error handling
- Implement malformed args handling
- Implement tool error envelope
- Implement max tool turn guard
- Implement duplicate tool call detection

### 4.5 Acceptance criteria
- Mock tool call flow completes end-to-end
- Tool errors don't crash runtime
- Duplicate tool loops prevented
- Agent loop handles all error cases gracefully

## Phase 5 - Telegram Interface + Command System

### 5.1 Telegram bot bootstrap
- Implement `app/interfaces/telegram_bot.py` (async bot)
- Implement message handler -> inbound queue
- Implement typing indicators

### 5.2 Telegram sender worker
- Implement `app/interfaces/telegram_sender.py`
- Integrate with outbound queue
- Implement long message chunking
- Implement retry on 429/network errors

### 5.3 Command router
- Implement `app/interfaces/telegram_commands.py`
- Implement core commands: `/start`, `/help`, `/ping`, `/status`
- Implement mode commands: `/mode`, `/mode <name>`
- Implement thread commands: `/thread`, `/thread new`
- Implement pause commands: `/pause jobs`, `/pause all`, `/resume`
- Implement permission checks

### 5.4 Acceptance criteria
- Telegram messages go through queue, not directly
- Commands work and return responses
- Status shows real runtime data
- Permission system works correctly

## Phase 6 - Memory System (Deterministic + Review First)

### 6.1 Session + thread state
- Implement `app/memory/models.py` (SessionMessage, Thread, etc.)
- Implement `app/memory/store.py` (CRUD operations)
- Implement `app/memory/thread_state.py` (thread tracking)

### 6.2 Context routing (topic switching)
- Implement `app/agent/context_router.py` (topic detection)
- Implement explicit `/thread new` handling
- Implement similarity-based topic switch
- Implement thread metadata management

### 6.3 Deterministic memory extraction
- Implement `app/memory/extraction_rules.py` (filtering rules)
- Implement candidate filtering
- Implement category classification
- Implement blocked categories enforcement

### 6.4 Memory CRUD + review commands
- Implement `app/memory/review.py` (review commands)
- Implement `/memory review`, `/memory search`, `/memory forget`
- Implement auto-memory pause/resume
- Implement memory audit trail

### 6.5 Acceptance criteria
- Memories only store allowed categories
- User can review/delete memories
- Topic switches create separate threads
- Memory system handles all edge cases gracefully

## Phase 7 - LLM Memory Extraction + Embeddings + Hybrid Retrieval

### 7.1 LLM extractor
- Implement `app/memory/extractor_llm.py` (structured extraction)
- Implement JSON parsing
- Implement validation pipeline
- Implement confidence threshold enforcement

### 7.2 Dedupe
- Implement `app/memory/dedupe.py` (hash dedupe)
- Implement semantic dedupe hook
- Implement duplicate prevention

### 7.3 Embeddings integration
- Implement `app/memory/embeddings.py` (Ollama embeddings)
- Implement embeddings table
- Implement embed on memory save
- Implement model version tracking

### 7.4 Hybrid retrieval
- Implement `app/memory/retrieval.py` (FTS + semantic)
- Implement ranking merge
- Implement retrieval budget
- Implement context injection

### 7.5 Acceptance criteria
- Memory extraction outputs structured records
- Similar memories deduped
- Retrieval returns relevant memories
- Hybrid retrieval works correctly

## Phase 8 - Tool Implementations (Web, Files, Exec, Memory, Scheduler)

### 8.1 Web tool
- Implement `app/tools/web_tool.py` (search/fetch/extract)
- Implement timeouts and limits
- Implement domain policy support
- Implement response size limits

### 8.2 Files tool
- Implement `app/tools/files_tool.py` (sandboxed operations)
- Implement path traversal protection
- Implement file size guard
- Implement workspace sandbox enforcement

### 8.3 Exec tool (hardened)
- Implement `app/tools/exec_tool.py` (PowerShell/Python)
- Implement command allowlist
- Implement timeout + kill on overrun
- Implement admin-only enforcement
- Implement audit trail

### 8.4 Memory tool
- Implement `app/tools/memory_tool.py` (direct memory ops)
- Implement memory_remember, memory_search, etc.
- Implement permission checks
- Implement audit logging

### 8.5 Scheduler tool (stub)
- Implement `app/tools/scheduler_tool.py` (schemas)
- Implement integration points
- Implement permission checks

### 8.6 Acceptance criteria
- Tools usable from agent loop
- Exec tool denied for non-admin
- Files tool cannot escape sandbox
- All tools handle errors gracefully

## Phase 9 - Scheduler / Cron System (APScheduler + Control State)

### 9.1 APScheduler service
- Implement `app/scheduler/service.py` (startup/shutdown)
- Implement job store configuration
- Implement trigger parsing
- Implement job persistence

### 9.2 Scheduler execution bridge
- Implement `app/scheduler/executor.py` (job execution)
- Implement scheduled jobs enqueue inbound queue
- Implement run history tracking
- Implement retry logic

### 9.3 Control state / pause modes
- Implement `app/scheduler/control_state.py` (control_state table)
- Implement `/pause jobs`, `/pause all`, `/resume`
- Implement state persistence
- Implement state enforcement

### 9.4 Scheduler commands
- Implement `/jobs` command
- Implement list/pause/resume/delete/run-now
- Implement dead-letter integration
- Implement job history

### 9.5 Acceptance criteria
- Cron and interval jobs execute
- Pause mode blocks jobs immediately
- Failed jobs visible and replayable
- Scheduler handles all edge cases gracefully

## Phase 10 - Skills System

### 10.1 Skill schema + loader
- Implement `app/skills/schema.py` (YAML schema validation)
- Implement `app/skills/loader.py` (definitions loader)
- Implement skill file validation
- Implement version management

### 10.2 Skill engine
- Implement `app/skills/engine.py` (step execution)
- Implement skill context management
- Implement error handling
- Implement step type support

### 10.3 Skill router + commands
- Implement `app/skills/router.py` (intent matching)
- Implement `/skills` command (list available skills)
- Implement `/skill <name>` command (direct invocation)
- Implement trigger-based invocation

### 10.4 Built-in skills implementation
- Implement `create_job` skill
- Implement `summarize_files` skill
- Implement `run_study` skill
- Implement `debug_report` skill

### 10.5 Acceptance criteria
- Skills run end-to-end
- Skills can call tools
- `create_job` successfully schedules a job
- Skills handle all error cases gracefully

## Phase 11 - Sub-Agent System (MANDATORY)

### 11.1 Sub-agent models + policies
- Implement `app/subagents/models.py` (task/result/policy models)
- Implement `app/subagents/policies.py` (quotas and limits)
- Implement spawn depth limits
- Implement tool restrictions

### 11.2 Sub-agent manager + executor
- Implement `app/subagents/manager.py` (spawn management)
- Implement `app/subagents/executor.py` (child runtime)
- Implement parent-child linkage tracking
- Implement quota enforcement

### 11.3 Sub-agent summarizer
- Implement `app/subagents/summarizer.py` (result merging)
- Implement error/partial exposure
- Implement confidence scoring
- Implement artifact reference handling

### 11.4 Tool integration
- Implement `app/tools/subagent_tool.py` (spawn interface)
- Implement parent agent spawn capability
- Implement task specification
- Implement result handling

### 11.5 Acceptance criteria
- Parent agent spawns child successfully
- Child restricted to allowed tools
- Parent receives summarized result
- Infinite recursion blocked
- Sub-agent system handles all edge cases gracefully

## Phase 12 - Soul / Modes Polish + Context Quality

### 12.1 Soul loader and policy integration
- Implement `app/soul/loader.py` (load soul configs)
- Implement `app/soul/models.py` (Pydantic models)
- Implement `app/soul/policies.py` (behavior policies)
- Implement config merging

### 12.2 Mode commands
- Implement `/mode` command (list modes)
- Implement `/mode <name>` command (change mode)
- Implement thread mode persistence
- Implement mode behavior changes

### 12.3 Context builder polish
- Implement `app/agent/context_builder.py` (token budget)
- Implement thread summary integration
- Implement retrieval budget tuning
- Implement scheduler/tool state snapshots

### 12.4 Acceptance criteria
- Mode changes alter behavior consistently
- Architect mode produces structured outputs
- Context remains coherent across long chats
- Soul system handles all edge cases gracefully

## Phase 13 - Observability + Health + Admin APIs

### 13.1 Health endpoints
- Implement `app/api/routes_health.py` (`/health`)
- Implement `app/api/routes_status.py` (`/status`)
- Implement `app/api/routes_admin.py` (admin endpoints)
- Implement `app/api/schemas.py` (API schemas)

### 13.2 Audit logging
- Implement `app/observability/audit.py` (audit events)
- Implement tool audit logging
- Implement scheduler audit logging
- Implement memory audit logging
- Implement sub-agent audit logging

### 13.3 Admin endpoints
- Implement pause/resume endpoints
- Implement dead-letter inspect/replay
- Implement system status
- Implement metrics endpoints

### 13.4 Acceptance criteria
- Health endpoint reflects real component status
- Audit records queryable
- Status command mirrors API status
- Admin endpoints work correctly

## Phase 14 - Windows PowerShell Ops + Service Hardening

### 14.1 `scripts/setup.ps1`
- Implement environment checks
- Implement dependency installation
- Implement DB initialization
- Implement smoke test

### 14.2 `scripts/run_dev.ps1`
- Implement dev runner
- Implement log clearing option
- Implement venv activation

### 14.3 `scripts/install_service.ps1`
- Implement Windows Task Scheduler registration
- Implement startup task creation
- Implement restart on failure
- Implement validation

### 14.4 `scripts/backup.ps1`, `scripts/reset_db.ps1`, `scripts/smoke_test.ps1`
- Implement backup functionality
- Implement safe reset
- Implement smoke test
- Implement validation

### 14.5 Acceptance criteria
- Fresh machine setup works via PowerShell scripts
- Startup task registers successfully
- Smoke tests pass
- All scripts handle errors gracefully

## Phase 15 - Test Coverage + Failure Drills + Release Hardening

### 15.1 Unit + integration + e2e coverage
- Implement unit tests for all modules
- Implement integration tests
- Implement e2e tests
- Implement test fixtures

### 15.2 Failure simulation drills
- Implement Ollama failure simulation
- Implement Telegram failure simulation
- Implement tool failure simulation
- Implement queue failure simulation

### 15.3 Security review
- Implement security audit
- Implement permission validation
- Implement input sanitization
- Implement audit trail validation

### 15.4 Performance tuning
- Implement performance benchmarks
- Implement load testing
- Implement memory usage optimization
- Implement concurrency optimization

### 15.5 Release checklist
- Implement release validation
- Implement documentation update
- Implement changelog generation
- Implement final testing

### Acceptance criteria
- End-to-end scenarios pass
- Failure modes degrade gracefully
- Logs and audits are sufficient for debugging
- Performance targets met
- Security requirements satisfied

## Git Workflow Requirements

### Branch policy
- `main` = stable only
- `develop` = active integration
- `feature branches` = one phase/subphase or one tightly scoped task

### Feature branch naming
- `feat/phase0-spec-baseline`
- `feat/phase1-db-logging-foundation`
- `feat/phase2-queue-workers`
- `feat/phase3-ollama-retries-breaker`
- `feat/phase4-agent-loop`
- `feat/phase5-telegram-interface`
- `feat/phase6-memory-foundation`
- `feat/phase7-memory-embeddings`
- `feat/phase8-tools-core`
- `feat/phase9-scheduler`
- `feat/phase10-skills`
- `feat/phase11-subagents`
- `feat/phase12-soul-modes`
- `feat/phase13-observability`
- `feat/phase14-windows-ops`
- `feat/phase15-hardening-release`

### Commit message standard
- Use Conventional Commits with scope
- Format: `type(scope): summary`
- Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`