import asyncio

import pytest

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.files_tool import FilesWriteSubtool
from app.tools.mock_tools import EchoTool
from app.tools.protocol import ToolCall
from app.tools.registry import ToolRegistry


class SleepTool(Tool):
    @property
    def name(self) -> str:
        return "sleepy"

    @property
    def description(self) -> str:
        return "Sleep tool"

    @property
    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": "sleepy",
                "description": "sleep",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }

    async def execute(self, **kwargs):
        await asyncio.sleep(0.2)
        return ToolResult.success("ok")


class FakeWebTool(Tool):
    @property
    def name(self) -> str:
        return "web"

    @property
    def description(self) -> str:
        return "fake web"

    @property
    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": "web",
                "description": "fake web",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }

    async def execute(self, **kwargs):
        return ToolResult.success("web-ok")


@pytest.mark.asyncio
async def test_executor_allows_safe_echo():
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="safe")
    call = ToolCall(id="tc_1", tool="echo", args={"message": "hello"})
    results = await executor.execute_calls([call], ctx=ctx)
    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].tool == "echo"


@pytest.mark.asyncio
async def test_executor_denies_disallowed_profile_tool(tmp_path):
    registry = ToolRegistry()
    registry.register(FilesWriteSubtool(policy=ToolPolicy(enabled=True)))
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="safe", workspace_root=tmp_path)
    call = ToolCall(id="tc_1", tool="files.write", args={"path": "x.md", "content": "x"})
    results = await executor.execute_calls([call], ctx=ctx)
    assert results[0].ok is False
    assert results[0].error["type"] == "not_allowed"
    assert not (tmp_path / "x.md").exists()


@pytest.mark.asyncio
async def test_executor_denies_when_tools_paused():
    class _Paused:
        @staticmethod
        def is_tools_paused() -> bool:
            return True

    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="dangerous", control_state_manager=_Paused())
    call = ToolCall(id="tc_1", tool="echo", args={"message": "hello"})
    results = await executor.execute_calls([call], ctx=ctx)
    assert results[0].ok is False
    assert "paused" in results[0].error["message"]


@pytest.mark.asyncio
async def test_executor_timeout():
    registry = ToolRegistry()
    registry.register(SleepTool(policy=ToolPolicy(timeout_sec=5.0)))
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="dangerous", timeout_sec=0.01)
    call = ToolCall(id="tc_1", tool="sleepy", args={})
    results = await executor.execute_calls([call], ctx=ctx)
    assert results[0].ok is False
    assert results[0].error["type"] == "timeout"


@pytest.mark.asyncio
async def test_executor_propagates_structured_tool_error(tmp_path):
    registry = ToolRegistry()
    registry.register(FilesWriteSubtool(policy=ToolPolicy(enabled=True)))
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="balanced", workspace_root=tmp_path)
    call = ToolCall(id="tc_1", tool="files.write", args={"path": "../x.md", "content": "x"})
    results = await executor.execute_calls([call], ctx=ctx)
    assert results[0].ok is False
    assert results[0].error["type"] == "err_path_traversal"
    assert results[0].error["code"] == "ERR_PATH_TRAVERSAL"
    assert results[0].error["legacy_code"] == "PATH_SECURITY_ERROR"


@pytest.mark.asyncio
async def test_executor_accepts_legacy_web_search_alias_for_safe_profile():
    registry = ToolRegistry()
    registry.register(FakeWebTool())
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(tool_profile="safe")
    call = ToolCall(id="tc_1", tool="web.search", args={})
    results = await executor.execute_calls([call], ctx=ctx)
    assert results[0].ok is True
    assert results[0].tool == "web"
