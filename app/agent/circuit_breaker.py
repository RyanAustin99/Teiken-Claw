"""
Circuit breaker pattern implementation for the Teiken Claw agent system.

The circuit breaker prevents cascading failures by blocking requests to a failing
service until it has a chance to recover. This is essential for maintaining system
stability when external services (like Ollama) become unavailable.

States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Failing state, all requests are blocked
    - HALF_OPEN: Recovery state, probe requests are allowed

State Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout_sec has elapsed
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure

Usage:
    # Create a circuit breaker
    breaker = CircuitBreaker(
        name="ollama",
        failure_threshold=5,
        success_threshold=1,
        timeout_sec=60.0
    )

    # Use with decorator
    @circuit_breaker_protect(breaker)
    async def call_ollama():
        ...

    # Or use manually
    if breaker.can_execute():
        try:
            result = await call_ollama()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
"""

import asyncio
import functools
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, ParamSpec, TypeVar

from pydantic import BaseModel, Field, PrivateAttr

from app.agent.errors import CircuitBreakerOpenError

logger = logging.getLogger(__name__)

# Type variables for generic decorator
P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failing, requests are blocked
    HALF_OPEN = "half_open"  # Recovery mode, probe requests allowed


class CircuitBreaker(BaseModel):
    """
    Circuit breaker implementation using the state pattern.

    The circuit breaker tracks failures and successes to determine when to
    block requests to a failing service. It automatically transitions between
    states based on configurable thresholds.

    Attributes:
        name: Human-readable name for logging and metrics.
        state: Current circuit state (CLOSED, OPEN, HALF_OPEN).
        failure_count: Consecutive failures in CLOSED state.
        success_count: Consecutive successes in HALF_OPEN state.
        last_failure_time: Timestamp of the most recent failure.
        failure_threshold: Failures needed to transition CLOSED -> OPEN.
        success_threshold: Successes needed to transition HALF_OPEN -> CLOSED.
        timeout_sec: Seconds to wait before transitioning OPEN -> HALF_OPEN.
    """

    name: str = Field(default="default", description="Circuit breaker name")
    state: CircuitState = Field(
        default=CircuitState.CLOSED, description="Current circuit state"
    )
    failure_count: int = Field(default=0, ge=0, description="Consecutive failures")
    success_count: int = Field(default=0, ge=0, description="Consecutive successes")
    last_failure_time: Optional[datetime] = Field(
        default=None, description="Last failure timestamp"
    )
    failure_threshold: int = Field(
        default=5, ge=1, description="Failures to open circuit"
    )
    success_threshold: int = Field(
        default=1, ge=1, description="Successes to close circuit"
    )
    timeout_sec: float = Field(
        default=60.0, ge=0.0, description="Timeout before half-open"
    )

    # Thread lock for state transitions - using PrivateAttr for Pydantic v2 compatibility
    _lock: threading.Lock = PrivateAttr(default_factory=lambda: threading.Lock())

    def can_execute(self) -> bool:
        """
        Check if a request can be executed based on current state.

        Returns:
            True if the request can proceed, False if blocked.

        State behavior:
            - CLOSED: Always returns True
            - OPEN: Returns False until timeout, then transitions to HALF_OPEN
            - HALF_OPEN: Returns True for probe requests
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if self._should_transition_to_half_open():
                    self._transition_to_half_open()
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                return True

            return False

    def should_allow_request(self) -> bool:
        """
        Alias for can_execute() for API compatibility.

        Returns:
            True if the request should be allowed.
        """
        return self.can_execute()

    def record_success(self) -> None:
        """
        Record a successful operation.

        In CLOSED state: Resets failure count.
        In HALF_OPEN state: Increments success count, may transition to CLOSED.
        In OPEN state: Should not be called (log warning).
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = 0
                logger.debug(
                    f"Circuit breaker '{self.name}' success in CLOSED state, "
                    f"failure count reset"
                )

            elif self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    f"Circuit breaker '{self.name}' success in HALF_OPEN state "
                    f"({self.success_count}/{self.success_threshold})"
                )

                if self.success_count >= self.success_threshold:
                    self._transition_to_closed()

            elif self.state == CircuitState.OPEN:
                logger.warning(
                    f"Circuit breaker '{self.name}' recorded success while OPEN - "
                    f"this should not happen"
                )

    def record_failure(self) -> None:
        """
        Record a failed operation.

        In CLOSED state: Increments failure count, may transition to OPEN.
        In HALF_OPEN state: Transitions immediately to OPEN.
        In OPEN state: Updates last_failure_time.
        """
        with self._lock:
            self.last_failure_time = datetime.now(timezone.utc)

            if self.state == CircuitState.CLOSED:
                self.failure_count += 1
                logger.warning(
                    f"Circuit breaker '{self.name}' failure in CLOSED state "
                    f"({self.failure_count}/{self.failure_threshold})"
                )

                if self.failure_count >= self.failure_threshold:
                    self._transition_to_open()

            elif self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker '{self.name}' failure in HALF_OPEN state, "
                    f"transitioning to OPEN"
                )
                self._transition_to_open()

            elif self.state == CircuitState.OPEN:
                logger.debug(
                    f"Circuit breaker '{self.name}' failure recorded while OPEN"
                )

    def _should_transition_to_half_open(self) -> bool:
        """Check if enough time has elapsed to transition from OPEN to HALF_OPEN."""
        if self.last_failure_time is None:
            return True

        elapsed = (
            datetime.now(timezone.utc) - self.last_failure_time
        ).total_seconds()
        return elapsed >= self.timeout_sec

    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.success_count = 0
        logger.warning(
            f"Circuit breaker '{self.name}' transitioned: {old_state.value} -> OPEN "
            f"(failures: {self.failure_count})"
        )

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        logger.info(
            f"Circuit breaker '{self.name}' transitioned: {old_state.value} -> HALF_OPEN"
        )

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(
            f"Circuit breaker '{self.name}' transitioned: {old_state.value} -> CLOSED"
        )

    def reset(self) -> None:
        """Reset the circuit breaker to initial CLOSED state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            logger.info(f"Circuit breaker '{self.name}' reset to CLOSED")

    def force_open(self) -> None:
        """Force the circuit breaker to OPEN state (for testing/maintenance)."""
        with self._lock:
            self.state = CircuitState.OPEN
            self.last_failure_time = datetime.now(timezone.utc)
            logger.warning(f"Circuit breaker '{self.name}' forced to OPEN")

    @property
    def is_closed(self) -> bool:
        """Check if circuit is in CLOSED state."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is in OPEN state."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is in HALF_OPEN state."""
        return self.state == CircuitState.HALF_OPEN

    def get_status(self) -> dict[str, Any]:
        """
        Get current circuit breaker status for health checks.

        Returns:
            Dictionary with current state and metrics.
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "timeout_sec": self.timeout_sec,
                "last_failure_time": (
                    self.last_failure_time.isoformat()
                    if self.last_failure_time
                    else None
                ),
            }


