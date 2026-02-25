"""
Custom error classes for the Teiken Claw agent system.

This module defines all custom exceptions used throughout the agent subsystem,
including Ollama communication errors, tool execution errors, and system state errors.

Error Hierarchy:
    Exception
    └── TeikenClawError (base for all custom errors)
        ├── OllamaError (base for Ollama-related errors)
        │   ├── OllamaTransportError (network/timeout errors)
        │   ├── OllamaResponseError (invalid response)
        │   └── OllamaModelError (model not found)
        ├── ToolError (base for tool-related errors)
        │   ├── ToolValidationError (invalid tool args)
        │   └── ToolExecutionError (tool execution failed)
        └── SystemError (base for system state errors)
            ├── PolicyViolationError (policy check failed)
            ├── PausedStateError (system paused)
            └── CircuitBreakerOpenError (breaker open)
"""

from typing import Any, Optional


class TeikenClawError(Exception):
    """Base exception for all Teiken Claw custom errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details: {self.details}"
        return self.message


# =============================================================================
# Ollama Errors
# =============================================================================


class OllamaError(TeikenClawError):
    """Base exception for Ollama-related errors."""

    pass


class OllamaTransportError(OllamaError):
    """
    Raised when a network or timeout error occurs during Ollama communication.

    This error is retryable - it indicates a transient failure that may succeed
    on subsequent attempts.

    Attributes:
        endpoint: The Ollama API endpoint that failed.
        timeout: Whether the error was caused by a timeout.
    """

    def __init__(
        self,
        message: str,
        endpoint: Optional[str] = None,
        timeout: bool = False,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.endpoint = endpoint
        self.timeout = timeout

    def __str__(self) -> str:
        parts = [self.message]
        if self.endpoint:
            parts.append(f"endpoint={self.endpoint}")
        if self.timeout:
            parts.append("timeout=True")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


class OllamaResponseError(OllamaError):
    """
    Raised when Ollama returns an invalid or unexpected response.

    This error is typically permanent - it indicates a configuration issue
    or incompatible response format.

    Attributes:
        status_code: HTTP status code if available.
        response_body: The raw response body for debugging.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"status_code={self.status_code}")
        if self.response_body:
            # Truncate response body for display
            truncated = (
                self.response_body[:200] + "..."
                if len(self.response_body) > 200
                else self.response_body
            )
            parts.append(f"response={truncated}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


class OllamaModelError(OllamaError):
    """
    Raised when a requested model is not found or not available in Ollama.

    This error is permanent - the model must be pulled or the configuration
    must be corrected.

    Attributes:
        model_name: The name of the model that was not found.
    """

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.model_name = model_name

    def __str__(self) -> str:
        parts = [self.message]
        if self.model_name:
            parts.append(f"model={self.model_name}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


# =============================================================================
# Tool Errors
# =============================================================================


class ToolError(TeikenClawError):
    """Base exception for tool-related errors."""

    pass


class ToolValidationError(ToolError):
    """
    Raised when tool arguments fail validation.

    This error is permanent for the given input - the arguments must be corrected.

    Attributes:
        tool_name: The name of the tool that failed validation.
        arguments: The invalid arguments that were provided.
        validation_errors: List of specific validation error messages.
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        arguments: Optional[dict[str, Any]] = None,
        validation_errors: Optional[list[str]] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.tool_name = tool_name
        self.arguments = arguments
        self.validation_errors = validation_errors or []

    def __str__(self) -> str:
        parts = [self.message]
        if self.tool_name:
            parts.append(f"tool={self.tool_name}")
        if self.validation_errors:
            parts.append(f"errors={self.validation_errors}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


class ToolExecutionError(ToolError):
    """
    Raised when a tool execution fails.

    This error may be retryable depending on the nature of the failure.

    Attributes:
        tool_name: The name of the tool that failed.
        retryable: Whether the error is retryable.
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        retryable: bool = False,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.tool_name = tool_name
        self.retryable = retryable

    def __str__(self) -> str:
        parts = [self.message]
        if self.tool_name:
            parts.append(f"tool={self.tool_name}")
        parts.append(f"retryable={self.retryable}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


# =============================================================================
# System Errors
# =============================================================================


class SystemError(TeikenClawError):
    """Base exception for system state errors."""

    pass


class PolicyViolationError(SystemError):
    """
    Raised when an action violates a policy check.

    This error is permanent - the action is not allowed by policy.

    Attributes:
        policy_name: The name of the policy that was violated.
        action: The action that was blocked.
    """

    def __init__(
        self,
        message: str,
        policy_name: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.policy_name = policy_name
        self.action = action

    def __str__(self) -> str:
        parts = [self.message]
        if self.policy_name:
            parts.append(f"policy={self.policy_name}")
        if self.action:
            parts.append(f"action={self.action}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


class PausedStateError(SystemError):
    """
    Raised when an action is attempted while the system is paused.

    This error is transient - the system may be resumed.

    Attributes:
        reason: The reason the system is paused.
    """

    def __init__(
        self,
        message: str = "System is paused",
        reason: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.reason = reason

    def __str__(self) -> str:
        parts = [self.message]
        if self.reason:
            parts.append(f"reason={self.reason}")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


class CircuitBreakerOpenError(SystemError):
    """
    Raised when a request is blocked by an open circuit breaker.

    This error is transient - the circuit breaker will transition to half-open
    after the timeout period.

    Attributes:
        breaker_name: The name of the circuit breaker.
        failure_count: The number of failures that caused the breaker to open.
        timeout_sec: Seconds until the breaker transitions to half-open.
    """

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        breaker_name: Optional[str] = None,
        failure_count: int = 0,
        timeout_sec: float = 60.0,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.breaker_name = breaker_name
        self.failure_count = failure_count
        self.timeout_sec = timeout_sec

    def __str__(self) -> str:
        parts = [self.message]
        if self.breaker_name:
            parts.append(f"breaker={self.breaker_name}")
        parts.append(f"failures={self.failure_count}")
        parts.append(f"timeout={self.timeout_sec}s")
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


# =============================================================================
# Error Classification Utilities
# =============================================================================


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.

    Retryable errors are transient failures that may succeed on retry:
    - OllamaTransportError (network/timeout)
    - ToolExecutionError with retryable=True
    - CircuitBreakerOpenError (wait for half-open)

    Permanent errors should not be retried:
    - OllamaResponseError (4xx errors, invalid responses)
    - OllamaModelError (model not found)
    - ToolValidationError (invalid arguments)
    - PolicyViolationError (policy blocked)
    - PausedStateError (system paused)

    Args:
        error: The exception to classify.

    Returns:
        True if the error is retryable, False otherwise.
    """
    # Ollama transport errors are retryable
    if isinstance(error, OllamaTransportError):
        return True

    # Tool execution errors may be retryable
    if isinstance(error, ToolExecutionError):
        return error.retryable

    # Circuit breaker open is retryable after timeout
    if isinstance(error, CircuitBreakerOpenError):
        return True

    # All other errors are permanent
    return False


def classify_http_status(status_code: int) -> str:
    """
    Classify an HTTP status code as retryable or permanent.

    Args:
        status_code: HTTP status code.

    Returns:
        'retryable' for 5xx and 429, 'permanent' for 4xx, 'unknown' otherwise.
    """
    if status_code >= 500:
        return "retryable"
    elif status_code == 429:  # Too Many Requests
        return "retryable"
    elif status_code >= 400:
        return "permanent"
    else:
        return "unknown"
