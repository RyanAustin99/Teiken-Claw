# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.22.0] - 2026-03-01

### Added

- Phase 22 Souls + Modes deterministic contract:
  - Versioned souls/ and modes/ registries with schema validation + hashes
  - Thread/session persisted ctive_mode, ctive_soul, and mode lock controls
  - Persona resolver with legacy mode aliases and effective tool/file policy derivation
  - Deterministic prompt assembly with prompt fingerprinting
  - Telegram /soul command surface and expanded /mode controls (list/show/set/lock/unlock)
  - Persona audit persistence for soul/mode changes

### Changed

- Runtime now resolves soul/mode deterministically per request and enforces effective tool/file policy at execution time.
- Telegram status now reports active soul/mode scope and effective file policy summary.
- Control-plane agent/session models include explicit default and active soul/mode state for deterministic behavior.

## [1.21.0] - 2026-02-28

### Added

- Phase 21 Memory v1.5 persistence and APIs:
  - `memory_items` and `memory_audit_events` schema/models
  - Thread public refs (`t_...`) and memory refs (`m_...`)
  - Deterministic extraction orchestration with secret/category blocking
  - Thread-scoped memory stores (`ThreadStore`, `MessageStore`, `MemoryStoreV15`)

### Changed

- Telegram `/thread` commands now use persistent thread records:
  - `/thread new`, `/thread list`, `/thread use`, `/thread` info
- Telegram `/memory` commands now target active thread memory cards:
  - `/memory review`, `/memory search`, `/memory forget`, `/memory pause`, `/memory resume`, `/memory stats`
- Agent runtime memory pipeline is deterministic-first and no longer creates memory from LLM extraction output.
- Context builder now injects deterministic thread header + relevant memory cards + recent transcript window.

## [1.0.1] - Unreleased

### Fixed

- `.gitignore` - Force-added `app/config/` directory (was ignored by `config/` pattern)
  - Added `app/config/__init__.py`, `app/config/constants.py`, `app/config/logging.py` to git
  - These modules are required for application runtime

### Added - Phase 10: Skills System

#### Skill System Core
- `app/skills/__init__.py` - Skills package exports
- `app/skills/schema.py` - YAML skill schema validation
  - SkillDefinition, SkillStep, SkillTrigger, SkillInput, SkillOutput models
  - StepType enum (tool_call, llm_prompt, condition, transform, subagent, schedule_create, return)
  - Schema validation functions
- `app/skills/loader.py` - Skill definitions loader
  - SkillLoader class
  - load_skill(), load_all_skills(), validate_skill() methods
  - Skill search and category filtering
- `app/skills/engine.py` - Skill execution engine
  - SkillEngine class with execute_skill() method
  - Step executors for each step type
  - ExecutionContext for state management
  - SkillResult for execution results
- `app/skills/router.py` - Skill routing
  - SkillRouter class
  - route_intent() for detecting skill triggers
  - Direct invocation detection (/skill <name>)
  - Keyword and pattern matching

#### Built-in Skills
- `app/skills/definitions/create_job.yaml` - Job creation skill
- `app/skills/definitions/summarize_files.yaml` - File summarization skill
- `app/skills/definitions/run_study.yaml` - Study/research workflow skill
- `app/skills/definitions/debug_report.yaml` - Debug report generation skill

#### Integration
- `app/main.py` - Skills initialization on startup
  - SkillLoader, SkillEngine, SkillRouter initialization
  - Tool registration with engine
- `app/interfaces/telegram_commands.py` - Skill commands
  - handle_skills() - List and run skills
  - _list_skills() - List available skills
  - _execute_skill() - Execute skill and format result
- `app/interfaces/telegram_bot.py` - /skills command handler
- `app/agent/runtime.py` - Skill router integration
  - _check_skill_trigger() - Pre-process check for skill triggers
  - Automatic skill execution before agent processing

#### Tests
- `tests/test_skills.py` - Comprehensive skill system tests
  - Schema validation tests
  - Loader tests
  - Engine execution tests
  - Router matching tests
  - Integration tests

