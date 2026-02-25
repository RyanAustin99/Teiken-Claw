"""
Retry logic and policies for the Teiken Claw agent system.

This module provides configurable retry mechanisms with exponential backoff and jitter
for handling transient failures in distributed systems.

Key Components:
    - RetryPolicy: Configuration model for retry behavior
    - exponential_backoff_with_jitter: Calculate delay with jitter
    - is_retryable_error: Classify errors as retryable vs permanent
    - retry_async: Decorator for automatic retry with backoff

Default Policies:
    - OLLAMA_CHAT_RETRY_POLICY: For Ollama chat completions
    - OLLAMA_EMBED_RETRY_POLICY: For Ollama embeddings
    - WEB_FETCH_RETRY_POLICY: For web fetching operations
    - TELEGRAM_SEND_RETRY_POLICY: For Telegram message sending
"""

import asyncio
import functools
import logging
import random
from typing import Any, Callable, ParamSpec, TypeVar

from pydantic import BaseModel, Field

from app.agent.errors import (
    CircuitBreakerOpenError,
    OllamaTransportError,
    ToolExecutionError,
    is_retryable_error,
)

logger = logging.getLogger(__name__)

# Type variables for generic decorator
P = ParamSpec("P")
T = TypeVar("T")


class RetryPolicy(BaseModel):
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (including initial call).
        base_delay_sec: Initial delay in seconds before first retry.
        max_delay_sec: Maximum delay cap in seconds.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to delays.
    """

    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    base_delay_sec: float = Field(
        default=1.0, ge=0.0, description="Base delay in seconds"
    )
    max_delay_sec: float = Field(
        default=30.0, ge=0.0, description="Maximum delay cap in seconds"
    )
    exponential_base: float = Field(
        default=2.0, ge=1.0, description="Exponential backoff base"
    )
    jitter: bool = Field(default=True, description="Add random jitter to delays")

    @property
    def max_retries(self) -> int:
        """Number of retries after the initial attempt."""
        return self.max_attempts - 1


def exponential_backoff_with_jitter(
    attempt: int, policy: RetryPolicy
) -> float:
    """
    Calculate delay for a given attempt using exponential backoff with optional jitter.

    The delay is calculated as:
        delay = min(base_delay * (exponential_base ^ attempt), max_delay)

    If jitter is enabled, a random factor between 0.5 and 1.5 is applied.

    Args:
        attempt: The attempt number (0-indexed, so first retry is attempt 1).
        policy: The retry policy configuration.

    Returns:
        The delay in seconds before the next retry.

    Example:
        >>> policy = RetryPolicy(base_delay_sec=1.0, max_delay_sec=30.0, exponential_base=2.0)
        >>> exponential_backoff_with_jitter(0, policy)  # ~1s
        >>> exponential_backoff_with_jitter(1, policy)  # ~2s
        >>> exponential_backoff_with_jitter(2, policy)  # ~4s
    """
    # Calculate base exponential delay
    delay = policy.base_delay_sec * (policy.exponential_base**attempt)

    # Apply cap
    delay = min(delay, policy.max_delay_sec)

    # Apply jitter if enabled (random factor between 0.5 and 1.5)
    if policy.jitter:
        jitter_factor = 0.5 + random.random()  # noqa: S311 (not crypto)
        delay *= jitter_factor

    return delay


def should_retry(error: Exception, policy: RetryPolicy, attempt: int) -> bool:
    """
    Determine if a retry should be attempted for the given error.

    Args:
        error: The exception that occurred.
        policy: The retry policy configuration.
        attempt: The current attempt number (0-indexed).

    Returns:
        True if a retry should be attempted, False otherwise.
    """
    # Check if we've exhausted attempts
    if attempt >= policy.max_attempts - 1:
        return False

    # Check if the error is retryable
    return is_retryable_error(error)


def retry_async(policy: RetryPolicy) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that adds automatic retry with exponential backoff to async functions.

    The decorated function will be retried on retryable errors up to max_attempts
    times, with exponential backoff delays between attempts.

    Args:
        policy: The retry policy configuration.

    Returns:
        A decorator function.

    Example:
        >>> @retry_async(OLLAMA_CHAT_RETRY_POLICY)
        ... async def call_ollama(prompt: str) -> str:
        ...     # Make API call
        ...     pass

    Note:
        - Only retryable errors trigger retries (see is_retryable_error)
        - Permanent errors fail immediately without retry
        - Logs each retry attempt with delay information
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None

            for attempt in range(policy.max_attempts):
                try:
                    return await func(*args, **kwargs)  # type: ignore
                except Exception as e:
                    last_error = e

                    # Check if we should retry
                    if not should_retry(e, policy, attempt):
                        logger.debug(
                            f"Not retrying {func.__name__}: error is not retryable",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "error_type": type(e).__name__,
                                "error_message": str(e),
                            },
                        )
                        raise

                    # Calculate delay for next attempt
                    delay = exponential_backoff_with_jitter(attempt, policy)

                    logger.warning(
                        f"Retrying {func.__name__} after error (attempt {attempt + 1}/{policy.max_attempts})",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": policy.max_attempts,
                            "delay_sec": delay,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )

                    # Wait before retry
                    await asyncio.sleep(delay)

            # Should not reach here, but raise last error if we do
            if last_error:
                raise last_error
            raise RuntimeError(f"Unexpected state in retry logic for {func.__name__}")

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Default Retry Policies
# =============================================================================

# Ollama chat completions - allow more time for model inference
OLLAMA_CHAT_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_sec=1.0,
    max_delay_sec=30.0,
    exponential_base=2.0,
    jitter=True,
)

# Ollama embeddings - faster, smaller payloads
OLLAMA_EMBED_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_sec=0.5,
    max_delay_sec=10.0,
    exponential_base=2.0,
    jitter=True,
)

# Web fetching - external services may be flaky
WEB_FETCH_RETRY_POLICY = RetryPolicy(
    max_attempts=2,
    base_delay_sec=1.0,
    max_delay_sec=10.0,
    exponential_base=2.0,
    jitter=True,
)

# Telegram message sending - critical for user communication
TELEGRAM_SEND_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_sec=1.0,
    max_delay_sec=30.0,
    exponential_base=2.0,
    jitter=True,
)


# =============================================================================
# Retry Statistics (for observability)
# =============================================================================


class RetryStats(BaseModel):
    """Statistics for retry operations."""

    total_calls: int = 0
    successful_first_try: int = 0
    successful_after_retry: int = 0
    failed_after_retries: int = 0
    total_retries: int = 0
    total_delay_sec: float = 0.0

    @property
    def success_rate(self) -> float:
        """Overall success rate including retries."""
        if self.total_calls == 0:
            return 0.0
        return (self.successful_first_try + self.successful_after_retry) / self.total_calls

    @property
    def first_try_success_rate(self) -> float:
        """Success rate on first attempt only."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_first_try / self.total_calls

    @property
    def average_retries_per_call(self) -> float:
        """Average number of retries per call."""
        if self.total_calls == 0:
            return 0.0
        return self.total_retries / self.total_calls


# Global retry statistics tracker
_retry_stats: dict[str, RetryStats] = {}


def get_retry_stats(name: str) -> RetryStats:
    """Get retry statistics for a named operation."""
    if name not in _retry_stats:
        _retry_stats[name] = RetryStats()
    return _retry_stats[name]


def record_retry_success(name: str, attempts: int, total_delay: float) -> None:
    """Record a successful retry operation."""
    stats = get_retry_stats(name)
    stats.total_calls += 1
    stats.total_delay_sec += total_delay

    if attempts == 1:
        stats.successful_first_try += 1
    else:
        stats.successful_after_retry += 1
        stats.total_retries += attempts - 1


def record_retry_failure(name: str, attempts: int, total_delay: float) -> None:
    """Record a failed retry operation."""
    stats = get_retry_stats(name)
    stats.total_calls += 1
    stats.failed_after_retries += 1
    stats.total_retries += attempts - 1
    stats.total_delay_sec += total_delay


def reset_retry_stats() -> None:
    """Reset all retry statistics."""
    global _retry_stats
    _retry_stats = {}


def get_all_retry_stats() -> dict[str, RetryStats]:
    """Get all retry statistics."""
    return _retry_stats.copy()
