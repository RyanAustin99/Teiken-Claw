"""Reusable widgets and formatting helpers for control-plane TUI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.control_plane.domain.errors import ControlPlaneError

from textual.widgets import Static


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    LOADING = "loading"


HEALTH_STYLE = {
    HealthState.HEALTHY: ("[OK]", "status-healthy"),
    HealthState.DEGRADED: ("[WARN]", "status-degraded"),
    HealthState.FAILED: ("[FAIL]", "status-failed"),
    HealthState.LOADING: ("[WAIT]", "status-loading"),
}


def format_health(label: str, state: HealthState, detail: Optional[str] = None) -> str:
    icon, _ = HEALTH_STYLE[state]
    suffix = f" - {detail}" if detail else ""
    return f"{icon} {label}{suffix}"


def format_size(size_bytes: Optional[int]) -> str:
    if not size_bytes:
        return "-"
    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = 0
    while size >= 1024.0 and unit < len(units) - 1:
        size /= 1024.0
        unit += 1
    return f"{size:.1f} {units[unit]}"


def sanitize_terminal_text(value: str) -> str:
    """Best-effort text sanitization for non-UTF Windows shells."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


@dataclass
class ErrorPayload:
    message: str
    code: Optional[str] = None
    details: Optional[str] = None
    correlation_id: Optional[str] = None
    logs_path: Optional[str] = None


def map_exception_to_payload(error: Exception, *, logs_path: Optional[Path] = None) -> ErrorPayload:
    correlation_id = str(uuid4())
    if isinstance(error, ControlPlaneError):
        details = ", ".join(f"{k}={v}" for k, v in error.details.items()) if error.details else None
        return ErrorPayload(
            message=error.user_message,
            code=error.code,
            details=details,
            correlation_id=correlation_id,
            logs_path=str(logs_path) if logs_path else None,
        )
    return ErrorPayload(
        message="Unexpected error",
        code="UNEXPECTED",
        details=str(error),
        correlation_id=correlation_id,
        logs_path=str(logs_path) if logs_path else None,
    )


class ErrorBanner(Static):
    """Small reusable banner for user-facing errors with details toggle."""

    def __init__(self, widget_id: str = "error-banner") -> None:
        super().__init__("", id=widget_id, classes="hidden")
        self._payload: Optional[ErrorPayload] = None
        self._show_details = False

    def clear(self) -> None:
        self._payload = None
        self._show_details = False
        self.update("")
        self.add_class("hidden")

    def show_error(self, payload: ErrorPayload) -> None:
        self._payload = payload
        self._show_details = False
        self.remove_class("hidden")
        self._render()

    def toggle_details(self) -> None:
        if not self._payload:
            return
        self._show_details = not self._show_details
        self._render()

    def _render(self) -> None:
        if not self._payload:
            self.update("")
            return
        lines = [f"Error: {self._payload.message}"]
        footer_parts = []
        if self._payload.code:
            footer_parts.append(f"code={self._payload.code}")
        if self._payload.correlation_id:
            footer_parts.append(f"correlation_id={self._payload.correlation_id}")
        if self._payload.logs_path:
            footer_parts.append(f"logs={self._payload.logs_path}")
        if footer_parts:
            lines.append(" | ".join(footer_parts))
        if self._show_details and self._payload.details:
            lines.append(f"Details: {self._payload.details}")
        else:
            lines.append("Press F1 for help, or use Doctor/Config quick actions.")
        self.update("\n".join(lines))

