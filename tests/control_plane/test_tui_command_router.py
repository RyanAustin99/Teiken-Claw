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
