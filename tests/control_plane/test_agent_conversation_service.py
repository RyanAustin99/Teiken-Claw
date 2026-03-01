import asyncio
import json
from pathlib import Path

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import AgentOnboardingState
from app.control_plane.domain.models import OnboardingStatus
from app.memory.onboarding_extractor import extract_onboarding_prefs
from app.memory.store import get_memory_store


def _run(coro):
    return asyncio.run(coro)


def test_onboarding_reply_extraction_transitions_agent_active(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="onboard-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_agent(
        agent.id,
        {
            "is_fresh": True,
            "onboarding_state": AgentOnboardingState.WAITING_USER_PREFS,
            "profile_json": {
                "agent_display_name": "Onboard",
                "agent_voice": ["calm", "direct"],
                "agent_principles": ["be useful", "be concise", "be honest"],
            },
        },
    )
    context.session_service.append_assistant_message(
        session.id,
        "Hey, what should I call you and what should I call myself?",
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return "Perfect, I’m ready."

    context.model_service.chat_messages = _fake_chat_messages
    response = _run(
        context.conversation_service.generate_response(
            agent.id,
            session.id,
            "Call me Ryan, call yourself Forge, and your job is to automate my workflow.",
        )
    )
    assert "ready" in response.lower()

    done_session = context.session_service.get_session(session.id)
    assert done_session is not None
    assert done_session.onboarding_status == OnboardingStatus.COMPLETE

    done_agent = context.agent_service.get_agent(agent.id)
    assert done_agent is not None
    assert done_agent.is_fresh is False
    assert done_agent.onboarding_state == AgentOnboardingState.ACTIVE
    assert done_agent.onboarding_complete is True
    assert done_agent.agent_profile_user_name == "Ryan"
    assert done_agent.agent_profile_agent_name == "Forge"
    assert "automate my workflow" in (done_agent.agent_profile_purpose or "").lower()

    memories = get_memory_store().list_memories(scope=f"agent:{agent.id}", limit=100)
    prefs_user = [m for m in memories if getattr(m, "key", None) == "user_preferred_name"]
    prefs_agent = [m for m in memories if getattr(m, "key", None) == "agent_name_preference"]
    prefs_purpose = [m for m in memories if getattr(m, "key", None) == "agent_purpose"]
    assert prefs_user, "expected USER_PREFS user_preferred_name record"
    assert prefs_agent, "expected USER_PREFS agent_name_preference record"
    assert prefs_purpose, "expected USER_PREFS agent_purpose record"


def test_conversation_rewrites_third_person_self_reference(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="first-person-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_agent(
        agent.id,
        {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE},
    )

    outputs = iter(["this agent can help you.", "I can help you."])

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(outputs)

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response(agent.id, session.id, "hello"))
    assert "i can help you" in result.lower()
    assert "this agent" not in result.lower()


def test_onboarding_extractor_supports_casual_name_and_purpose_phrasing():
    extracted = extract_onboarding_prefs(
        user_text="You can call me Ryan, call yourself Forge, and I want you to automate my releases.",
        last_assistant_text="",
        agent_profile_json={"agent_display_name": "OldName"},
    )
    assert extracted["user_preferred_name"] == "Ryan"
    assert extracted["agent_name_preference"] == "Forge"
    assert "automate my releases" in (extracted["agent_purpose"] or "").lower()


def test_onboarding_extractor_captures_profanity_preference():
    extracted = extract_onboarding_prefs(
        user_text="You can swear if you want, keep it casual.",
        last_assistant_text="",
        agent_profile_json={"agent_display_name": "OldName"},
    )
    assert extracted["profanity_level"] == "allowed"
    assert extracted["tone_preference"] == "casual"


