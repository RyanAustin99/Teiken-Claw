"""Runtime registry view used by install-time boot UI."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class AgentSnapshot:
    """Compact runtime view for boot dashboard tables."""

    agent_id: str
    kind: str
    status: str
    current_task: str = ""
    queue_depth: int = 0
    last_heartbeat_s: float = 0.0
    notes: str = ""


class AgentRegistry:
    """Interface for terminal boot status displays."""

    def snapshot(self) -> List[AgentSnapshot]:
        raise NotImplementedError


class InMemoryAgentRegistry(AgentRegistry):
    """Thread-safe registry used for local boot dashboards."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: Dict[str, AgentSnapshot] = {}

    def upsert(self, snap: AgentSnapshot) -> None:
        with self._lock:
            self._agents[snap.agent_id] = snap

    def heartbeat(
        self,
        agent_id: str,
        *,
        kind: str,
        status: str,
        current_task: str = "",
        queue_depth: int = 0,
        notes: str = "",
    ) -> None:
        now = time.time()
        self.upsert(
            AgentSnapshot(
                agent_id=agent_id,
                kind=kind,
                status=status,
                current_task=current_task,
                queue_depth=queue_depth,
                last_heartbeat_s=now,
                notes=notes,
            )
        )

    def snapshot(self) -> List[AgentSnapshot]:
        with self._lock:
            return sorted(self._agents.values(), key=lambda item: (item.kind, item.agent_id))
