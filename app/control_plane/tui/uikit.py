"""Reusable widgets and formatting helpers for control-plane TUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from textual.widgets import Static


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    LOADING = "loading"


HEALTH_STYLE = {
    HealthState.HEALTHY: ("✅", "status-healthy"),
    HealthState.DEGRADED: ("⚠️", "status-degraded"),
    HealthState.FAILED: ("❌", "status-failed"),
    HealthState.LOADING: ("⏳", "status-loading"),
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


@dataclass
class ErrorPayload:
    message: str
    code: Optional[str] = None
    details: Optional[str] = None


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
        if self._payload.code:
            lines.append(f"Code: {self._payload.code}")
        if self._show_details and self._payload.details:
            lines.append(f"Details: {self._payload.details}")
        else:
            lines.append("Press F1 for help, or use Doctor/Config quick actions.")
        self.update("\n".join(lines))

