import asyncio
from pathlib import Path

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import OnboardingStatus


def _run(coro):
    return asyncio.run(coro)


def test_onboarding_state_machine_and_profile_persistence(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="onboard-agent")
    session = context.session_service.new_session(agent.id, title="chat")

    first = _run(context.conversation_service.generate_response(agent.id, session.id, "hello"))
    assert "what name should i call you" in first.lower()
    session = context.session_service.get_session(session.id)
    assert session is not None
    assert session.onboarding_status == OnboardingStatus.IN_PROGRESS
    assert session.onboarding_step == 1

    second = _run(context.conversation_service.generate_response(agent.id, session.id, "Ryan"))
    assert "what would you like this agent to be called" in second.lower()
    agent = context.agent_service.get_agent(agent.id)
    assert agent is not None
    assert agent.agent_profile_user_name == "Ryan"

    third = _run(context.conversation_service.generate_response(agent.id, session.id, "Forge"))
    assert "primary purpose" in third.lower()
    renamed = context.agent_service.get_agent(agent.id)
    assert renamed is not None
    assert renamed.name == "Forge"

    fourth = _run(context.conversation_service.generate_response(agent.id, session.id, "Automation and debugging"))
    assert "onboarding complete" in fourth.lower()
    done_agent = context.agent_service.get_agent(agent.id)
    assert done_agent is not None
    assert done_agent.onboarding_complete is True
    assert done_agent.agent_profile_purpose == "Automation and debugging"
    done_session = context.session_service.get_session(session.id)
    assert done_session is not None
    assert done_session.onboarding_status == OnboardingStatus.COMPLETE


def test_conversation_uses_system_prompt_after_onboarding(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="prompt-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_onboarding_profile(
        agent.id,
        user_name="Ryan",
        preferred_agent_name="PromptAgent",
        purpose="Ship production fixes quickly",
        complete=True,
    )
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    captured = {}

    async def _fake_chat_messages(messages, model=None, tools=None):
        captured["messages"] = messages
        captured["model"] = model
        return "ok-response"

    context.model_service.chat_messages = _fake_chat_messages
    context.session_service.append_user_message(session.id, "Give me a plan")

    response = _run(context.conversation_service.generate_response(agent.id, session.id, "Give me a plan"))
    assert response == "ok-response"
    assert captured["messages"][0]["role"] == "system"
    system_prompt = captured["messages"][0]["content"]
    assert "Workspace" in system_prompt
    assert "Tool Profile" in system_prompt
    assert "Skills" in system_prompt


def test_conversation_executes_tool_envelope_and_writes_file(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="writer", tool_profile="balanced")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_onboarding_profile(
        agent.id,
        user_name="Ryan",
        preferred_agent_name="Writer",
        purpose="Create files",
        complete=True,
    )
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    outputs = iter(
        [
            (
                "<TEIKEN_TOOL_CALL>\n"
                '{"id":"tc_1","tool":"files.write","args":{"path":"hello.md","content":"Hello"}}\n'
                "</TEIKEN_TOOL_CALL>"
            ),
            "Done. I created hello.md in your workspace.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None):
        return next(outputs)

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response_with_tools(agent.id, session.id, "Create hello.md"))

    assert "created hello.md" in result.response.lower()
    assert result.tool_events
    assert result.tool_events[0].ok is True
    assert result.tool_events[0].tool == "files.write"
    written_path = Path(agent.workspace_path) / "hello.md"
    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == "Hello"


def test_conversation_does_not_execute_markdown_code_fence_tool_text(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="fence-test", tool_profile="balanced")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_onboarding_profile(
        agent.id,
        user_name="Ryan",
        preferred_agent_name="Fence",
        purpose="Test",
        complete=True,
    )
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    async def _fake_chat_messages(messages, model=None, tools=None):
        return '```bash\nfiles.write("hello.md", "Hello")\n```'

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response_with_tools(agent.id, session.id, "Write hello"))

    assert "files.write" in result.response
    assert not result.tool_events
    assert not (Path(agent.workspace_path) / "hello.md").exists()
