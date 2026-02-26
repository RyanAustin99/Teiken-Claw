import os
from pathlib import Path

from app.control_plane.infra.paths import PathResolver


def test_path_precedence_cli_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TEIKEN_HOME", str(tmp_path / "env_home"))
    resolved = PathResolver.resolve_base_path(cli_data_dir=str(tmp_path / "cli_home"))
    assert resolved == (tmp_path / "cli_home").resolve()


def test_path_precedence_env_over_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TEIKEN_HOME", str(tmp_path / "env_home"))
    resolved = PathResolver.resolve_base_path()
    assert resolved == (tmp_path / "env_home").resolve()

