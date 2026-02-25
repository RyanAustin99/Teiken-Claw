"""
Application settings for Teiken Claw.

This module provides configuration via environment variables with defaults.
Settings are loaded from .env file and can be overridden by environment variables.
"""

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
    APP_VERSION: str = "1.0.0"
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
    
    # =========================================================================
    # Memory Configuration
    # =========================================================================
    
    AUTO_MEMORY_ENABLED: bool = True
    MEMORY_TYPE: str = "sqlite"
    MEMORY_URL: str = "sqlite:///./data/memory.db"
    
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
    # Redis Configuration (optional)
    # =========================================================================
    
    REDIS_URL: Optional[str] = None
    
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