def circuit_breaker_protect(
    breaker: CircuitBreaker,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that protects an async function with a circuit breaker.

    If the circuit breaker is open, raises CircuitBreakerOpenError instead
    of executing the function. Records successes and failures to the breaker.

    Args:
        breaker: The circuit breaker instance to use.

    Returns:
        A decorator function.

    Example:
        >>> breaker = CircuitBreaker(name="ollama", failure_threshold=5)
        >>> @circuit_breaker_protect(breaker)
        ... async def call_ollama(prompt: str) -> str:
        ...     # Make API call
        ...     pass

    Raises:
        CircuitBreakerOpenError: If the circuit breaker is open.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Check if we can execute
            if not breaker.can_execute():
                raise CircuitBreakerOpenError(
                    message=f"Circuit breaker '{breaker.name}' is open",
                    breaker_name=breaker.name,
                    failure_count=breaker.failure_count,
                    timeout_sec=breaker.timeout_sec,
                )

            try:
                result = await func(*args, **kwargs)  # type: ignore
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Global Circuit Breaker Instances
# =============================================================================

# Global Ollama circuit breaker (configured via settings in production)
_ollama_circuit_breaker: Optional[CircuitBreaker] = None
_ollama_breaker_lock = threading.Lock()


def get_ollama_circuit_breaker(
    failure_threshold: int = 5,
    success_threshold: int = 1,
    timeout_sec: float = 60.0,
) -> CircuitBreaker:
    """
    Get or create the global Ollama circuit breaker.

    This is a singleton pattern to ensure all Ollama calls use the same
    circuit breaker instance.

    Args:
        failure_threshold: Failures needed to open circuit.
        success_threshold: Successes needed to close circuit.
        timeout_sec: Timeout before transitioning to half-open.

    Returns:
        The global Ollama circuit breaker instance.
    """
    global _ollama_circuit_breaker

    with _ollama_breaker_lock:
        if _ollama_circuit_breaker is None:
            _ollama_circuit_breaker = CircuitBreaker(
                name="ollama",
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout_sec=timeout_sec,
            )
            logger.info(
                f"Created Ollama circuit breaker: "
                f"failure_threshold={failure_threshold}, "
                f"success_threshold={success_threshold}, "
                f"timeout_sec={timeout_sec}"
            )
        return _ollama_circuit_breaker


def reset_ollama_circuit_breaker() -> None:
    """Reset the global Ollama circuit breaker (for testing)."""
    global _ollama_circuit_breaker

    with _ollama_breaker_lock:
        if _ollama_circuit_breaker is not None:
            _ollama_circuit_breaker.reset()


# =============================================================================
# Circuit Breaker Metrics
# =============================================================================


class CircuitBreakerMetrics(BaseModel):
    """Aggregated metrics for circuit breaker monitoring."""

    total_breakers: int = 0
    closed_count: int = 0
    open_count: int = 0
    half_open_count: int = 0

    @property
    def health_percentage(self) -> float:
        """Percentage of breakers in healthy (CLOSED) state."""
        if self.total_breakers == 0:
            return 100.0
        return (self.closed_count / self.total_breakers) * 100


def get_all_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """
    Get status of all known circuit breakers.

    Returns:
        Dictionary mapping breaker names to their status.
    """
    statuses: dict[str, dict[str, Any]] = {}

    # Add Ollama circuit breaker if it exists
    global _ollama_circuit_breaker
    if _ollama_circuit_breaker is not None:
        statuses["ollama"] = _ollama_circuit_breaker.get_status()

    return statuses


def get_circuit_breaker_metrics() -> CircuitBreakerMetrics:
    """
    Get aggregated metrics for all circuit breakers.

    Returns:
        CircuitBreakerMetrics with counts by state.
    """
    statuses = get_all_circuit_breaker_status()

    metrics = CircuitBreakerMetrics()
    metrics.total_breakers = len(statuses)

    for status in statuses.values():
        state = status.get("state", "closed")
        if state == "closed":
            metrics.closed_count += 1
        elif state == "open":
            metrics.open_count += 1
        elif state == "half_open":
            metrics.half_open_count += 1

    return metrics