## [1.0.0] - 2026-02-25

### Added - Phase 9: Scheduler / Cron System

#### APScheduler Integration
- `app/scheduler/__init__.py` - Scheduler package exports
- `app/scheduler/service.py` - SchedulerService class
  - AsyncIOScheduler integration
  - SQLite-backed job persistence
  - Date, interval, and cron trigger support
  - Job lifecycle management (add, remove, pause, resume)
- `app/scheduler/jobs.py` - Job models
  - ScheduledJob Pydantic model
  - JobRunResult Pydantic model
  - TriggerType, JobStatus enums
  - TriggerConfig, JobAction models
- `app/scheduler/parser.py` - Schedule parsing
  - ScheduleParser class
  - Cron expression parsing with aliases (@daily, @hourly, etc.)
  - Interval trigger parsing
  - Date trigger parsing
  - Validation utilities
- `app/scheduler/executor.py` - Job execution bridge
  - SchedulerExecutor class
  - Retry logic with configurable max_retries
  - Dead-letter queue integration
  - Job history tracking
- `app/scheduler/control_state.py` - Control state management
  - ControlStateManager class
  - Control states: normal, pause_jobs, pause_tools, pause_all
  - Persisted across restarts
- `app/scheduler/persistence.py` - Job persistence
  - SchedulerPersistence class
  - SQLite-backed job storage
  - Run history tracking

#### Telegram Commands
- `/jobs` - List scheduled jobs
- `/jobs <job_id>` - Show job details
- `/jobs pause <job_id>` - Pause specific job
- `/jobs resume <job_id>` - Resume specific job
- `/jobs delete <job_id>` - Delete job
- `/jobs run <job_id>` - Run job now
- `/pause jobs` - Pause all scheduled jobs
- `/pause all` - Pause everything (read-only mode)
- `/resume` - Resume from pause

#### Configuration
- `app/config/settings.py` - Added scheduler settings
  - SCHEDULER_ENABLED: bool = True
  - SCHEDULER_MAX_INSTANCES: int = 3
  - SCHEDULER_COALESCE: bool = True
  - SCHEDULER_MAX_INSTANCES_PER_JOB: int = 1
  - SCHEDULER_MISFIRE_GRACE_SEC: int = 300
  - SCHEDULER_JOB_DEFAULTS: dict

#### Dependencies
- `requirements.txt` - Added apscheduler>=3.10.0

#### Tests
- `tests/test_scheduler.py` - Comprehensive scheduler tests
  - Schedule parser tests
  - Job model tests
  - Control state tests
  - Persistence tests
  - Executor tests
  - Service tests
  - Tool tests
  - Integration tests

### Added - Phase 8: Tool Implementations

#### Security Utilities
- `app/security/__init__.py` - Security package exports
- `app/security/path_guard.py` - Path validation and traversal protection
  - PathGuard class for workspace boundary enforcement
  - normalize_path() for path normalization
  - prevent_traversal() for traversal attack detection
  - is_within_workspace() for boundary checking
  - validate_and_resolve() for full validation pipeline
- `app/security/sanitization.py` - Input sanitization utilities
  - Sanitizer class for input validation
  - sanitize_url() with scheme and domain validation
  - sanitize_path() with traversal protection
  - sanitize_command() with shell metacharacter detection
  - sanitize_filename() with reserved name blocking

#### Web Tool
- `app/tools/web_tool.py` - Web operations tool
  - search() using DuckDuckGo
  - fetch() for URL content retrieval
  - extract() for readable text extraction
  - search_and_extract() combined operation
  - Domain allowlist support
  - Timeout and response size limits

#### Files Tool
- `app/tools/files_tool.py` - File operations tool
  - list_dir() for directory listing
  - read_file() for file reading
  - write_file() for file writing
  - search_files() for content/name search
  - delete_file() for file deletion (admin only)
  - Workspace sandbox enforcement
  - Path traversal protection

