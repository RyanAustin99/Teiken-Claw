import asyncio

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import AgentOnboardingState, RuntimeStatus
from app.control_plane.tui.command_router import TuiCommandRouter
from app.memory.store import get_memory_store


def _run(coro):
    return asyncio.run(coro)


def test_hatch_boot_persists_identity_and_transitions_after_reply(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    responses = iter(
        [
            (
                '<tc_profile>{"agent_display_name":"Forge","agent_voice":["calm","direct"],'
                '"agent_principles":["Be useful","Be concise","Be honest"],'
                '"onboarding_intent":{"ask_user_name":true,"ask_agent_name":true,"ask_purpose":true,"ask_tone":false}}'
                "</tc_profile>\n\n"
                "Hey, what should I call you, and what should you call me?"
            ),
            "Perfect, I'm ready.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(responses)

    context.model_service.chat_messages = _fake_chat_messages

    hatch = _run(router.execute("hatch --name phase19-agent"))
    assert "Started runtime and opened chat session" in hatch.output

    agent = context.agent_service.get_agent("phase19-agent")
    assert agent is not None
    assert agent.profile_json is not None
    assert agent.profile_json.get("agent_display_name") == "Assistant"
    assert agent.onboarding_state == AgentOnboardingState.WAITING_USER_PREFS

    memories = get_memory_store().list_memories(scope=f"agent:{agent.id}", limit=100)
    display_mem = [m for m in memories if getattr(m, "key", None) == "agent_display_name"]
    assert display_mem, "expected AGENT_SELF agent_display_name memory"
    voice_mem = [m for m in memories if getattr(m, "key", None) == "agent_voice"]
    assert voice_mem, "expected AGENT_SELF agent_voice memory"
    principles_mem = [m for m in memories if getattr(m, "key", None) == "agent_principles"]
    assert principles_mem, "expected AGENT_SELF agent_principles memory"
    assert "hello, i am your agent" not in hatch.output.lower()
    assert "how can i help you today" not in hatch.output.lower()
    assert "teiken claw agent" not in hatch.output.lower()
    assert "operational identity" not in hatch.output.lower()

    reply = _run(
        router.execute(
            "chat send Call me Ryan, call yourself Forge, and your job is to automate release workflows."
        )
    )
    assert "assistant>" in reply.output

    agent_after = context.agent_service.get_agent(agent.id)
    assert agent_after is not None
    assert agent_after.is_fresh is False
    assert agent_after.onboarding_state == AgentOnboardingState.ACTIVE
    assert agent_after.agent_profile_user_name == "Ryan"
    assert "automate release workflows" in (agent_after.agent_profile_purpose or "").lower()

    memories_after = get_memory_store().list_memories(scope=f"agent:{agent.id}", limit=100)
    prefs_name = [m for m in memories_after if getattr(m, "key", None) == "user_preferred_name"]
    prefs_agent = [m for m in memories_after if getattr(m, "key", None) == "agent_name_preference"]
    prefs_purpose = [m for m in memories_after if getattr(m, "key", None) == "agent_purpose"]
    assert prefs_name, "expected USER_PREFS user_preferred_name memory entry"
    assert prefs_agent, "expected USER_PREFS agent_name_preference memory entry"
    assert prefs_purpose, "expected USER_PREFS agent_purpose memory entry"


def test_hatch_boot_synthesizes_profile_when_tc_profile_missing(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    responses = iter(
        [
            "Hey, what should I call you, and what should you call me?",
            "Sounds good to me.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(responses)

    context.model_service.chat_messages = _fake_chat_messages

    hatch = _run(router.execute("hatch --name fallback-agent"))
    assert "Started runtime and opened chat session" in hatch.output
    assert "First message boot failed" not in hatch.output

    agent = context.agent_service.get_agent("fallback-agent")
    assert agent is not None
    assert agent.status != RuntimeStatus.DEGRADED
    assert agent.degraded_reason is None
    assert agent.onboarding_state == AgentOnboardingState.WAITING_USER_PREFS
    assert agent.profile_json is not None
    assert agent.profile_json.get("agent_display_name") == "Assistant"
    assert agent.profile_json.get("agent_voice")
    assert agent.profile_json.get("agent_principles")
    assert isinstance(agent.profile_json.get("onboarding_intent"), dict)

    transcript = context.session_service.get_transcript(router.active_session_id)
    assert transcript
    assistant_messages = [item.content for item in transcript if item.role == "assistant"]
    assert assistant_messages
    assert all("<tc_profile>" not in item.lower() for item in assistant_messages)
    assert any(item.strip() for item in assistant_messages)


def test_hatch_boot_strips_self_assigned_name_from_visible_message(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    responses = iter(
        [
            (
                '<tc_profile>{"agent_display_name":"Alex","agent_voice":["calm","direct"],'
                '"agent_principles":["Be useful","Be concise","Be honest"],'
                '"onboarding_intent":{"ask_user_name":true,"ask_agent_name":true,"ask_purpose":true,"ask_tone":false}}'
                "</tc_profile>\n\n"
                "I don't have a real name, but you can call me Alex. What should I call you?"
            ),
            "Ready.",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(responses)

    context.model_service.chat_messages = _fake_chat_messages
    hatch = _run(router.execute("hatch --name no-name-invent"))
    lowered = hatch.output.lower()
    assert "you can call me alex" not in lowered
    assert "choose what to call me" in lowered


def test_hatch_boot_uses_neutral_fallback_when_rewrite_still_fails(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    responses = iter(
        [
            (
                '<tc_profile>{"agent_display_name":"Alex","agent_voice":["calm","direct"],'
                '"agent_principles":["Be useful","Be concise","Be honest"],'
                '"onboarding_intent":{"ask_user_name":true,"ask_agent_name":true,"ask_purpose":true,"ask_tone":false}}'
                "</tc_profile>\n\n"
                "In this scenario:\n1) First\n2) Second"
            ),
            "session scenario pretend roleplay",
        ]
    )

    async def _fake_chat_messages(messages, model=None, tools=None, options=None):
        return next(responses)

    context.model_service.chat_messages = _fake_chat_messages
    hatch = _run(router.execute("hatch --name fallback-lint"))
    lowered = hatch.output.lower()
    assert "first-message boot failed" not in lowered
    assert "what should i call you" in lowered
