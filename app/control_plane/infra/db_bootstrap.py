"""Control-plane storage bootstrap."""

from __future__ import annotations

from dataclasses import dataclass

from app.control_plane.infra.agent_repo import AgentRepository
from app.control_plane.infra.paths import ControlPlanePaths, PathResolver
from app.control_plane.infra.session_repo import SessionRepository


@dataclass
class BootstrapResult:
    ok: bool
    paths: ControlPlanePaths
    message: str


def bootstrap_storage(paths: ControlPlanePaths) -> BootstrapResult:
    PathResolver.ensure_dirs(paths)
    AgentRepository(paths.control_plane_db)
    SessionRepository(paths.control_plane_db)
    return BootstrapResult(ok=True, paths=paths, message="Storage bootstrap complete")