#### Exec Tool
- `app/tools/exec_tool.py` - Command execution tool
  - powershell_exec() with allowlist enforcement
  - python_exec() with sandboxed execution
  - Execution modes: safe, extended, disabled
  - Command allowlist for PowerShell
  - Protected environment variables
  - Full audit logging

#### Memory Tool
- `app/tools/memory_tool.py` - Memory operations tool
  - remember() for storing memories
  - search() for searching memories
  - forget() for deleting memories
  - review() for listing memories
  - pause()/resume() for auto-memory control
  - Memory types: fact, preference, context, instruction, note
  - Memory scopes: global, chat, session

#### Scheduler Tool
- `app/tools/scheduler_tool.py` - Scheduler operations tool
  - create() for creating scheduled jobs
  - list() for listing jobs
  - pause()/resume() for job control
  - delete() for job deletion
  - run_now() for immediate execution
  - pause_all()/resume_all() for bulk operations
  - Trigger types: interval, cron, once

#### Tests
- `tests/test_security.py` - Security utilities tests
- `tests/test_web_tool.py` - Web tool tests
- `tests/test_files_tool.py` - Files tool tests
- `tests/test_exec_tool.py` - Exec tool tests
- `tests/test_memory_tool.py` - Memory tool tests
- `tests/test_scheduler_tool.py` - Scheduler tool tests

#### Configuration
- Added tool settings to settings.py:
  - WEB_TIMEOUT_SEC, WEB_MAX_RESPONSE_SIZE, WEB_ALLOWED_DOMAINS
  - FILES_MAX_SIZE
  - EXEC_TIMEOUT_SEC, EXEC_ADMIN_ONLY

#### Dependencies
- duckduckgo-search>=4.0.0
- beautifulsoup4>=4.12.0
- readability-lxml>=0.8.1
- lxml>=4.9.0
- aiofiles>=23.0.0

### Added - Phase 7: LLM Memory Extraction + Embeddings + Hybrid Retrieval

#### LLM Memory Extractor
- `app/memory/extractor_llm.py` - LLM-based memory extraction
  - LLMMemoryExtractor class for intelligent memory extraction
  - extract_memory() method using Ollama for structured extraction
  - ExtractedMemory schema with validation (memory_type, content, tags, confidence, scope, ttl_days, sensitive, justification)
  - ExtractionResult schema for batch results
  - Server-side validation: confidence threshold, category allowlist, size limits
  - VALID_MEMORY_TYPES allowlist (preference, project, workflow, environment, schedule_pattern, fact, note)
  - VALID_SCOPES validation (global, project, thread, user)
  - extract_multiple() for batch extraction
  - extract_from_conversation() for conversation analysis

#### Memory Deduplication
- `app/memory/dedupe.py` - Memory deduplication system
  - MemoryDeduplicator class for duplicate detection
  - hash_content() for SHA-256 content hashing
  - check_duplicate() for exact duplicate detection
  - find_similar() for semantic similarity detection
  - semantic_similarity() using embeddings
  - mark_duplicate() for soft-delete duplicates
  - check_and_dedupe() combined check method
  - restore_duplicate() for restoring marked duplicates
  - cleanup_duplicates() for permanent deletion of old duplicates

#### Embedding Service
- `app/memory/embeddings.py` - Ollama embeddings integration
  - EmbeddingService class for embedding generation
  - embed() for single text embedding using nomic-embed-text
  - embed_batch() for batch embedding generation
  - store_embedding() for persisting embeddings
  - get_embedding() for retrieving embeddings
  - compute_similarity() for cosine similarity calculation
  - find_nearest() for nearest neighbor search
  - needs_re_embedding() for detecting stale embeddings
  - re_embed() for updating embeddings
  - re_embed_all() for model migration
  - Model version tracking for re-embedding support

