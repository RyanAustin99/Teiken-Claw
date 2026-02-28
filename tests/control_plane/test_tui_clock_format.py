import pytest

pytest.importorskip("textual")

from app.control_plane.bootstrap import build_context
from app.control_plane.tui.app import TeikenControlPlaneApp
from app.control_plane.tui.screens.dashboard import DashboardScreen


def test_clock_defaults_to_12h(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    screen = DashboardScreen(context)
    assert screen.current_time_format() == "%I:%M:%S %p"


def test_clock_format_persists_when_config_updated(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    context.config_service.save_patch({"clock_24h": True})
    screen = DashboardScreen(context)
    assert screen.current_time_format() == "%H:%M:%S"


def test_toggle_time_format_updates_persisted_config(tmp_path, monkeypatch):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    app = TeikenControlPlaneApp(context=context)

    monkeypatch.setattr(app, "_apply_clock_format", lambda **kwargs: None)
    monkeypatch.setattr(app, "action_refresh_screen", lambda: None)

    assert context.config_service.load().values.clock_24h is False
    app.action_toggle_time_format()
    assert context.config_service.load().values.clock_24h is True
    app.action_toggle_time_format()
    assert context.config_service.load().values.clock_24h is False