def test_llm_onboarding_fallback_rejects_low_confidence_fields(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="low-confidence-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_agent(
        agent.id,
        {
            "is_fresh": True,
            "onboarding_state": AgentOnboardingState.WAITING_USER_PREFS,
            "profile_json": {"agent_display_name": "Assistant"},
        },
    )
    context.session_service.append_assistant_message(session.id, "What should I call you?")

    outputs = iter(
        [
            json.dumps(
                {
                    "user_preferred_name": "Ryan",
                    "agent_name_preference": None,
                    "agent_purpose": None,
                    "tone_preference": None,
                    "profanity_level": None,
                    "confidence": {
                        "user_preferred_name": 0.3,
                        "agent_name_preference": 0.0,
                        "agent_purpose": 0.0,
                        "tone_preference": 0.0,
                        "profanity_level": 0.0,
                    },
                }
            ),
            "Acknowledged.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(outputs)

    context.model_service.chat_messages = _fake_chat_messages
    _run(context.conversation_service.generate_response(agent.id, session.id, "yeah sure"))

    after = context.agent_service.get_agent(agent.id)
    assert after is not None
    assert after.is_fresh is True
    assert after.onboarding_state == AgentOnboardingState.WAITING_USER_PREFS


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
    context.agent_service.update_agent(agent.id, {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE})
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    captured = {}

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
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
    assert "Style Profile" in system_prompt
    assert "Skills" in system_prompt
    assert "hatched Teiken Claw agent" not in system_prompt


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
    context.agent_service.update_agent(agent.id, {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE})
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

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
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
    context.agent_service.update_agent(agent.id, {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE})
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return '```bash\nfiles.write("hello.md", "Hello")\n```'

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response_with_tools(agent.id, session.id, "Write hello"))

    assert "files.write" in result.response
    assert not result.tool_events
    assert not (Path(agent.workspace_path) / "hello.md").exists()


def test_conversation_denies_disallowed_tool_profile(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="safe-agent", tool_profile="safe")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_onboarding_profile(
        agent.id,
        user_name="Ryan",
        preferred_agent_name="Safe",
        purpose="Test denial",
        complete=True,
    )
    context.agent_service.update_agent(agent.id, {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE})
    context.session_service.update_onboarding(session.id, status=OnboardingStatus.COMPLETE, step=3)

    outputs = iter(
        [
            (
                "<TEIKEN_TOOL_CALL>\n"
                '{"id":"tc_1","tool":"files.write","args":{"path":"hello.md","content":"Hello"}}\n'
                "</TEIKEN_TOOL_CALL>"
            ),
            "I cannot write files with the current safe tool profile.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(outputs)

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response_with_tools(agent.id, session.id, "Create hello.md"))

    assert result.tool_events
    assert result.tool_events[0].ok is False
    assert result.tool_events[0].error["type"] == "not_allowed"
    assert not (Path(agent.workspace_path) / "hello.md").exists()


def test_conversation_rewrites_meta_identity_language(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="meta-guard-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_agent(agent.id, {"is_fresh": False, "onboarding_state": AgentOnboardingState.ACTIVE})

    outputs = iter(
        [
            "My operational identity is Alex. Let's keep it respectful.",
            "I can help with that. What do you want to tackle first?",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(outputs)

    context.model_service.chat_messages = _fake_chat_messages
    result = _run(context.conversation_service.generate_response(agent.id, session.id, "hey"))
    lowered = result.lower()
    assert "operational identity" not in lowered
    assert "keep it respectful" not in lowered


def test_onboarding_waiting_injects_onboarding_system_block(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="onboarding-block-agent")
    session = context.session_service.new_session(agent.id, title="chat")
    context.agent_service.update_agent(
        agent.id,
        {"is_fresh": True, "onboarding_state": AgentOnboardingState.WAITING_USER_PREFS},
    )

    captured = {}

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        captured["messages"] = messages
        return "What should I call you, and what do you want to call me?"

    context.model_service.chat_messages = _fake_chat_messages
    _run(context.conversation_service.generate_response(agent.id, session.id, "whaddup my guy"))

    system_messages = [m["content"] for m in captured["messages"] if m["role"] == "system"]
    assert any("Onboarding is still in progress" in msg for msg in system_messages)
