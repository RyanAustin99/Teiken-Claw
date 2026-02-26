import asyncio

import pytest

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.errors import ValidationError


def _run(coro):
    return asyncio.run(coro)


def test_runtime_supervisor_chat_requires_valid_agent(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))

    with pytest.raises(ValidationError):
        _run(context.runtime_supervisor.chat(agent_id="missing", session_id="missing", message="hello"))


def test_runtime_supervisor_chat_uses_conversation_service_path(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="chat-agent")
    session = context.session_service.new_session(agent.id, title="chat")

    calls = {"conversation": 0}

    async def _fake_generate_response(agent_id: str, session_id: str, user_message: str) -> str:
        calls["conversation"] += 1
        assert agent_id == agent.id
        assert session_id == session.id
        return "from-conversation-service"

    async def _fail_direct_chat(*_args, **_kwargs):  # pragma: no cover - defensive assertion path
        raise AssertionError("Direct ModelService.chat path should not be used")

    context.conversation_service.generate_response = _fake_generate_response
    context.model_service.chat = _fail_direct_chat

    response = _run(context.runtime_supervisor.chat(agent_id=agent.id, session_id=session.id, message="hello"))
    assert response == "from-conversation-service"
    assert calls["conversation"] == 1
