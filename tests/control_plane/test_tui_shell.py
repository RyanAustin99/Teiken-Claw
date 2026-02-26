import pytest

pytest.importorskip("textual")

from app.control_plane.bootstrap import build_context
from app.control_plane.tui.app import TeikenControlPlaneApp


def test_tui_shell_bindings_and_palette_commands(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    app = TeikenControlPlaneApp(context=context)

    keys = {binding.key for binding in app.BINDINGS}
    assert {"f1", "escape", "ctrl+k", "ctrl+r", "ctrl+l", "ctrl+c", "ctrl+s"}.issubset(keys)

    commands = list(app.get_palette_commands())
    groups = {command.group for command in commands}
    assert {"Navigation", "Diagnostics", "Runtime"}.issubset(groups)
