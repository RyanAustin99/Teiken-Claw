import asyncio

import pytest

pytest.importorskip("textual")

from app.control_plane.bootstrap import build_context
from app.control_plane.tui.screens.agents import AgentsScreen
from app.control_plane.tui.screens.chat import ChatScreen


def _run(coro):
    return asyncio.run(coro)


class _DummyTable:
    def __init__(self):
        self.cursor_row = 0
        self.row_count = 1
        self.moved = None

    def move_cursor(self, row: int, column: int) -> None:
        self.moved = (row, column)


class _DummyHint:
    def __init__(self):
        self.value = ""

    def update(self, value: str) -> None:
        self.value = value


def test_agents_delete_path_handles_cleanup_warning_without_crash(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="ui-delete-warn")

    screen = AgentsScreen(context)
    screen.table = _DummyTable()
    screen.hint = _DummyHint()
    screen._selected_agent = lambda: agent
    screen.refresh_data = lambda: asyncio.sleep(0)

    async def _delete(_agent_id: str) -> bool:
        return True

    context.runtime_supervisor.delete_agent = _delete
    context.runtime_supervisor.get_last_error = lambda _agent_id: "session_cleanup_failed:db locked"

    _run(screen.handle_primary_action("agents-delete"))
    assert "Delete completed with warnings" in screen.hint.value


def test_agents_delete_path_updates_hint_on_success(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="ui-delete-ok")

    screen = AgentsScreen(context)
    screen.table = _DummyTable()
    screen.hint = _DummyHint()
    screen._selected_agent = lambda: agent
    screen.refresh_data = lambda: asyncio.sleep(0)

    async def _delete(_agent_id: str) -> bool:
        return True

    context.runtime_supervisor.delete_agent = _delete
    context.runtime_supervisor.get_last_error = lambda _agent_id: None

    _run(screen.handle_primary_action("agents-delete"))
    assert "Deleted agent: ui-delete-ok" in screen.hint.value


def test_chat_screen_clears_deleted_active_agent_context(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    agent = context.agent_service.create_agent(name="chat-delete-agent")
    session = context.session_service.new_session(agent.id, title="chat")

    chat = ChatScreen(context)
    transcript_lines = []
    chat._append_transcript = lambda line: transcript_lines.append(line)
    chat.active_agent_id = agent.id
    chat.active_session_id = session.id

    context.agent_service.delete_agent(agent.id)

    chat._ensure_active_context()
    assert chat.active_agent_id is None
    assert chat.active_session_id is None
    assert any("Active agent was deleted" in line for line in transcript_lines)
