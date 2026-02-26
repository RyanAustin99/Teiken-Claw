import asyncio

import pytest

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.errors import ValidationError
from app.control_plane.tui.command_router import TuiCommandRouter


def _run(coro):
    return asyncio.run(coro)


def test_router_accepts_teiken_prefix(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    result = _run(router.execute("teiken status"))

    assert "Dev server:" in result.output
    assert not result.exit_app


async def _run_lifecycle(router: TuiCommandRouter):
    hatch = await router.execute("hatch --name tui-agent --no-start")
    listed = await router.execute("agents list")
    started = await router.execute("agents start tui-agent")
    stopped = await router.execute("agents stop tui-agent")
    return hatch, listed, started, stopped


def test_router_hatch_agents_and_lifecycle(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    hatch, listed, started, stopped = _run(_run_lifecycle(router))
    assert "Hatched agent:" in hatch.output
    assert "tui-agent" in listed.output
    assert "Started tui-agent:" in started.output
    assert "Stopped tui-agent:" in stopped.output


def test_router_unknown_command_without_chat_raises(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    with pytest.raises(ValidationError):
        _run(router.execute("hello from ui"))


def test_router_chat_receipts_command(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)
    hatch = _run(router.execute("hatch --name receipts-agent"))
    assert "Started runtime and opened chat session" in hatch.output

    async def _fake_chat(agent_id: str, session_id: str, message: str) -> str:
        context.session_service.append_assistant_message(
            session_id=session_id,
            content='<TEIKEN_TOOL_RESULT>{"id":"tc_1","tool":"files.write","ok":true,"result":{"path":"hello.md","bytes":5}}</TEIKEN_TOOL_RESULT>',
            tool_name="files.write",
            tool_ok=True,
            tool_elapsed_ms=10,
        )
        return "done"

    context.runtime_supervisor.chat = _fake_chat
    _run(router.execute("chat send write hello"))
    receipts = _run(router.execute("chat receipts --limit 5"))
    assert "[TOOL] files.write OK -> hello.md (5 bytes)" in receipts.output