#### Hybrid Retrieval System
- `app/memory/retrieval.py` - Hybrid retrieval combining keyword and semantic search
  - MemoryRetriever class for hybrid search
  - retrieve() method combining FTS5 and semantic search
  - keyword_search() for text-based search
  - semantic_search() for embedding-based search
  - merge_results() for combining search results
  - rank_results() for weighted scoring
  - retrieve_with_budget() for token-budget-aware retrieval
  - get_relevant_memories() for context building
  - RetrievalResult dataclass with scores

#### Integration Updates
- `app/memory/store.py` - Enhanced with embedding support
  - create_memory() now generates and stores embeddings automatically
  - search_memories() uses hybrid retrieval by default
  - Fallback to keyword search on hybrid failure

- `app/agent/context_builder.py` - Enhanced with retrieval integration
  - _get_relevant_memories() uses hybrid retrieval
  - Builds query from recent context for semantic search
  - Returns memories with confidence and relevance scores

- `app/agent/runtime.py` - Enhanced memory extraction pipeline
  - _trigger_memory_extraction() now uses both rules and LLM extraction
  - _llm_memory_extraction() for LLM-based extraction
  - _check_memory_duplicate() for deduplication before storage
  - Merged candidates from deterministic and LLM extraction

- `app/main.py` - New service initialization
  - EmbeddingService initialization on startup
  - MemoryRetriever initialization on startup
  - MemoryDeduplicator initialization on startup
  - LLMMemoryExtractor initialization on startup

- `app/config/settings.py` - New embedding settings
  - EMBEDDING_MODEL (default: nomic-embed-text)
  - EMBEDDING_DIMENSION (default: 768)
  - RETRIEVAL_TOP_K (default: 10)
  - SEMANTIC_SEARCH_THRESHOLD (default: 0.7)
  - DEDUPE_SIMILARITY_THRESHOLD (default: 0.9)

#### Tests
- `tests/test_embeddings.py` - Embedding service tests
  - Test embedding generation
  - Test similarity computation
  - Test nearest neighbor search
  - Test model version tracking
  - Test error handling

- `tests/test_retrieval.py` - Retrieval system tests
  - Test keyword search
  - Test semantic search
  - Test hybrid retrieval
  - Test result ranking
  - Test error handling

### Added - Phase 6: Memory System - Deterministic + Review First

#### Memory Database Models
- `app/memory/models.py` - Memory database models
  - Session model (id, chat_id, created_at, updated_at, mode, metadata)
  - Thread model (id, session_id, created_at, updated_at, summary, metadata)
  - SessionMessage model (id, thread_id, role, content, created_at, metadata)
  - ThreadSummary model (id, thread_id, content, created_at, version)
  - MemoryRecord model (id, memory_type, content, tags, scope, confidence, created_at, updated_at)
  - MemoryAudit model (id, memory_id, action, reason, created_at)
  - EmbeddingRecord model (id, source_type, source_id, content_hash, embedding_model, vector_dim, created_at)
  - ControlState model (id, key, value, updated_at)
  - IdempotencyKey model (id, key, created_at, expires_at)
  - AppEvent model (id, event_type, event_data, created_at)

#### Memory Store
- `app/memory/store.py` - Memory CRUD operations
  - MemoryStore class with async database operations
  - append_message() for persisting messages to threads
  - create_thread() and get_thread() for thread management
  - create_memory(), get_memory(), update_memory(), delete_memory() for memory CRUD
  - list_memories() with filtering by scope, type, tags
  - search_memories() for text-based search
  - audit_memory() for tracking memory changes

#### Thread State Management
- `app/memory/thread_state.py` - Thread tracking
  - ThreadState class for managing conversation threads
  - get_current_thread() for retrieving active thread
  - set_current_thread() for updating active thread
  - create_new_thread() for starting new conversations
  - get_thread_history() for retrieving past threads
  - get_all_sessions() for listing all sessions
  - get_session_stats() for session statistics

#### Context Routing
- `app/agent/context_router.py` - Topic detection and routing
  - ContextRouter class for intelligent thread management
  - should_create_new_thread() for topic change detection
  - get_topic_similarity() for semantic similarity scoring
  - create_new_thread_if_needed() for automatic thread creation
  - get_thread_context() for retrieving thread context

