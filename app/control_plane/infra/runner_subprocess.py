"""Subprocess runner skeleton using JSONL stdin/stdout IPC."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.control_plane.domain.models import RuntimeStatus, RunnerType
from app.control_plane.infra.runner_base import AgentRunner, RunnerStatus


class SubprocessRunner(AgentRunner):
    """Feature-flag subprocess runner with deterministic minimal IPC contract."""

    def __init__(self, agent_id: str, startup_timeout_sec: float = 5.0) -> None:
        self.agent_id = agent_id
        self.startup_timeout_sec = startup_timeout_sec
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stdout_task: Optional[asyncio.Task[None]] = None
        self._status = RuntimeStatus.STOPPED
        self._last_error: Optional[str] = None
        self._last_heartbeat_at: Optional[datetime] = None
        self._pending: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._ready_event = asyncio.Event()

    async def start(self) -> None:
        if self._status in (RuntimeStatus.RUNNING, RuntimeStatus.STARTING):
            return
        self._status = RuntimeStatus.STARTING
        self._ready_event.clear()
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.control_plane.infra.subprocess_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout(), name=f"subproc-runner-{self.agent_id}")
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=self.startup_timeout_sec)
            self._status = RuntimeStatus.RUNNING
        except asyncio.TimeoutError as exc:
            self._status = RuntimeStatus.CRASHED
            self._last_error = "Runner readiness timeout"
            raise RuntimeError(self._last_error) from exc

    async def stop(self) -> None:
        if not self._proc:
            self._status = RuntimeStatus.STOPPED
            return
        self._status = RuntimeStatus.STOPPING
        try:
            await self._send_command({"action": "shutdown"}, wait_response=False)
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except Exception:
            self._proc.terminate()
            await self._proc.wait()
        finally:
            if self._stdout_task:
                self._stdout_task.cancel()
                await asyncio.gather(self._stdout_task, return_exceptions=True)
            self._proc = None
            self._status = RuntimeStatus.STOPPED

    async def send_message(self, message: str, *, session_id: Optional[str] = None) -> str:
        response = await self._send_command(
            {"action": "send_message", "message": message, "session_id": session_id},
            wait_response=True,
        )
        return str(response.get("content", ""))

    def status(self) -> RunnerStatus:
        derived = self._status
        if self._status == RuntimeStatus.RUNNING and self._last_heartbeat_at:
            if datetime.utcnow() - self._last_heartbeat_at > timedelta(seconds=10):
                derived = RuntimeStatus.DEGRADED
        return RunnerStatus(
            agent_id=self.agent_id,
            status=derived,
            runner_type=RunnerType.SUBPROCESS,
            queued=0,
            overflow_count=0,
            last_error=self._last_error,
            last_heartbeat_at=self._last_heartbeat_at,
        )

    async def _send_command(self, payload: Dict[str, Any], wait_response: bool) -> Dict[str, Any]:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("Subprocess runner not started")
        request_id = str(uuid.uuid4())
        payload["request_id"] = request_id
        future: asyncio.Future[Dict[str, Any]] = asyncio.get_running_loop().create_future()
        if wait_response:
            self._pending[request_id] = future

        self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()
        if not wait_response:
            return {"ok": True}

        return await asyncio.wait_for(future, timeout=30.0)

    async def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                payload = json.loads(line.decode("utf-8").strip())
            except Exception:
                continue
            event = payload.get("event")
            request_id = payload.get("request_id")
            if event == "ready":
                self._last_heartbeat_at = datetime.utcnow()
                self._ready_event.set()
            elif event == "heartbeat":
                self._last_heartbeat_at = datetime.utcnow()
            elif request_id and request_id in self._pending:
                future = self._pending.pop(request_id)
                if not future.done():
                    future.set_result(payload)
            elif event == "error":
                self._last_error = str(payload.get("error", "unknown subprocess error"))

