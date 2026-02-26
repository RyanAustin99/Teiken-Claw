"""Runner abstraction for in-process and subprocess agent runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.control_plane.domain.models import RuntimeStatus, RunnerType


@dataclass
class RunnerStatus:
    agent_id: str
    status: RuntimeStatus
    runner_type: RunnerType
    queued: int = 0
    overflow_count: int = 0
    last_error: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None


class AgentRunner(ABC):
    """Abstract runner API used by RuntimeSupervisor."""

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, message: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> RunnerStatus:
        raise NotImplementedError

