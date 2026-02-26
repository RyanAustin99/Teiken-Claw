"""Domain errors for the Teiken control plane."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ControlPlaneError(Exception):
    """Base deterministic error for control-plane operations."""

    def __init__(
        self,
        code: str,
        user_message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.details = details or {}


class SingleInstanceError(ControlPlaneError):
    """Raised when control-plane lock is already held."""

    def __init__(self, lock_path: str, details: Optional[Dict[str, Any]] = None) -> None:
        payload = {"lock_path": lock_path}
        if details:
            payload.update(details)
        super().__init__(
            code="LOCK_HELD",
            user_message="Control plane already running",
            details=payload,
        )


class ValidationError(ControlPlaneError):
    """Raised when user configuration or command input is invalid."""

    def __init__(self, user_message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(code="VALIDATION_ERROR", user_message=user_message, details=details)


class QueueFullError(ControlPlaneError):
    """Raised when an agent queue reached max depth."""

    def __init__(self, agent_id: str, max_depth: int) -> None:
        super().__init__(
            code="QUEUE_FULL",
            user_message=f"Agent queue is full for {agent_id}. Try again shortly.",
            details={"agent_id": agent_id, "max_depth": max_depth},
        )

