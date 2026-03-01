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
        tool_profile: str = "balanced",
        workspace_path: Optional[str] = None,
        runner_type: Optional[RunnerType] = None,
        auto_restart: bool = True,
        max_queue_depth: Optional[int] = None,
        tool_profile_version: Optional[str] = None,
        prompt_template_version: str = "1.0.0",
        allow_dangerous_override: bool = False,
        default_soul: str = "teiken_claw_agent@1.5.0",
        default_mode: str = "builder@1.5.0",
    ) -> AgentRecord:
        if not name.strip():
            raise ValidationError("Agent name is required")
        if self.repo.get_by_name(name):
            raise ValidationError(f"Agent name already exists: {name}")
        self._validate_tool_profile(tool_profile, allow_dangerous_override=allow_dangerous_override)
        workspace = Path(workspace_path) if workspace_path else self.workspace_root / name
        try:
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationError(
                "Could not create agent workspace. Use a different name or workspace path.",
                details={"workspace_path": str(workspace), "error": str(exc)},
            ) from exc
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
            prompt_template_version=prompt_template_version,
            default_soul=default_soul,
            default_mode=default_mode,
        )

    def list_agents(self) -> List[AgentRecord]:
        return self.repo.list()

    def get_agent(self, agent_id_or_name: str) -> Optional[AgentRecord]:
        agent = self.repo.get(agent_id_or_name)
        if agent:
            return agent
        return self.repo.get_by_name(agent_id_or_name)

    def update_agent(self, agent_id: str, patch: Dict[str, object]) -> AgentRecord:
        if "tool_profile" in patch:
            self._validate_tool_profile(
                str(patch["tool_profile"]),
                allow_dangerous_override=bool(patch.pop("_allow_dangerous_override", False)),
            )
        updated = self.repo.update(agent_id, patch)
        if not updated:
            raise ValidationError(f"Unknown agent: {agent_id}")
        return updated

    def update_onboarding_profile(
        self,
        agent_id: str,
        *,
        user_name: Optional[str] = None,
        preferred_agent_name: Optional[str] = None,
        purpose: Optional[str] = None,
        complete: Optional[bool] = None,
    ) -> AgentRecord:
        patch: Dict[str, object] = {}
        if user_name is not None:
            patch["agent_profile_user_name"] = user_name
        if preferred_agent_name is not None:
            patch["agent_profile_agent_name"] = preferred_agent_name
        if purpose is not None:
            patch["agent_profile_purpose"] = purpose
        if complete is not None:
            patch["onboarding_complete"] = complete
            patch["onboarding_updated_at"] = datetime.utcnow().isoformat()
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

    @staticmethod
    def _validate_tool_profile(tool_profile: str, allow_dangerous_override: bool) -> None:
        normalized = tool_profile.strip().lower()
        allowed = {"safe", "balanced", "dangerous"}
        if normalized not in allowed:
            raise ValidationError(f"Unsupported tool profile: {tool_profile}")
        if normalized == "dangerous" and not allow_dangerous_override:
            raise ValidationError(
                "Dangerous tool profile requires explicit override confirmation.",
                details={"hint": "Pass --allow-dangerous and enable dangerous_tools_enabled in config."},
            )
