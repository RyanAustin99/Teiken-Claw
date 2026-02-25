"""
Application constants for Teiken Claw.

This module defines all application-wide constants including:
- Job priority levels
- Control state keys
- Default values
- Status codes
- Time constants
"""

# =============================================================================
# Application Constants
# =============================================================================

APP_NAME = "Teiken Claw"
APP_DESCRIPTION = "AI Agent System"
APP_VERSION = "1.0.0"

# =============================================================================
# Environment Constants
# =============================================================================

ENVIRONMENT_DEVELOPMENT = "development"
ENVIRONMENT_PRODUCTION = "production"
ENVIRONMENT_TESTING = "testing"

# =============================================================================
# Job Priority Constants
# =============================================================================

# Lower number = higher priority
JOB_PRIORITY_INTERACTIVE = 10  # User-initiated requests (highest priority)
JOB_PRIORITY_SUBAGENT = 20     # Subagent tasks
JOB_PRIORITY_SCHEDULED = 30    # Scheduled/cron jobs
JOB_PRIORITY_MAINTENANCE = 40  # Background maintenance (lowest priority)

# =============================================================================
# Control State Keys
# =============================================================================

CONTROL_KEY_MAINTENANCE_MODE = "maintenance_mode"
CONTROL_KEY_MAX_CONCURRENT_JOBS = "max_concurrent_jobs"
CONTROL_KEY_MEMORY_ENABLED = "memory_enabled"
CONTROL_KEY_SCHEDULER_ENABLED = "scheduler_enabled"
CONTROL_KEY_LAST_MIGRATION_VERSION = "last_migration_version"
CONTROL_KEY_FEATURE_FLAGS = "feature_flags"

# Default control state values
DEFAULT_CONTROL_STATES = {
    CONTROL_KEY_MAINTENANCE_MODE: "false",
    CONTROL_KEY_MAX_CONCURRENT_JOBS: "10",
    CONTROL_KEY_MEMORY_ENABLED: "true",
    CONTROL_KEY_SCHEDULER_ENABLED: "true",
    CONTROL_KEY_LAST_MIGRATION_VERSION: "0",
    CONTROL_KEY_FEATURE_FLAGS: "{}",
}

# =============================================================================
# Database Constants
# =============================================================================

DATABASE_SQLITE = "sqlite"
DATABASE_POSTGRES = "postgresql"
DATABASE_MYSQL = "mysql"

# SQLite PRAGMA defaults
SQLITE_JOURNAL_MODE_WAL = "WAL"
SQLITE_SYNCHRONOUS_NORMAL = "NORMAL"
SQLITE_BUSY_TIMEOUT_MS = 5000

# =============================================================================
# Queue Constants
# =============================================================================

QUEUE_REDIS = "redis"
QUEUE_SQLITE = "sqlite"
QUEUE_RABBITMQ = "rabbitmq"
QUEUE_SQS = "sqs"

# Queue status
QUEUE_STATUS_PENDING = "pending"
QUEUE_STATUS_RUNNING = "running"
QUEUE_STATUS_COMPLETED = "completed"
QUEUE_STATUS_FAILED = "failed"
QUEUE_STATUS_CANCELLED = "cancelled"

# =============================================================================
# Memory Constants
# =============================================================================

MEMORY_REDIS = "redis"
MEMORY_SQLITE = "sqlite"
MEMORY_MEMCACHED = "memcached"
MEMORY_IN_MEMORY = "in_memory"

# Memory types
MEMORY_TYPE_EPISODIC = "episodic"
MEMORY_TYPE_SEMANTIC = "semantic"
MEMORY_TYPE_PROCEDURAL = "procedural"
MEMORY_TYPE_WORKING = "working"

# Memory scopes
MEMORY_SCOPE_GLOBAL = "global"
MEMORY_SCOPE_SESSION = "session"
MEMORY_SCOPE_USER = "user"

# =============================================================================
# Agent Constants
# =============================================================================

AGENT_STATUS_ACTIVE = "active"
AGENT_STATUS_INACTIVE = "inactive"
AGENT_STATUS_ERROR = "error"

# Message roles
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"

# =============================================================================
# Scheduler Constants
# =============================================================================

TRIGGER_TYPE_INTERVAL = "interval"
TRIGGER_TYPE_CRON = "cron"
TRIGGER_TYPE_DATE = "date"
TRIGGER_TYPE_ONCE = "once"

# Scheduler job status
SCHEDULER_STATUS_PENDING = "pending"
SCHEDULER_STATUS_RUNNING = "running"
SCHEDULER_STATUS_COMPLETED = "completed"
SCHEDULER_STATUS_FAILED = "failed"
SCHEDULER_STATUS_CANCELLED = "cancelled"

# =============================================================================
# HTTP Status Codes
# =============================================================================

HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201
HTTP_STATUS_NO_CONTENT = 204
HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_CONFLICT = 409
HTTP_STATUS_UNPROCESSABLE_ENTITY = 422
HTTP_STATUS_TOO_MANY_REQUESTS = 429
HTTP_STATUS_INTERNAL_ERROR = 500
HTTP_STATUS_NOT_IMPLEMENTED = 501
HTTP_STATUS_SERVICE_UNAVAILABLE = 503

# =============================================================================
# Time Constants
# =============================================================================

SECONDS_IN_MINUTE = 60
SECONDS_IN_HOUR = 3600
SECONDS_IN_DAY = 86400
SECONDS_IN_WEEK = 604800

# Milliseconds
MS_IN_SECOND = 1000
MS_IN_MINUTE = 60000
MS_IN_HOUR = 3600000

# =============================================================================
# File Paths
# =============================================================================

LOGS_DIR = "logs"
CONFIG_DIR = "config"
DATA_DIR = "data"
TEMP_DIR = "temp"
WORKSPACE_DIR = "workspace"

# =============================================================================
# Default Values
# =============================================================================

DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_MAX_CONCURRENT_JOBS = 10

# Ollama defaults
DEFAULT_OLLAMA_TIMEOUT = 120
DEFAULT_OLLAMA_MAX_CONCURRENCY = 3
DEFAULT_OLLAMA_CHAT_MODEL = "llama3.2"
DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"

# Telegram defaults
DEFAULT_TELEGRAM_GLOBAL_MSG_PER_SEC = 25.0
DEFAULT_TELEGRAM_PER_CHAT_MSG_PER_SEC = 1.0

# Agent defaults
DEFAULT_MAX_TOOL_TURNS = 10
DEFAULT_AGENT_TIMEOUT = 30

# =============================================================================
# Feature Flags
# =============================================================================

FEATURE_MEMORY_ENABLED = "memory_enabled"
FEATURE_SCHEDULER_ENABLED = "scheduler_enabled"
FEATURE_SUBAGENTS_ENABLED = "subagents_enabled"
FEATURE_WEB_SEARCH_ENABLED = "web_search_enabled"
FEATURE_CODE_EXECUTION_ENABLED = "code_execution_enabled"

# =============================================================================
# Event Types
# =============================================================================

EVENT_APP_STARTUP = "app_startup"
EVENT_APP_SHUTDOWN = "app_shutdown"
EVENT_REQUEST_START = "request_start"
EVENT_REQUEST_END = "request_end"
EVENT_JOB_START = "job_start"
EVENT_JOB_END = "job_end"
EVENT_JOB_ERROR = "job_error"
EVENT_MEMORY_CREATE = "memory_create"
EVENT_MEMORY_UPDATE = "memory_update"
EVENT_MEMORY_DELETE = "memory_delete"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_ERROR = "tool_error"

# =============================================================================
# Error Codes
# =============================================================================

ERROR_CODE_UNKNOWN = "UNKNOWN_ERROR"
ERROR_CODE_TIMEOUT = "TIMEOUT_ERROR"
ERROR_CODE_RATE_LIMIT = "RATE_LIMIT_ERROR"
ERROR_CODE_VALIDATION = "VALIDATION_ERROR"
ERROR_CODE_NOT_FOUND = "NOT_FOUND_ERROR"
ERROR_CODE_UNAUTHORIZED = "UNAUTHORIZED_ERROR"
ERROR_CODE_FORBIDDEN = "FORBIDDEN_ERROR"
ERROR_CODE_CONFLICT = "CONFLICT_ERROR"
ERROR_CODE_INTERNAL = "INTERNAL_ERROR"
ERROR_CODE_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE_ERROR"

# =============================================================================
# Export
# =============================================================================

