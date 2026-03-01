from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.ollama_client import ChatMessage, ChatResponse
from app.agent.runtime import AgentRuntime
from app.queue.jobs import Job, JobPriority, JobSource, JobType
from app.tools.registry import ToolRegistry
from app.tools import register_production_tools


@pytest.mark.asyncio
async def test_agent_runtime_executes_envelope_tool_calls_in_scheduler_mode(tmp_path):
    ollama = AsyncMock()
    ollama.chat.side_effect = [
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(
                role="assistant",
                content=(
                    '<TEIKEN_TOOL_CALL>{"id":"tc_1","tool":"files.write","args":{"path":"hello.md","content":"Hello"}}'
                    "</TEIKEN_TOOL_CALL>"
                ),
            ),
            done=True,
        ),
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(role="assistant", content="Done."),
            done=True,
        ),
    ]

    registry = ToolRegistry()
    register_production_tools(registry)
    context_builder = MagicMock()
    context_builder.build_with_user_message.return_value = [{"role": "user", "content": "write file"}]
    runtime = AgentRuntime(
        ollama_client=ollama,
        tool_registry=registry,
        context_builder=context_builder,
        max_tool_turns=4,
    )
    job = Job(
        source=JobSource.SCHEDULER,
        type=JobType.SCHEDULED_TASK,
        priority=JobPriority.SCHEDULED,
        chat_id="scheduler",
        payload={
            "text": "Create hello.md",
            "tool_profile": "balanced",
            "workspace_root": str(tmp_path),
            "scheduler_job_id": "job-1",
            "scheduler_run_id": "run-1",
        },
    )

    result = await runtime.run(job)
    assert result.ok is True
    assert (tmp_path / "hello.md").exists()
    assert (tmp_path / "hello.md").read_text(encoding="utf-8") == "Hello"
    assert any(item.get("tool") == "files.write" and item.get("ok") for item in result.tool_results)


@pytest.mark.asyncio
async def test_agent_runtime_ignores_code_fence_pseudo_calls(tmp_path):
    ollama = AsyncMock()
    ollama.chat.return_value = ChatResponse(
        model="llama3.2",
        message=ChatMessage(role="assistant", content='```bash\nfiles.write("hello.md","Hello")\n```'),
        done=True,
    )
    registry = ToolRegistry()
    register_production_tools(registry)
    context_builder = MagicMock()
    context_builder.build_with_user_message.return_value = [{"role": "user", "content": "write file"}]
    runtime = AgentRuntime(ollama_client=ollama, tool_registry=registry, context_builder=context_builder, max_tool_turns=2)
    job = Job(
        source=JobSource.SCHEDULER,
        type=JobType.SCHEDULED_TASK,
        priority=JobPriority.SCHEDULED,
        chat_id="scheduler",
        payload={
            "text": "Create hello.md",
            "tool_profile": "balanced",
            "workspace_root": str(tmp_path),
        },
    )

    result = await runtime.run(job)
    assert result.ok is True
    assert not (tmp_path / "hello.md").exists()
    assert result.tool_results == []


@pytest.mark.asyncio
async def test_agent_runtime_denies_disallowed_tool_profile(tmp_path):
    ollama = AsyncMock()
    ollama.side_effect = None
    ollama.chat.side_effect = [
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(
                role="assistant",
                content='<TEIKEN_TOOL_CALL>{"id":"tc_1","tool":"files.write","args":{"path":"hello.md","content":"Hello"}}</TEIKEN_TOOL_CALL>',
            ),
            done=True,
        ),
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(role="assistant", content="Cannot perform that action."),
            done=True,
        ),
    ]
    registry = ToolRegistry()
    register_production_tools(registry)
    context_builder = MagicMock()
    context_builder.build_with_user_message.return_value = [{"role": "user", "content": "write file"}]
    runtime = AgentRuntime(ollama_client=ollama, tool_registry=registry, context_builder=context_builder, max_tool_turns=3)
    job = Job(
        source=JobSource.SCHEDULER,
        type=JobType.SCHEDULED_TASK,
        priority=JobPriority.SCHEDULED,
        chat_id="scheduler",
        payload={
            "text": "Create hello.md",
            "tool_profile": "safe",
            "workspace_root": str(tmp_path),
        },
    )

    result = await runtime.run(job)
    assert result.ok is True
    assert not (tmp_path / "hello.md").exists()
    assert any(item.get("tool") == "files.write" and item.get("ok") is False for item in result.tool_results)


@pytest.mark.asyncio
async def test_agent_runtime_boot_rewrites_once_when_lint_fails():
    ollama = AsyncMock()
    ollama.chat.side_effect = [
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(
                role="assistant",
                content=(
                    '<tc_profile>{"agent_display_name":"Forge","agent_voice":["calm"],'
                    '"agent_principles":["Be useful"]}</tc_profile>\n\n'
                    "In this scenario, how can I assist you today?"
                ),
            ),
            done=True,
        ),
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(role="assistant", content="Hey, what should I call you, and what would you like to call me?"),
            done=True,
        ),
    ]
    runtime = AgentRuntime(ollama_client=ollama, tool_registry=ToolRegistry(), context_builder=MagicMock())
    job = Job(
        source=JobSource.SCHEDULER,
        type=JobType.SYSTEM_EVENT,
        priority=JobPriority.SCHEDULED,
        chat_id="scheduler",
        payload={"event_subtype": "HATCH_BOOT"},
    )
    result = await runtime.run(job)
    assert result.ok is True
    assert "what should i call you" in result.response.lower()
    assert result.metadata.get("tc_profile_parsed") is True


@pytest.mark.asyncio
async def test_agent_runtime_boot_uses_fallback_after_failed_rewrite():
    ollama = AsyncMock()
    ollama.chat.side_effect = [
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(role="assistant", content="In this scenario:\n1) First\n2) Second"),
            done=True,
        ),
        ChatResponse(
            model="llama3.2",
            message=ChatMessage(role="assistant", content="session scenario pretend roleplay"),
            done=True,
        ),
    ]
    runtime = AgentRuntime(ollama_client=ollama, tool_registry=ToolRegistry(), context_builder=MagicMock())
    job = Job(
        source=JobSource.SCHEDULER,
        type=JobType.SYSTEM_EVENT,
        priority=JobPriority.SCHEDULED,
        chat_id="scheduler",
        payload={"event_subtype": "HATCH_BOOT"},
    )
    result = await runtime.run(job)
    assert result.ok is True
    assert result.response == "Hey, what should I call you, and what would you like to call me?"
    assert result.metadata.get("boot_fallback_used") is True
