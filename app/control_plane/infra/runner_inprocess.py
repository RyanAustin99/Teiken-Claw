"""In-process runner implementation for agent runtime."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional, Tuple

from app.control_plane.domain.errors import QueueFullError
from app.control_plane.domain.models import RuntimeStatus, RunnerType
from app.control_plane.infra.runner_base import AgentRunner, RunnerStatus


class InProcessRunner(AgentRunner):
    """Queue-backed in-process runner with bounded backpressure."""

    def __init__(
        self,
        agent_id: str,
        max_queue_depth: int,
        semaphore: asyncio.Semaphore,
        chat_fn: Callable[[str, Optional[str]], Awaitable[str]],
    ) -> None:
        self.agent_id = agent_id
        self.max_queue_depth = max_queue_depth
        self._semaphore = semaphore
        self._chat_fn = chat_fn
        self._queue: asyncio.Queue[Tuple[str, Optional[str], asyncio.Future[str]]] = asyncio.Queue(maxsize=max_queue_depth)
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._status = RuntimeStatus.STOPPED
        self._overflow_count = 0
        self._last_error: Optional[str] = None
        self._last_heartbeat_at: Optional[datetime] = None

    async def start(self) -> None:
        if self._status in (RuntimeStatus.RUNNING, RuntimeStatus.STARTING):
            return
        self._status = RuntimeStatus.STARTING
        self._worker_task = asyncio.create_task(self._worker_loop(), name=f"agent-runner-{self.agent_id}")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"agent-heartbeat-{self.agent_id}")
        self._status = RuntimeStatus.RUNNING

    async def stop(self) -> None:
        self._status = RuntimeStatus.STOPPING
        tasks = [task for task in (self._worker_task, self._heartbeat_task) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._status = RuntimeStatus.STOPPED

    async def send_message(self, message: str, *, session_id: Optional[str] = None) -> str:
        if self._status != RuntimeStatus.RUNNING:
            raise RuntimeError(f"Agent {self.agent_id} is not running")
        if self._queue.full():
            self._overflow_count += 1
            raise QueueFullError(agent_id=self.agent_id, max_depth=self.max_queue_depth)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._queue.put_nowait((message, session_id, future))
        return await future

    def status(self) -> RunnerStatus:
        derived_status = self._status
        if self._status == RuntimeStatus.RUNNING and self._last_heartbeat_at:
            if datetime.utcnow() - self._last_heartbeat_at > timedelta(seconds=30):
                derived_status = RuntimeStatus.DEGRADED
        return RunnerStatus(
            agent_id=self.agent_id,
            status=derived_status,
            runner_type=RunnerType.INPROCESS,
            queued=self._queue.qsize(),
            overflow_count=self._overflow_count,
            last_error=self._last_error,
            last_heartbeat_at=self._last_heartbeat_at,
        )

    async def _worker_loop(self) -> None:
        while True:
            message, session_id, future = await self._queue.get()
            try:
                async with self._semaphore:
                    response = await self._chat_fn(message, session_id)
                if not future.done():
                    future.set_result(response)
            except Exception as exc:  # pragma: no cover - runtime guard
                self._last_error = str(exc)
                self._status = RuntimeStatus.CRASHED
                if not future.done():
                    future.set_exception(exc)

    async def _heartbeat_loop(self) -> None:
        while True:
            self._last_heartbeat_at = datetime.utcnow()
            await asyncio.sleep(2.0)

