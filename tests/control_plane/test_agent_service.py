import pytest

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

