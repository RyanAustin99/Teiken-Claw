import asyncio

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import AgentOnboardingState
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

    async def _fake_chat_messages(messages, model=None, tools=None):
        return next(responses)

    context.model_service.chat_messages = _fake_chat_messages

    hatch = _run(router.execute("hatch --name phase19-agent"))
    assert "Started runtime and opened chat session" in hatch.output

    agent = context.agent_service.get_agent("phase19-agent")
    assert agent is not None
    assert agent.profile_json is not None
    assert agent.profile_json.get("agent_display_name") == "Forge"
    assert agent.onboarding_state == AgentOnboardingState.WAITING_USER_PREFS

    memories = get_memory_store().list_memories(scope=f"agent:{agent.id}", limit=100)
    identity_mem = [m for m in memories if getattr(m, "key", None) == "identity"]
    assert identity_mem, "expected AGENT_SELF identity memory"

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
    prefs_mem = [m for m in memories_after if getattr(m, "key", None) == "user_prefs"]
    assert prefs_mem, "expected USER_PREFS memory entry"