__all__ = [
    # Application
    "APP_NAME",
    "APP_DESCRIPTION",
    "APP_VERSION",
    
    # Environment
    "ENVIRONMENT_DEVELOPMENT",
    "ENVIRONMENT_PRODUCTION",
    "ENVIRONMENT_TESTING",
    
    # Job Priority
    "JOB_PRIORITY_INTERACTIVE",
    "JOB_PRIORITY_SUBAGENT",
    "JOB_PRIORITY_SCHEDULED",
    "JOB_PRIORITY_MAINTENANCE",
    
    # Control State
    "CONTROL_KEY_MAINTENANCE_MODE",
    "CONTROL_KEY_MAX_CONCURRENT_JOBS",
    "CONTROL_KEY_MEMORY_ENABLED",
    "CONTROL_KEY_SCHEDULER_ENABLED",
    "CONTROL_KEY_LAST_MIGRATION_VERSION",
    "CONTROL_KEY_FEATURE_FLAGS",
    "DEFAULT_CONTROL_STATES",
    
    # Database
    "DATABASE_SQLITE",
    "DATABASE_POSTGRES",
    "DATABASE_MYSQL",
    "SQLITE_JOURNAL_MODE_WAL",
    "SQLITE_SYNCHRONOUS_NORMAL",
    "SQLITE_BUSY_TIMEOUT_MS",
    
    # Queue
    "QUEUE_REDIS",
    "QUEUE_SQLITE",
    "QUEUE_RABBITMQ",
    "QUEUE_SQS",
    "QUEUE_STATUS_PENDING",
    "QUEUE_STATUS_RUNNING",
    "QUEUE_STATUS_COMPLETED",
    "QUEUE_STATUS_FAILED",
    "QUEUE_STATUS_CANCELLED",
    
    # Memory
    "MEMORY_REDIS",
    "MEMORY_SQLITE",
    "MEMORY_MEMCACHED",
    "MEMORY_IN_MEMORY",
    "MEMORY_TYPE_EPISODIC",
    "MEMORY_TYPE_SEMANTIC",
    "MEMORY_TYPE_PROCEDURAL",
    "MEMORY_TYPE_WORKING",
    "MEMORY_SCOPE_GLOBAL",
    "MEMORY_SCOPE_SESSION",
    "MEMORY_SCOPE_USER",
    
    # Agent
    "AGENT_STATUS_ACTIVE",
    "AGENT_STATUS_INACTIVE",
    "AGENT_STATUS_ERROR",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_SYSTEM",
    "ROLE_TOOL",
    
    # Scheduler
    "TRIGGER_TYPE_INTERVAL",
    "TRIGGER_TYPE_CRON",
    "TRIGGER_TYPE_DATE",
    "TRIGGER_TYPE_ONCE",
    "SCHEDULER_STATUS_PENDING",
    "SCHEDULER_STATUS_RUNNING",
    "SCHEDULER_STATUS_COMPLETED",
    "SCHEDULER_STATUS_FAILED",
    "SCHEDULER_STATUS_CANCELLED",
    
    # HTTP Status
    "HTTP_STATUS_OK",
    "HTTP_STATUS_CREATED",
    "HTTP_STATUS_NO_CONTENT",
    "HTTP_STATUS_BAD_REQUEST",
    "HTTP_STATUS_UNAUTHORIZED",
    "HTTP_STATUS_FORBIDDEN",
    "HTTP_STATUS_NOT_FOUND",
    "HTTP_STATUS_CONFLICT",
    "HTTP_STATUS_UNPROCESSABLE_ENTITY",
    "HTTP_STATUS_TOO_MANY_REQUESTS",
    "HTTP_STATUS_INTERNAL_ERROR",
    "HTTP_STATUS_NOT_IMPLEMENTED",
    "HTTP_STATUS_SERVICE_UNAVAILABLE",
    
    # Time
    "SECONDS_IN_MINUTE",
    "SECONDS_IN_HOUR",
    "SECONDS_IN_DAY",
    "SECONDS_IN_WEEK",
    "MS_IN_SECOND",
    "MS_IN_MINUTE",
    "MS_IN_HOUR",
    
    # Paths
    "LOGS_DIR",
    "CONFIG_DIR",
    "DATA_DIR",
    "TEMP_DIR",
    "WORKSPACE_DIR",
    
    # Defaults
    "DEFAULT_TIMEOUT",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_DELAY",
    "DEFAULT_MAX_CONCURRENT_JOBS",
    "DEFAULT_OLLAMA_TIMEOUT",
    "DEFAULT_OLLAMA_MAX_CONCURRENCY",
    "DEFAULT_OLLAMA_CHAT_MODEL",
    "DEFAULT_OLLAMA_EMBED_MODEL",
    "DEFAULT_TELEGRAM_GLOBAL_MSG_PER_SEC",
    "DEFAULT_TELEGRAM_PER_CHAT_MSG_PER_SEC",
    "DEFAULT_MAX_TOOL_TURNS",
    "DEFAULT_AGENT_TIMEOUT",
    
    # Feature Flags
    "FEATURE_MEMORY_ENABLED",
    "FEATURE_SCHEDULER_ENABLED",
    "FEATURE_SUBAGENTS_ENABLED",
    "FEATURE_WEB_SEARCH_ENABLED",
    "FEATURE_CODE_EXECUTION_ENABLED",
    
    # Events
    "EVENT_APP_STARTUP",
    "EVENT_APP_SHUTDOWN",
    "EVENT_REQUEST_START",
    "EVENT_REQUEST_END",
    "EVENT_JOB_START",
    "EVENT_JOB_END",
    "EVENT_JOB_ERROR",
    "EVENT_MEMORY_CREATE",
    "EVENT_MEMORY_UPDATE",
    "EVENT_MEMORY_DELETE",
    "EVENT_TOOL_CALL",
    "EVENT_TOOL_ERROR",
    
    # Error Codes
    "ERROR_CODE_UNKNOWN",
    "ERROR_CODE_TIMEOUT",
    "ERROR_CODE_RATE_LIMIT",
    "ERROR_CODE_VALIDATION",
    "ERROR_CODE_NOT_FOUND",
    "ERROR_CODE_UNAUTHORIZED",
    "ERROR_CODE_FORBIDDEN",
    "ERROR_CODE_CONFLICT",
    "ERROR_CODE_INTERNAL",
    "ERROR_CODE_SERVICE_UNAVAILABLE",
]
