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
