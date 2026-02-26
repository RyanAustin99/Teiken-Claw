import pytest

pytest.importorskip("textual")

from app.control_plane.bootstrap import build_context
from app.control_plane.tui.app import TeikenControlPlaneApp
from app.control_plane.tui.navigation import Route
from textual.screen import Screen


def test_tui_shell_bindings_and_palette_commands(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    app = TeikenControlPlaneApp(context=context)

    keys = {binding.key for binding in app.BINDINGS}
    assert {"f1", "escape", "ctrl+k", "ctrl+r", "ctrl+l", "ctrl+c", "ctrl+s"}.issubset(keys)

    commands = list(app.get_palette_commands())
    groups = {command.group for command in commands}
    assert {"Navigation", "Diagnostics", "Runtime"}.issubset(groups)


def test_build_screen_is_lazy_and_does_not_construct_unrelated_routes(tmp_path, monkeypatch):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    app = TeikenControlPlaneApp(context=context)

    class DummyScreen(Screen):
        pass

    def _should_not_be_called(_context):
        raise AssertionError("Unrelated screen constructor should not run")

    monkeypatch.setattr("app.control_plane.tui.app.BootScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.DashboardScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.SetupWizardScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.ModelsScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.AgentsScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.HatchScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.StatusScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.DoctorScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.LogsScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.HelpScreen", _should_not_be_called)
    monkeypatch.setattr("app.control_plane.tui.app.ChatScreen", lambda _context, initial_agent_id=None: DummyScreen())

    screen = app._build_screen(Route.CHAT, agent_id="agent-1")
    assert isinstance(screen, DummyScreen)


@pytest.mark.asyncio
async def test_tui_run_test_boots_without_logger_collision(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    app = TeikenControlPlaneApp(context=context)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen is not None
