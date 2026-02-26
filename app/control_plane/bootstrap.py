"""Bootstrap helper for control-plane service graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.control_plane.infra.agent_repo import AgentRepository
from app.control_plane.infra.config_store import ConfigStore
from app.control_plane.infra.db_bootstrap import bootstrap_storage
from app.control_plane.infra.lock import SingleInstanceLock
from app.control_plane.infra.paths import ControlPlanePaths, PathResolver
from app.control_plane.infra.server_process import ServerProcessManager
from app.control_plane.infra.session_repo import SessionRepository
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.doctor_service import DoctorService
from app.control_plane.services.log_service import LogService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.runtime_supervisor import RuntimeSupervisor
from app.control_plane.services.session_service import SessionService


@dataclass
class ControlPlaneContext:
    paths: ControlPlanePaths
    lock: SingleInstanceLock
    config_service: ConfigService
    model_service: ModelService
    agent_service: AgentService
    session_service: SessionService
    runtime_supervisor: RuntimeSupervisor
    log_service: LogService
    doctor_service: DoctorService


def build_context(cli_data_dir: Optional[str] = None) -> ControlPlaneContext:
    paths = PathResolver.resolve_paths(cli_data_dir=cli_data_dir)
    bootstrap_storage(paths)

    config_store = ConfigStore(paths.config_file)
    config_service = ConfigService(config_store)
    model_service = ModelService(config_service)

    agent_repo = AgentRepository(paths.control_plane_db)
    session_repo = SessionRepository(paths.control_plane_db)
    workspace_root = Path(config_service.load().values.workspace_dir)
    if not workspace_root.is_absolute():
        workspace_root = (paths.base_dir / workspace_root).resolve()
    agent_service = AgentService(repo=agent_repo, workspace_root=workspace_root)
    session_service = SessionService(repo=session_repo)
    server_manager = ServerProcessManager(
        pid_file=paths.server_pid_file,
        host=config_service.load().values.dev_server_host,
        port=config_service.load().values.dev_server_port,
    )
    runtime_supervisor = RuntimeSupervisor(
        config_service=config_service,
        model_service=model_service,
        agent_service=agent_service,
        session_service=session_service,
        server_process_manager=server_manager,
    )
    log_service = LogService(logs_dir=paths.logs_dir)
    doctor_service = DoctorService(
        config_service=config_service,
        model_service=model_service,
        state_db_path=paths.control_plane_db,
        runtime_supervisor=runtime_supervisor,
    )
    lock = SingleInstanceLock(paths.lock_file)
    return ControlPlaneContext(
        paths=paths,
        lock=lock,
        config_service=config_service,
        model_service=model_service,
        agent_service=agent_service,
        session_service=session_service,
        runtime_supervisor=runtime_supervisor,
        log_service=log_service,
        doctor_service=doctor_service,
    )