#### Context Builder Updates
- `app/agent/context_builder.py` - Enhanced context assembly
  - Thread context integration (recent messages)
  - Relevant memories retrieval
  - Scheduler/tool state snapshots
  - Mode-specific context handling

#### Deterministic Extraction
- `app/memory/extraction_rules.py` - Deterministic filtering rules
  - MemoryExtractionRules class for rule-based extraction
  - classify_candidates() for filtering and categorization
  - is_allowed_category() for category validation
  - is_sensitive_content() for sensitive data detection
  - get_category() for content categorization
  - extract_facts() for fact extraction
  - extract_preferences() for preference extraction

#### LLM Extractor Placeholder
- `app/memory/extractor_llm.py` - LLM-based extraction (Phase 7 prep)
  - LLMMemoryExtractor class (minimal implementation)
  - extract_memory() method (returns empty for now)

#### Memory Review Commands
- `app/memory/review.py` - Memory review operations
  - MemoryReview class for user-facing memory operations
  - list_memories() for reviewing stored memories
  - search_memories() for finding specific memories
  - get_memory(), edit_memory(), delete_memory() for CRUD
  - pin_memory(), unpin_memory() for importance marking
  - pause_auto_memory(), resume_auto_memory() for user control
  - get_auto_memory_status() for checking state

#### Telegram Memory Commands
- `app/interfaces/telegram_commands.py` - Memory command handlers
  - /memory review - List recent memories
  - /memory search <query> - Search memories
  - /memory forget <id> - Delete a memory
  - /memory edit <id> <text> - Edit a memory
  - /memory pause - Pause auto-memory
  - /memory resume - Resume auto-memory
  - /memory policy - Show memory policy

#### Configuration
- `app/config/settings.py` - Memory settings
  - AUTO_MEMORY_ENABLED (default: True)
  - AUTO_MEMORY_CONFIDENCE_THRESHOLD (default: 0.7)
  - MAX_THREAD_MESSAGES (default: 100)
  - THREAD_INACTIVITY_TIMEOUT_MIN (default: 30)

#### Tests
- `tests/test_memory.py` - Memory system tests
  - MemoryStore tests (CRUD operations)
  - ThreadState tests (thread management)
  - ContextRouter tests (topic routing)
  - MemoryExtractionRules tests (extraction logic)
  - MemoryReview tests (review commands)
  - Integration tests (full lifecycle)
  - Edge case tests (empty, unicode, long content)

### Changed
- `app/main.py` - Added memory system initialization
- `app/agent/runtime.py` - Added memory persistence and extraction triggers
- `app/agent/context_builder.py` - Enhanced with thread and memory context

### Added - Phase 5: Telegram Interface + Command System

#### Telegram Bot
- `app/interfaces/telegram_bot.py` - Telegram bot implementation
  - TelegramBot class using python-telegram-bot (async)
  - start() method for polling mode
  - stop() method for graceful shutdown
  - Message handler that extracts chat_id, user_id, message text
  - Creates Job and enqueues to dispatcher
  - Shows typing indicator while processing
  - Error handler for Telegram API errors
  - Support for ENABLE_TELEGRAM flag to disable
  - All command handlers registered (/start, /help, /ping, /status, etc.)

#### Telegram Sender
- `app/interfaces/telegram_sender.py` - Telegram message sender
  - TelegramSender class for sending messages
  - send_message(chat_id, text, parse_mode) method
  - send_chunked_message() for long messages (>4096 chars)
  - Retry on 429 (rate limit) with retry-after respect
  - Retry on network errors with exponential backoff
  - Integration with OutboundQueue
  - Sender loop that pulls from outbound queue

