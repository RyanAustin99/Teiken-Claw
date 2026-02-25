"""
Enhanced structured logging for Teiken Claw.

This module provides JSON structured logging with:
- Trace ID context management
- Rotating file handler
- Console handler
- Structured log fields (timestamp, level, trace_id, job_id, session_id, thread_id, component, event)
"""

import logging
import sys
import json
import os
from datetime import datetime, timezone
from typing import Optional, Any
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config.settings import settings


# Context variables for trace ID and related IDs
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
job_id_var: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
session_id_var: ContextVar[Optional[int]] = ContextVar("session_id", default=None)
thread_id_var: ContextVar[Optional[int]] = ContextVar("thread_id", default=None)
component_var: ContextVar[Optional[str]] = ContextVar("component", default=None)


def get_trace_id() -> Optional[str]:
    """Get the current trace ID from context."""
    return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID in context."""
    trace_id_var.set(trace_id)


def get_job_id() -> Optional[str]:
    """Get the current job ID from context."""
    return job_id_var.get()


def set_job_id(job_id: str) -> None:
    """Set the job ID in context."""
    job_id_var.set(job_id)


def get_session_id() -> Optional[int]:
    """Get the current session ID from context."""
    return session_id_var.get()


def set_session_id(session_id: int) -> None:
    """Set the session ID in context."""
    session_id_var.set(session_id)


def get_thread_id() -> Optional[int]:
    """Get the current thread ID from context."""
    return thread_id_var.get()


def set_thread_id(thread_id: int) -> None:
    """Set the thread ID in context."""
    thread_id_var.set(thread_id)


def get_component() -> Optional[str]:
    """Get the current component from context."""
    return component_var.get()


def set_component(component: str) -> None:
    """Set the component in context."""
    component_var.set(component)


def clear_context() -> None:
    """Clear all context variables."""
    trace_id_var.set(None)
    job_id_var.set(None)
    session_id_var.set(None)
    thread_id_var.set(None)
    component_var.set(None)


class StructuredLogRecord(logging.LogRecord):
    """Custom log record with structured fields."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace_id = get_trace_id()
        self.job_id = get_job_id()
        self.session_id = get_session_id()
        self.thread_id = get_thread_id()
        self.component = get_component()


class StructuredFormatter(logging.Formatter):
    """
    JSON structured log formatter.
    
    Outputs logs in JSON format with structured fields:
    - timestamp: ISO 8601 UTC timestamp
    - level: Log level
    - trace_id: Request trace ID
    - job_id: Background job ID
    - session_id: User session ID
    - thread_id: Conversation thread ID
    - component: Component/module name
    - event: Event type (from extra)
    - message: Log message
    - logger: Logger name
    - extra: Additional fields
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        # Create the base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add context fields if present
        if hasattr(record, "trace_id") and record.trace_id:
            log_entry["trace_id"] = record.trace_id
        elif get_trace_id():
            log_entry["trace_id"] = get_trace_id()
        
        if hasattr(record, "job_id") and record.job_id:
            log_entry["job_id"] = record.job_id
        elif get_job_id():
            log_entry["job_id"] = get_job_id()
        
        if hasattr(record, "session_id") and record.session_id:
            log_entry["session_id"] = record.session_id
        elif get_session_id():
            log_entry["session_id"] = get_session_id()
        
        if hasattr(record, "thread_id") and record.thread_id:
            log_entry["thread_id"] = record.thread_id
        elif get_thread_id():
            log_entry["thread_id"] = get_thread_id()
        
        if hasattr(record, "component") and record.component:
            log_entry["component"] = record.component
        elif get_component():
            log_entry["component"] = get_component()
        
        # Add event type if provided
        if hasattr(record, "event"):
            log_entry["event"] = record.event
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "trace_id", "job_id", "session_id", "thread_id",
                "component", "event"
            }:
                extra_fields[key] = value
        
        if extra_fields:
            log_entry["extra"] = extra_fields
        
        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter with color support.
    
    Format: [timestamp] LEVEL [trace_id] message (component)
    """
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record for console output."""
        # Get timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Get color for level
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""
        
        # Build the formatted message
        parts = [f"[{timestamp}]"]
        parts.append(f"{color}{record.levelname:8}{reset}")
        
        # Add trace ID if present
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        if trace_id:
            parts.append(f"[{trace_id[:8]}]")
        
        # Add message
        parts.append(record.getMessage())
        
        # Add component if present
        component = getattr(record, "component", None) or get_component()
        if component:
            parts.append(f"({component})")
        
        # Add exception if present
        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))
        
        return " ".join(parts)


class StructuredLogger(logging.Logger):
    """
    Custom logger with structured logging support.
    
    Provides convenience methods for logging with structured fields:
    - log_event(): Log with event type
    - log_with_context(): Log with full context
    """
    
    def log_event(
        self,
        level: int,
        event: str,
        message: str,
        **kwargs: Any
    ) -> None:
        """
        Log with an event type.
        
        Args:
            level: Log level
            event: Event type (e.g., "request_start", "job_complete")
            message: Log message
            **kwargs: Additional structured fields
        """
        extra = {"event": event, **kwargs}
        super()._log(level, message, (), extra=extra)
    
    def log_with_context(
        self,
        level: int,
        message: str,
        trace_id: Optional[str] = None,
        job_id: Optional[str] = None,
        session_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        component: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Log with full context.
        
        Args:
            level: Log level
            message: Log message
            trace_id: Request trace ID
            job_id: Background job ID
            session_id: User session ID
            thread_id: Conversation thread ID
            component: Component/module name
            **kwargs: Additional structured fields
        """
        extra = {
            "trace_id": trace_id,
            "job_id": job_id,
            "session_id": session_id,
            "thread_id": thread_id,
            "component": component,
            **kwargs
        }
        super()._log(level, message, (), extra=extra)


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    enable_json: bool = True,
    enable_console: bool = True,
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        enable_json: Enable JSON structured logging to file
        enable_console: Enable console logging
    """
    # Get log level from settings or parameter
    level_name = log_level or settings.LOG_LEVEL
    level = getattr(logging, level_name.upper(), logging.INFO)
    
    # Set custom logger class
    logging.setLoggerClass(StructuredLogger)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create log directory
    log_path = Path(log_dir or settings.LOGS_DIR)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # JSON file handler with rotation
    if enable_json:
        json_handler = RotatingFileHandler(
            log_path / "app.json.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        json_handler.setLevel(level)
        json_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(json_handler)
    
    # Plain text file handler with rotation
    text_handler = RotatingFileHandler(
        log_path / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    text_handler.setLevel(level)
    text_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root_logger.addHandler(text_handler)
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    # Configure third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DATABASE_ECHO else logging.WARNING
    )
    logging.getLogger("alembic").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured",
        extra={
            "event": "logging_configured",
            "level": level_name,
            "log_dir": str(log_path),
        }
    )


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        StructuredLogger: A structured logger instance
    """
    return logging.getLogger(name)  # type: ignore


# Export commonly used items
__all__ = [
    "setup_logging",
    "get_logger",
    "get_trace_id",
    "set_trace_id",
    "get_job_id",
    "set_job_id",
    "get_session_id",
    "set_session_id",
    "get_thread_id",
    "set_thread_id",
    "get_component",
    "set_component",
    "clear_context",
    "StructuredLogger",
    "StructuredFormatter",
    "ConsoleFormatter",
]
