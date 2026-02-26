"""Navigation routes and labels for control-plane TUI screens."""

from __future__ import annotations

from enum import Enum


class Route(str, Enum):
    BOOT = "boot"
    DASHBOARD = "dashboard"
    WIZARD = "wizard"
    MODELS = "models"
    AGENTS = "agents"
    HATCH = "hatch"
    CHAT = "chat"
    STATUS = "status"
    DOCTOR = "doctor"
    LOGS = "logs"
    HELP = "help"


ROUTE_TITLES: dict[Route, str] = {
    Route.BOOT: "Boot",
    Route.DASHBOARD: "Dashboard",
    Route.WIZARD: "Setup Wizard",
    Route.MODELS: "Models",
    Route.AGENTS: "Agents",
    Route.HATCH: "Hatch Agent",
    Route.CHAT: "Chat",
    Route.STATUS: "Status",
    Route.DOCTOR: "Doctor",
    Route.LOGS: "Logs",
    Route.HELP: "Help",
}

