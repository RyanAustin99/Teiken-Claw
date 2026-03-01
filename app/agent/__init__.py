# Agent package
"""
Agent module for Teiken Claw.

Contains the core agent implementation including:
- Ollama HTTP client for LLM communication
- Custom error classes for error handling
- Retry utilities with exponential backoff
- Circuit breaker for fault tolerance
- Agent runtime with tool-calling loop
- Context building and prompt management
- Response formatting
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

# Agent Runtime
from app.agent.runtime import (
    AgentRuntime,
    AgentResult,
    ToolCallRecord,
    MAX_TOOL_TURNS,
    MAX_RETRIES,
    get_agent_runtime,
    set_agent_runtime,
    reset_agent_runtime,
)

# Prompts
from app.agent.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    MODE_PROMPTS,
    build_system_prompt,
    build_tool_prompt,
    build_context_prompt,
    format_message_for_prompt,
    build_tool_result_message,
)

# Context Builder
from app.agent.context_builder import (
    ContextBuilder,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RESERVED_TOKENS,
    get_context_builder,
)
from app.agent.prompt_assembler import (
    PromptAssembler,
    PromptBundle,
)

# Result Formatter
from app.agent.result_formatter import (
    TELEGRAM_MAX_LENGTH,
    CLI_MAX_LENGTH,
    DEFAULT_CHUNK_SIZE,
    format_response,
    format_for_telegram,
    format_for_cli,
    chunk_response,
    format_tool_result_for_display,
    format_error_response,
    extract_code_blocks,
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
    # Agent Runtime
    "AgentRuntime",
    "AgentResult",
    "ToolCallRecord",
    "MAX_TOOL_TURNS",
    "MAX_RETRIES",
    "get_agent_runtime",
    "set_agent_runtime",
    "reset_agent_runtime",
    # Prompts
    "DEFAULT_SYSTEM_PROMPT",
    "MODE_PROMPTS",
    "build_system_prompt",
    "build_tool_prompt",
    "build_context_prompt",
    "format_message_for_prompt",
    "build_tool_result_message",
    # Context Builder
    "ContextBuilder",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RESERVED_TOKENS",
    "get_context_builder",
    "PromptAssembler",
    "PromptBundle",
    # Result Formatter
    "TELEGRAM_MAX_LENGTH",
    "CLI_MAX_LENGTH",
    "DEFAULT_CHUNK_SIZE",
    "format_response",
    "format_for_telegram",
    "format_for_cli",
    "chunk_response",
    "format_tool_result_for_display",
    "format_error_response",
    "extract_code_blocks",
]
