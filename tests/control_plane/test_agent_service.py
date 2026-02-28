import pytest
from pathlib import Path

from app.control_plane.domain.errors import ValidationError
from app.control_plane.infra.agent_repo import AgentRepository
from app.control_plane.services.agent_service import AgentService


def test_dangerous_profile_requires_override(tmp_path):
    repo = AgentRepository(tmp_path / "state.db")
    service = AgentService(repo=repo, workspace_root=tmp_path / "workspace")

    with pytest.raises(ValidationError):
        service.create_agent(name="agent-a", tool_profile="dangerous")

    created = service.create_agent(
        name="agent-b",
        tool_profile="dangerous",
        allow_dangerous_override=True,
    )
    assert created.tool_profile == "dangerous"


def test_agent_service_defaults_to_balanced_profile(tmp_path):
    repo = AgentRepository(tmp_path / "state.db")
    service = AgentService(repo=repo, workspace_root=tmp_path / "workspace")
    created = service.create_agent(name="agent-default")
    assert created.tool_profile == "balanced"


def test_create_agent_workspace_oserror_maps_to_validation_error(tmp_path, monkeypatch):
    repo = AgentRepository(tmp_path / "state.db")
    service = AgentService(repo=repo, workspace_root=tmp_path / "workspace")

    original_mkdir = Path.mkdir

    def _boom(self, *args, **kwargs):
        if str(self).endswith("bad-agent"):
            raise OSError("Access is denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _boom)

    with pytest.raises(ValidationError, match="Could not create agent workspace"):
        service.create_agent(name="bad-agent")

