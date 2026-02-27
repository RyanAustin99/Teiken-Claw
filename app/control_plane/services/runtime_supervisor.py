"""Runtime supervision for dev server and agent runtimes."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Optional

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import RuntimeEntry, RuntimeStatus, RunnerType, SupervisorSnapshot
from app.control_plane.infra.runner_base import AgentRunner
from app.control_plane.infra.runner_inprocess import InProcessRunner
from app.control_plane.infra.runner_subprocess import SubprocessRunner
from app.control_plane.infra.server_process import ServerProcessManager
from app.control_plane.services.agent_service import AgentService
from app.control_plane.services.agent_conversation_service import AgentConversationService
from app.control_plane.services.audit_service import AuditService
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.hatch_boot_service import HatchBootService
from app.control_plane.services.model_service import ModelService
from app.control_plane.services.session_service import SessionService
from app.tools.protocol import render_tool_result


class RuntimeSupervisor:
    """Orchestrates dev server process and per-agent runtimes."""

    def __init__(
        self,
        config_service: ConfigService,
        model_service: ModelService,
        conversation_service: AgentConversationService,
        hatch_boot_service: HatchBootService,
        agent_service: AgentService,
        session_service: SessionService,
        server_process_manager: ServerProcessManager,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self.config_service = config_service
        self.model_service = model_service
        self.conversation_service = conversation_service
        self.hatch_boot_service = hatch_boot_service
        self.agent_service = agent_service
        self.session_service = session_service
        self.server_process_manager = server_process_manager
        self.audit_service = audit_service
        cfg = self.config_service.load().values
        self._semaphore = asyncio.Semaphore(max(1, cfg.max_inflight_ollama_requests))
        self._inflight = 0
        self._runners: Dict[str, AgentRunner] = {}
        self._last_errors: Dict[str, str] = {}

    def start_dev_server(self) -> SupervisorSnapshot:
        cfg = self.config_service.load().values
        self.server_process_manager.host = cfg.dev_server_host
        self.server_process_manager.port = cfg.dev_server_port
        self.server_process_manager.start(attach_if_running=True)
        if self.audit_service:
            self.audit_service.log("dev_server.start", target="dev_server", details={}, actor="supervisor")
        return self.snapshot()

    def stop_dev_server(self) -> SupervisorSnapshot:
        self.server_process_manager.stop()
        if self.audit_service:
            self.audit_service.log("dev_server.stop", target="dev_server", details={}, actor="supervisor")
        return self.snapshot()

    def restart_dev_server(self) -> SupervisorSnapshot:
        self.server_process_manager.restart()
        if self.audit_service:
            self.audit_service.log("dev_server.restart", target="dev_server", details={}, actor="supervisor")
        return self.snapshot()

    async def start_agent(self, agent_id: str) -> RuntimeEntry:
        agent = self.agent_service.get_agent(agent_id)
        if not agent:
            raise ValidationError(f"Unknown agent: {agent_id}")

        if agent.id in self._runners:
            return self._entry_from_runner(agent.id, self._runners[agent.id])

        cfg = self.config_service.load().values
        queue_depth = agent.max_queue_depth or cfg.max_agent_queue_depth
        runner_type = agent.runner_type or RunnerType.INPROCESS
        if runner_type == RunnerType.SUBPROCESS and not cfg.subprocess_runner_enabled:
            raise ValidationError("Subprocess runner is disabled. Enable in config first.")

        if runner_type == RunnerType.SUBPROCESS:
            runner: AgentRunner = SubprocessRunner(agent_id=agent.id)
        else:
            runner = InProcessRunner(
                agent_id=agent.id,
                max_queue_depth=queue_depth,
                semaphore=self._semaphore,
                chat_fn=lambda msg, sid, aid=agent.id: self._chat_with_limits(aid, msg, sid),
            )

        await runner.start()
        self._runners[agent.id] = runner
        self.agent_service.set_status(agent.id, RuntimeStatus.RUNNING)
        if self.audit_service:
            self.audit_service.log("agent.start", target=agent.id, details={"runner": runner_type.value}, actor="supervisor")
        return self._entry_from_runner(agent.id, runner)

    async def stop_agent(self, agent_id: str) -> RuntimeEntry:
        runner = self._runners.get(agent_id)
        if not runner:
            self.agent_service.set_status(agent_id, RuntimeStatus.STOPPED)
            return RuntimeEntry(agent_id=agent_id, status=RuntimeStatus.STOPPED, runner_type=RunnerType.INPROCESS)
        await runner.stop()
        del self._runners[agent_id]
        self.agent_service.set_status(agent_id, RuntimeStatus.STOPPED)
        if self.audit_service:
            self.audit_service.log("agent.stop", target=agent_id, details={}, actor="supervisor")
        return self._entry_from_runner(agent_id, runner)

    async def restart_agent(self, agent_id: str) -> RuntimeEntry:
        await self.stop_agent(agent_id)
        entry = await self.start_agent(agent_id)
        if self.audit_service:
            self.audit_service.log("agent.restart", target=agent_id, details={}, actor="supervisor")
        return entry

    async def delete_agent(self, agent_id: str) -> bool:
        """Stop runtime state and delete agent/session persistence safely."""
        agent = self.agent_service.get_agent(agent_id)
        resolved_agent_id = agent.id if agent else agent_id
        cleanup_errors: list[str] = []
        try:
            await self.stop_agent(resolved_agent_id)
        except Exception as exc:
            # Continue with deletion cleanup even if stop path fails.
            cleanup_errors.append(f"stop_failed:{exc}")
            self._runners.pop(resolved_agent_id, None)
        self._runners.pop(resolved_agent_id, None)

        try:
            self.session_service.delete_sessions_for_agent(resolved_agent_id)
        except Exception as exc:
            cleanup_errors.append(f"session_cleanup_failed:{exc}")

        deleted = False
        try:
            deleted = self.agent_service.delete_agent(resolved_agent_id)
        except Exception as exc:
            cleanup_errors.append(f"agent_delete_failed:{exc}")

        if cleanup_errors:
            self._last_errors[resolved_agent_id] = " | ".join(cleanup_errors)
            if self.audit_service:
                self.audit_service.log(
                    "agent.delete.error",
                    target=resolved_agent_id,
                    details={"errors": cleanup_errors, "deleted": deleted},
                    actor="supervisor",
                )
        else:
            self._last_errors.pop(resolved_agent_id, None)

        if deleted and self.audit_service:
            self.audit_service.log("agent.delete", target=resolved_agent_id, details={}, actor="supervisor")
        return deleted

    async def restart_all(self) -> SupervisorSnapshot:
        for agent_id in list(self._runners.keys()):
            await self.restart_agent(agent_id)
        self.restart_dev_server()
        return self.snapshot()

    async def chat(self, agent_id: str, session_id: str, message: str) -> str:
        runner = self._runners.get(agent_id)
        if runner:
            runner_status = runner.status().status
            if runner_status != RuntimeStatus.RUNNING:
                # Runners can become stale across loop boundaries in tests/CLI hops.
                # Drop stale handles and let start_agent recreate a healthy runner.
                self._runners.pop(agent_id, None)
                self.agent_service.set_status(agent_id, RuntimeStatus.STOPPED)
                runner = None
        if not runner:
            await self.start_agent(agent_id)
            runner = self._runners[agent_id]
        self.session_service.append_user_message(session_id, message)
        response = await runner.send_message(message, session_id=session_id)
        self.session_service.append_assistant_message(session_id, response)
        return response

    async def trigger_hatch_boot(
        self,
        *,
        agent_id: str,
        session_id: str,
        user_metadata: Optional[Dict[str, str]] = None,
        overwrite_profile: bool = True,
    ) -> str:
        """Generate and persist the proactive first boot message."""
        return await self.hatch_boot_service.run_boot(
            agent_id=agent_id,
            session_id=session_id,
            user_metadata=user_metadata,
            overwrite_profile=overwrite_profile,
        )

    def snapshot(self) -> SupervisorSnapshot:
        server_status = self.server_process_manager.status()
        entries = [self._entry_from_runner(agent_id, runner) for agent_id, runner in self._runners.items()]
        return SupervisorSnapshot(
            dev_server_running=server_status.running,
            dev_server_url=server_status.url if server_status.running else None,
            global_inflight_ollama=self._inflight,
            max_inflight_ollama=self.config_service.load().values.max_inflight_ollama_requests,
            runtimes=entries,
        )

    async def snapshot_async(self) -> SupervisorSnapshot:
        """Async-friendly snapshot hook for polling UIs."""
        await asyncio.sleep(0)
        return self.snapshot()

    async def shutdown_gracefully(self) -> None:
        for agent_id in list(self._runners.keys()):
            await self.stop_agent(agent_id)
        self.stop_dev_server()

    async def _chat_with_limits(self, agent_id: str, message: str, session_id: Optional[str]) -> str:
        agent = self.agent_service.get_agent(agent_id)
        if not agent:
            raise ValidationError("Unknown agent for runtime chat.", details={"agent_id": agent_id})
        self._inflight += 1
        try:
            if not session_id:
                raise ValidationError(
                    "Session ID required for agent-contextual chat.",
                    details={"agent_id": agent_id},
                )
            conversation = await self.conversation_service.generate_response_with_tools(
                agent_id=agent_id,
                session_id=session_id,
                user_message=message,
            )
            for tool_event in conversation.tool_events:
                self.session_service.append_assistant_message(
                    session_id=session_id,
                    content=render_tool_result(tool_event),
                    tool_name=tool_event.tool,
                    tool_ok=tool_event.ok,
                    tool_elapsed_ms=tool_event.elapsed_ms,
                )
            self.agent_service.set_status(agent_id, RuntimeStatus.RUNNING)
            return conversation.response
        except Exception as exc:
            self._last_errors[agent_id] = str(exc)
            try:
                if self.agent_service.get_agent(agent_id):
                    self.agent_service.set_status(agent_id, RuntimeStatus.DEGRADED, last_error=str(exc))
            except Exception:
                pass
            raise
        finally:
            self._inflight = max(0, self._inflight - 1)

    def _entry_from_runner(self, agent_id: str, runner: AgentRunner) -> RuntimeEntry:
        status = runner.status()
        return RuntimeEntry(
            agent_id=agent_id,
            status=status.status,
            runner_type=status.runner_type,
            queued=status.queued,
            overflow_count=status.overflow_count,
            last_error=status.last_error or self._last_errors.get(agent_id),
            last_heartbeat_at=status.last_heartbeat_at,
        )