#### Command Router
- `app/interfaces/telegram_commands.py` - Command handlers
  - CommandRouter class for all command processing
  - Core Commands: /start, /help, /ping, /status
  - Mode Commands: /mode, /mode <name>
  - Thread Commands: /thread, /thread new, /thread summary
  - Memory Commands (stubs): /memory review, /memory search, /memory pause, /memory resume
  - Scheduler Commands (stubs): /jobs, /pause jobs, /pause all, /resume
  - Admin Commands: /admin stats, /admin trace <job_id>
  - Admin permission checking

#### Interface Adapters
- `app/interfaces/adapters.py` - Message format conversion
  - TelegramAdapter class for message conversion
  - message_to_job() for Telegram to Job conversion
  - response_to_telegram() for internal to Telegram format
  - MarkdownV2 escaping utilities
  - HTML escaping utilities
  - Message formatting helpers (bold, italic, code, links)
  - Message validation and chunking

#### CLI Interface
- `app/interfaces/cli.py` - Interactive CLI
  - CLIInterface class for interactive REPL
  - Support for ENABLE_CLI flag
  - Command processing (/help, /exit, /status, /mode, /clear, /history)
  - Job creation and enqueueing
  - Response handling

#### Integration
- Updated `app/main.py` with Telegram bot lifecycle
  - Initialize TelegramBot on startup (if enabled)
  - Initialize TelegramSender on startup
  - Start bot polling on startup
  - Start sender loop on startup
  - Stop bot on shutdown
  - Stop sender on shutdown
- Updated `app/interfaces/__init__.py` with all exports
- Updated `requirements.txt` with aiolimiter dependency

#### Tests
- `tests/test_telegram.py` - Telegram interface tests
  - TelegramAdapter tests (escaping, conversion, formatting)
  - CommandRouter tests (all commands, permissions)
  - TelegramSender tests (chunking, retry logic)
  - Rate limiting tests
  - OutboundQueue tests
  - Integration tests

### Added - Phase 4: Core Agent Loop

#### Agent Runtime
- `app/agent/runtime.py` - Core agent runtime with tool-calling loop
  - AgentRuntime class with run(job) -> AgentResult method
  - MAX_TOOL_TURNS guard (default: 10) to prevent infinite loops
  - Duplicate tool call detection using argument hashing
  - Circuit breaker integration for fault tolerance
  - Retry logic for transient errors
  - Graceful error handling for all error types
  - AgentResult Pydantic model for structured responses
  - ToolCallRecord for duplicate detection

#### Tool System
- `app/tools/base.py` - Base tool interface
  - Tool abstract base class with name, description, json_schema
  - ToolResult Pydantic model (ok, content, error_code, error_message)
  - ToolPolicy Pydantic model (enabled, admin_only, allowed_chats, timeout_sec)
  - ToolError, ToolTimeoutError, ToolDisabledError, ToolPermissionError
- `app/tools/registry.py` - Tool registry for management
  - ToolRegistry class with register, get, get_all_schemas methods
  - execute_tool_call() with timeout and error handling
  - Permission checking integration
  - Global registry singleton pattern
- `app/tools/policies.py` - Tool policies and permission checking
  - check_tool_permission() function
  - get_paused_behavior() function
  - Default policies for common tool types
  - Policy validation and merging
- `app/tools/validators.py` - Argument validation and coercion
  - validate_tool_args() with schema validation
  - coerce_value() for type coercion
  - safe_defaults() for default value generation
  - Support for string, integer, number, boolean, array, object types

#### Mock Tools
- `app/tools/mock_tools.py` - Mock tools for development
  - EchoTool - echoes input back
  - TimeTool - returns current time in various formats
  - StatusTool - returns system status
  - DelayTool - tests timeout handling
  - ErrorTool - tests error handling
  - register_mock_tools() function for easy registration

#### Context Building
- `app/agent/context_builder.py` - Context assembly
  - ContextBuilder class with build() method
  - Token budget management (placeholder)
  - Message truncation for long conversations
  - System prompt integration
- `app/agent/prompts.py` - System prompt building
  - build_system_prompt() with mode support
  - build_tool_prompt() for tool descriptions
  - MODE_PROMPTS dictionary for different modes
  - DEFAULT_SYSTEM_PROMPT template

