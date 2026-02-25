# Agent package
"""
Agent module for Teiken Claw.

Contains the core agent implementation including:
- Ollama HTTP client for LLM communication
- Custom error classes for error handling
- Retry utilities with exponential backoff
- Circuit breaker for fault tolerance
"""

# Ollama Client
from app.agent.ollama_client import (
    OllamaClient,
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    ModelInfo,
    get_ollama_client,
    reset_ollama_client,
)

# Error Classes
from app.agent.errors import (
    TeikenClawError,
    OllamaError,
    OllamaTransportError,
    OllamaResponseError,
    OllamaModelError,
    ToolError,
    ToolValidationError,
    ToolExecutionError,
    SystemError,
    PolicyViolationError,
    PausedStateError,
    CircuitBreakerOpenError,
    is_retryable_error,
    classify_http_status,
)

# Retry Utilities
from app.agent.retries import (
    RetryPolicy,
    RetryStats,
    exponential_backoff_with_jitter,
    is_retryable_error as is_retryable,
    retry_async,
    OLLAMA_CHAT_RETRY_POLICY,
    OLLAMA_EMBED_RETRY_POLICY,
    WEB_FETCH_RETRY_POLICY,
    TELEGRAM_SEND_RETRY_POLICY,
    get_retry_stats,
    record_retry_success,
    record_retry_failure,
    reset_retry_stats,
    get_all_retry_stats,
)

# Circuit Breaker
from app.agent.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerMetrics,
    circuit_breaker_protect,
    get_ollama_circuit_breaker,
    reset_ollama_circuit_breaker,
    get_all_circuit_breaker_status,
    get_circuit_breaker_metrics,
)

__all__ = [
    # Ollama Client
    "OllamaClient",
    "ChatMessage",
    "ChatResponse",
    "EmbeddingResponse",
    "ModelInfo",
    "get_ollama_client",
    "reset_ollama_client",
    # Error Classes
    "TeikenClawError",
    "OllamaError",
    "OllamaTransportError",
    "OllamaResponseError",
    "OllamaModelError",
    "ToolError",
    "ToolValidationError",
    "ToolExecutionError",
    "SystemError",
    "PolicyViolationError",
    "PausedStateError",
    "CircuitBreakerOpenError",
    "is_retryable_error",
    "classify_http_status",
    # Retry Utilities
    "RetryPolicy",
    "RetryStats",
    "exponential_backoff_with_jitter",
    "is_retryable",
    "retry_async",
    "OLLAMA_CHAT_RETRY_POLICY",
    "OLLAMA_EMBED_RETRY_POLICY",
    "WEB_FETCH_RETRY_POLICY",
    "TELEGRAM_SEND_RETRY_POLICY",
    "get_retry_stats",
    "record_retry_success",
    "record_retry_failure",
    "reset_retry_stats",
    "get_all_retry_stats",
    # Circuit Breaker
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerMetrics",
    "circuit_breaker_protect",
    "get_ollama_circuit_breaker",
    "reset_ollama_circuit_breaker",
    "get_all_circuit_breaker_status",
    "get_circuit_breaker_metrics",
]
