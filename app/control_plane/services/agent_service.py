"""Agent registry service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentRecord, RunnerType, RuntimeStatus
from app.control_plane.infra.agent_repo import AgentRepository


class AgentService:
    """Create/list/update/delete agents with persistence."""

    def __init__(self, repo: AgentRepository, workspace_root: Path) -> None:
        self.repo = repo
        self.workspace_root = workspace_root
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create_agent(
        self,
        name: str,
        description: Optional[str] = None,
        model: Optional[str] = None,
        tool_profile: str = "safe",
        workspace_path: Optional[str] = None,
        runner_type: Optional[RunnerType] = None,
        auto_restart: bool = True,
        max_queue_depth: Optional[int] = None,
        tool_profile_version: Optional[str] = None,
    ) -> AgentRecord:
        if not name.strip():
            raise ValidationError("Agent name is required")
        if self.repo.get_by_name(name):
            raise ValidationError(f"Agent name already exists: {name}")
        workspace = Path(workspace_path) if workspace_path else self.workspace_root / name
        workspace.mkdir(parents=True, exist_ok=True)
        return self.repo.create(
            name=name,
            description=description,
            model=model,
            tool_profile=tool_profile,
            workspace_path=str(workspace),
            runner_type=runner_type,
            auto_restart=auto_restart,
            max_queue_depth=max_queue_depth,
            tool_profile_version=tool_profile_version,
        )

    def list_agents(self) -> List[AgentRecord]:
        return self.repo.list()

    def get_agent(self, agent_id_or_name: str) -> Optional[AgentRecord]:
        agent = self.repo.get(agent_id_or_name)
        if agent:
            return agent
        return self.repo.get_by_name(agent_id_or_name)

    def update_agent(self, agent_id: str, patch: Dict[str, object]) -> AgentRecord:
        updated = self.repo.update(agent_id, patch)
        if not updated:
            raise ValidationError(f"Unknown agent: {agent_id}")
        return updated

    def delete_agent(self, agent_id: str) -> bool:
        return self.repo.delete(agent_id)

    def set_default_agent(self, agent_id: str) -> None:
        if not self.repo.get(agent_id):
            raise ValidationError(f"Unknown agent: {agent_id}")
        self.repo.set_default(agent_id)

    def set_status(
        self,
        agent_id: str,
        status: RuntimeStatus,
        last_error: Optional[str] = None,
    ) -> AgentRecord:
        patch: Dict[str, object] = {
            "status": status.value,
            "last_seen_at": datetime.utcnow().isoformat(),
            "last_error": last_error,
        }
        updated = self.repo.update(agent_id, patch)
        if not updated:
            raise ValidationError(f"Unknown agent: {agent_id}")
        return updated

