"""
Application settings for Teiken Claw.

This module provides configuration via environment variables with defaults.
Settings are loaded from .env file and can be overridden by environment variables.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Optional, List
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Settings can be overridden by:
    1. Environment variables (highest priority)
    2. .env file
    3. Default values (lowest priority)
    """
    
    # =========================================================================
    # Application Configuration
    # =========================================================================
    
    APP_NAME: str = "Teiken Claw"
    APP_DESCRIPTION: str = "AI Agent System"
    APP_VERSION: str = "1.22.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # =========================================================================
    # Database Configuration
    # =========================================================================
    
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/teiken_claw.db"
    DATABASE_ECHO: bool = False
    
    # =========================================================================
    # Ollama Configuration
    # =========================================================================
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT_SEC: int = 120
    OLLAMA_MAX_CONCURRENCY: int = 3
    
    # Ollama Circuit Breaker Configuration
    OLLAMA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    OLLAMA_CIRCUIT_BREAKER_TIMEOUT_SEC: float = 60.0
    OLLAMA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 1
    
    # =========================================================================
    # Telegram Configuration
    # =========================================================================
    
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_GLOBAL_MSG_PER_SEC: float = 25.0
    TELEGRAM_PER_CHAT_MSG_PER_SEC: float = 1.0
    
    # =========================================================================
    # Interface Configuration
    # =========================================================================
    
    ENABLE_CLI: bool = True
    ENABLE_TELEGRAM: bool = False
    
    # =========================================================================
    # Workspace Configuration
    # =========================================================================
    
    WORKSPACE_DIR: str = "./data/workspace"
    LOGS_DIR: str = "./logs"
    
    # =========================================================================
    # Logging Configuration
    # =========================================================================
    
    LOG_LEVEL: str = "INFO"
    
    # =========================================================================
    # Agent Configuration
    # =========================================================================
    
    AGENT_MAX_CONCURRENT: int = 5
    AGENT_TIMEOUT: int = 30
    MAX_TOOL_TURNS: int = 10
    TC_BOOT_MAX_WORDS: int = 140
    TC_BOOT_MAX_QUESTIONS: int = 2
    TC_BOOT_FORBIDDEN_PHRASES: List[str] = [
        "this agent",
        "as an ai",
        "language model",
        "system prompt",
        "developer instructions",
        "operational identity",
        "teiken claw agent",
        "how can i assist you today",
        "keep it respectful",
        "keep it clean and professional",
    ]
    TC_BOOT_CANNED_PHRASES: List[str] = [
        "hello, i am your agent",
        "hello, i am an agent",
        "hello! i am your assistant",
        "how can i help you today",
        "i am here to help you",
    ]
    TC_BOOT_LIST_MARKERS: List[str] = [
        r"^\s*[-*•]\s+",
        r"^\s*\d+\.\s+",
        r"^\s*\d+\)\s+",
    ]
    TC_BOOT_RETRY_ON_LINT_FAIL: int = 1
    TC_BOOT_DIRECTIVES: Optional[str] = None
    TC_BOOT_TEMPERATURE: float = 0.7
    TC_BOOT_TOP_P: float = 0.9
    
    # =========================================================================
    # Memory Configuration
    # =========================================================================
    
    AUTO_MEMORY_ENABLED: bool = True
    AUTO_MEMORY_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_THREAD_MESSAGES: int = 100
    THREAD_INACTIVITY_TIMEOUT_MIN: int = 30
    MEMORY_CONTEXT_MAX_MESSAGES: int = 20
    MEMORY_CONTEXT_MAX_ITEMS: int = 20
    MEMORY_ROUTER_SIMILARITY_THRESHOLD: float = 0.35
    MEMORY_SECRET_BLOCK_ENABLED: bool = True
    MEMORY_THREAD_PROPOSE_ONLY: bool = True
    DEFAULT_SOUL_REF: str = "teiken_claw_agent@1.5.0"
    DEFAULT_MODE_REF: str = "builder@1.5.0"
    SOULS_DIR: str = "./souls"
    MODES_DIR: str = "./modes"
    SOULS_HOT_RELOAD: bool = False
    MODES_HOT_RELOAD: bool = False
    MEMORY_TYPE: str = "sqlite"
    MEMORY_URL: str = "sqlite:///./data/memory.db"
    
    # Embedding Configuration
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSION: int = 768
    RETRIEVAL_TOP_K: int = 10
    SEMANTIC_SEARCH_THRESHOLD: float = 0.7
    DEDUPE_SIMILARITY_THRESHOLD: float = 0.9
    
    # =========================================================================
    # Queue Configuration
    # =========================================================================
    
    QUEUE_TYPE: str = "sqlite"
    QUEUE_URL: str = "sqlite:///./data/queue.db"
    QUEUE_MAX_SIZE: int = 1000
    WORKER_COUNT: int = 3
    OLLAMA_MAX_CONCURRENCY: int = 2
    TELEGRAM_GLOBAL_MSG_PER_SEC: float = 30.0
    TELEGRAM_PER_CHAT_MSG_PER_SEC: float = 1.0
    JOB_MAX_ATTEMPTS: int = 3
    LOCK_TIMEOUT_SEC: int = 300
    IDEMPOTENCY_TTL_SEC: int = 3600
    
    # =========================================================================
    # Security Configuration
    # =========================================================================
    
    ADMIN_CHAT_IDS: List[int] = []
    EXEC_ALLOWLIST: List[str] = []
    WEB_ALLOWED_DOMAINS: List[str] = []
    
    # =========================================================================
    # Tool Configuration (Phase 8)
    # =========================================================================
    
    # Web Tool Settings
    WEB_TIMEOUT_SEC: float = 30.0
    WEB_MAX_RESPONSE_SIZE: int = 1_000_000  # 1MB
    
    # Files Tool Settings
    FILES_MAX_SIZE: int = 10_000_000  # 10MB
    FILES_MAX_READ_BYTES: int = 1_048_576  # 1MB
    FILES_MAX_WRITE_BYTES: int = 262_144  # 256KB
    FILES_SOFT_WRITE_WARN_RATIO: float = 0.75
    FILES_ALLOWED_WRITE_EXTENSIONS: List[str] = [".md", ".txt", ".json", ".yaml", ".yml", ".log"]
    FILES_ALLOW_OVERWRITE: bool = True
    FILES_AUTO_MKDIR: bool = True
    
    # Exec Tool Settings
    EXEC_TIMEOUT_SEC: float = 60.0
    EXEC_ADMIN_ONLY: bool = True
    
    # =========================================================================
    # Scheduler Configuration (Phase 9)
    # =========================================================================
    
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_MAX_INSTANCES: int = 3
    SCHEDULER_COALESCE: bool = True
    SCHEDULER_MAX_INSTANCES_PER_JOB: int = 1
    SCHEDULER_MISFIRE_GRACE_SEC: int = 300  # 5 minutes
    SCHEDULER_JOB_DEFAULTS: dict = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    }
    
    # =========================================================================
    # Observability Configuration (Phase 13)
    # =========================================================================
    
    AUDIT_ENABLED: bool = True
    METRICS_ENABLED: bool = True
    TRACING_ENABLED: bool = True
    
    # =========================================================================
    # Redis Configuration (optional)
    # =========================================================================
    
    REDIS_URL: Optional[str] = None

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _coerce_debug_bool(cls, value):
        """
        Accept common non-boolean env values for DEBUG.

        Some environments set DEBUG to values like "release" or "prod".
        Normalize these safely instead of failing settings initialization.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            truthy = {"1", "true", "yes", "y", "on", "debug", "dev", "development", "test", "testing"}
            falsy = {"0", "false", "no", "n", "off", "release", "prod", "production"}
            if normalized in truthy:
                return True
            if normalized in falsy:
                return False
        return value
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        # Parse list values from comma-separated strings
        env_parse_none_str = ""
        
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT.lower() in ("development", "dev", "local")
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT.lower() in ("production", "prod")
    
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.ENVIRONMENT.lower() in ("testing", "test")
    
    def get_database_path(self) -> str:
        """Extract the database file path from DATABASE_URL."""
        url = self.DATABASE_URL
        if ":///" in url:
            # SQLite file path
            return url.split(":///")[1]
        return url


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are only loaded once.
    
    Returns:
        Settings: The application settings instance.
    """
    return Settings()


# Global settings instance
settings = get_settings()


# Export
__all__ = ["Settings", "settings", "get_settings"]
