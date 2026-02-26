"""Path resolution and directory topology for the control plane."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_HOME_DIRNAME = "TeikenClaw"


@dataclass(frozen=True)
class ControlPlanePaths:
    base_dir: Path
    config_dir: Path
    state_dir: Path
    run_dir: Path
    exports_dir: Path
    logs_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "user_config.json"

    @property
    def control_plane_db(self) -> Path:
        return self.state_dir / "control_plane.db"

    @property
    def lock_file(self) -> Path:
        return self.run_dir / "control_plane.lock"

    @property
    def server_pid_file(self) -> Path:
        return self.run_dir / "dev_server.pid"


class PathResolver:
    """Resolve base path with precedence: CLI > env > default."""

    @staticmethod
    def resolve_base_path(cli_data_dir: Optional[str] = None) -> Path:
        if cli_data_dir:
            return Path(cli_data_dir).expanduser().resolve()

        env_home = os.getenv("TEIKEN_HOME")
        if env_home:
            return Path(env_home).expanduser().resolve()

        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data) / DEFAULT_HOME_DIRNAME).resolve()

        return (Path.home() / "AppData" / "Local" / DEFAULT_HOME_DIRNAME).resolve()

    @classmethod
    def resolve_paths(cls, cli_data_dir: Optional[str] = None) -> ControlPlanePaths:
        base_dir = cls.resolve_base_path(cli_data_dir=cli_data_dir)
        return ControlPlanePaths(
            base_dir=base_dir,
            config_dir=base_dir / "config",
            state_dir=base_dir / "state",
            run_dir=base_dir / "run",
            exports_dir=base_dir / "exports",
            logs_dir=base_dir / "logs",
        )

    @staticmethod
    def ensure_dirs(paths: ControlPlanePaths) -> None:
        for path in (
            paths.base_dir,
            paths.config_dir,
            paths.state_dir,
            paths.run_dir,
            paths.exports_dir,
            paths.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

