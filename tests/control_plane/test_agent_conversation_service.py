import asyncio

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