#### Response Formatting
- `app/agent/result_formatter.py` - Response formatting
  - format_response() for channel-specific formatting
  - format_for_telegram() with MarkdownV2 escaping
  - format_for_cli() for terminal output
  - chunk_response() for long message splitting
  - extract_code_blocks() for code extraction

#### Integration
- Updated `app/main.py` with ToolRegistry and AgentRuntime initialization
- Updated `app/queue/workers.py` with chat message handler
- Updated `app/agent/__init__.py` with new exports
- Updated `app/tools/__init__.py` with all tool exports

#### Tests
- `tests/test_agent_runtime.py` - Agent runtime tests (12 test cases)
- `tests/test_tools.py` - Tool registry and validator tests (25+ test cases)

### Added - Phase 3: Ollama Client, Retry Logic, and Circuit Breaker

#### Ollama HTTP Client
- `app/agent/ollama_client.py` - Async HTTP client for Ollama API
  - ChatMessage, ChatResponse, EmbeddingResponse, ModelInfo models
  - chat() method for completions with tool calling support
  - embeddings() method for text embeddings
  - list_models() method for available models
  - check_health() method for connectivity verification
  - Automatic retry with exponential backoff
  - Circuit breaker protection
  - Timeout handling and error classification
  - Singleton pattern via get_ollama_client()

#### Custom Error Classes
- `app/agent/errors.py` - Comprehensive error hierarchy
  - TeikenClawError (base class)
  - OllamaError -> OllamaTransportError, OllamaResponseError, OllamaModelError
  - ToolError -> ToolValidationError, ToolExecutionError
  - SystemError -> PolicyViolationError, PausedStateError, CircuitBreakerOpenError
  - is_retryable_error() classification function
  - classify_http_status() for HTTP status classification

#### Retry Utilities
- `app/agent/retries.py` - Retry logic with exponential backoff
  - RetryPolicy Pydantic model with configurable parameters
  - exponential_backoff_with_jitter() function
  - retry_async() decorator for automatic retry
  - Default retry policies:
    - OLLAMA_CHAT_RETRY_POLICY (3 attempts, 1s base, 30s max)
    - OLLAMA_EMBED_RETRY_POLICY (3 attempts, 0.5s base, 10s max)
    - WEB_FETCH_RETRY_POLICY (2 attempts, 1s base, 10s max)
    - TELEGRAM_SEND_RETRY_POLICY (3 attempts, 1s base, 30s max)
  - RetryStats for observability

#### Circuit Breaker
- `app/agent/circuit_breaker.py` - Fault tolerance pattern
  - CircuitState enum (CLOSED, OPEN, HALF_OPEN)
  - CircuitBreaker class with state transitions:
    - CLOSED -> OPEN (after failure_threshold)
    - OPEN -> HALF_OPEN (after timeout)
    - HALF_OPEN -> CLOSED (after success_threshold)
    - HALF_OPEN -> OPEN (on failure)
  - circuit_breaker_protect() decorator
  - Global Ollama circuit breaker singleton
  - CircuitBreakerMetrics for monitoring

#### Configuration
- New Ollama circuit breaker settings in `app/config/settings.py`:
  - OLLAMA_CIRCUIT_BREAKER_FAILURE_THRESHOLD (default: 5)
  - OLLAMA_CIRCUIT_BREAKER_TIMEOUT_SEC (default: 60.0)
  - OLLAMA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD (default: 1)

#### Application Integration
- Updated `app/main.py`:
  - Ollama connectivity check in /health/ready
  - Circuit breaker status in /health
  - Agent module imports

#### Tests
- `tests/test_ollama_client.py` - Comprehensive tests
  - Error classification tests
  - Retry policy and backoff tests
  - Circuit breaker state transition tests
  - Ollama client tests (chat, embeddings, models)
  - Error handling tests (timeout, network, HTTP errors)
  - Integration tests for retry + circuit breaker

---

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

