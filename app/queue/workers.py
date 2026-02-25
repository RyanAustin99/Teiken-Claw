"""
Worker pool for the Teiken Claw queue system.

This module provides:
- WorkerPool class for managing async workers
- Worker loop that processes jobs from the dispatcher
- Per-chat lock enforcement
- Ollama concurrency semaphore
- Graceful shutdown handling
- Agent runtime integration for chat messages
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable, Awaitable, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field

from app.config.logging import get_logger
from app.config.settings import settings
from app.queue.jobs import Job, JobType
from app.queue.dispatcher import JobDispatcher, get_dispatcher
from app.queue.locks import LockManager, get_lock_manager

# Agent runtime imports
from app.agent.runtime import AgentRuntime, AgentResult, get_agent_runtime
from app.agent.result_formatter import format_response

logger = get_logger(__name__)


class WorkerStatus(str, Enum):
    """Status of a worker."""
    IDLE = "idle"
    BUSY = "busy"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class WorkerInfo:
    """Information about a worker."""
    worker_id: int
    status: WorkerStatus = WorkerStatus.IDLE
    current_job_id: Optional[str] = None
    jobs_processed: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    last_job_at: Optional[datetime] = None


# Type alias for job handlers
JobHandler = Callable[[Job], Awaitable[None]]


class WorkerPool:
    """
    Pool of async workers for processing jobs.
    
    Workers pull jobs from the dispatcher and process them with:
    - Per-chat lock enforcement
    - Ollama concurrency limiting
    - Graceful shutdown support
    - Error handling and retry logic
    - Agent runtime integration
    
    Attributes:
        num_workers: Number of worker tasks
        ollama_concurrency: Maximum concurrent Ollama calls
        workers: List of worker tasks
        status: Current pool status
        agent_runtime: Agent runtime for processing chat messages
    """
    
    def __init__(
        self,
        dispatcher: Optional[JobDispatcher] = None,
        lock_manager: Optional[LockManager] = None,
        num_workers: int = 3,
        ollama_concurrency: int = 2,
        lock_timeout: int = 300,
        agent_runtime: Optional[AgentRuntime] = None,
    ):
        """
        Initialize the worker pool.
        
        Args:
            dispatcher: JobDispatcher instance (uses global if None)
            lock_manager: LockManager instance (uses global if None)
            num_workers: Number of worker tasks to spawn
            ollama_concurrency: Maximum concurrent Ollama API calls
            lock_timeout: Lock timeout in seconds
            agent_runtime: AgentRuntime instance (uses global if None)
        """
        self.dispatcher = dispatcher or get_dispatcher()
        self.lock_manager = lock_manager or get_lock_manager()
        self.num_workers = num_workers
        self.ollama_concurrency = ollama_concurrency
        self.lock_timeout = lock_timeout
        self.agent_runtime = agent_runtime  # Will be set later if None
        
        # Semaphore for Ollama concurrency
        self._ollama_semaphore = asyncio.Semaphore(ollama_concurrency)
        
        # Worker tracking
        self._workers: List[asyncio.Task] = []
        self._worker_info: Dict[int, WorkerInfo] = {}
        
        # Job handlers registry
        self._handlers: Dict[JobType, JobHandler] = {}
        
        # Shutdown signal
        self._shutdown_event = asyncio.Event()
        self._running = False
        
        # Statistics
        self._total_jobs_processed = 0
        self._total_errors = 0
        
        # Register default chat message handler
        self._register_default_handlers()
        
        logger.info(
            f"WorkerPool initialized: num_workers={num_workers}, ollama_concurrency={ollama_concurrency}",
            extra={"event": "worker_pool_initialized"}
        )
    
    def _register_default_handlers(self) -> None:
        """Register default job handlers."""
        self.register_handler(JobType.CHAT_MESSAGE, self._handle_chat_message)
    
    async def _handle_chat_message(self, job: Job) -> None:
        """
        Handle a chat message job using the agent runtime.
        
        Args:
            job: Chat message job to process
        """
        # Get agent runtime if not set
        runtime = self.agent_runtime or get_agent_runtime()
        
        # Run the agent
        result: AgentResult = await runtime.run(job)
        
        # Log the result
        logger.info(
            f"Agent run completed: ok={result.ok}",
            extra={
                "event": "agent_run_complete",
                "job_id": job.job_id,
                "ok": result.ok,
                "tool_calls": result.tool_calls,
            }
        )
        
        # TODO: Send response to outbound queue
        # For now, just log the response
        if result.ok:
            logger.info(
                f"Agent response: {result.response[:200]}...",
                extra={
                    "event": "agent_response",
                    "job_id": job.job_id,
                    "response_length": len(result.response),
                }
            )
        else:
            logger.warning(
                f"Agent error: {result.error}",
                extra={
                    "event": "agent_error",
                    "job_id": job.job_id,
                    "error_code": result.error_code,
                }
            )
    
    def register_handler(self, job_type: JobType, handler: JobHandler) -> None:
        """
        Register a handler for a specific job type.
        
        Args:
            job_type: The type of job this handler processes
            handler: Async function that processes the job
        """
        self._handlers[job_type] = handler
        logger.debug(
            f"Registered handler for job type: {job_type}",
            extra={"event": "handler_registered", "job_type": job_type}
        )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the worker pool.
        
        Returns:
            dict: Status information including workers and statistics
        """
        workers_status = {}
        for worker_id, info in self._worker_info.items():
            workers_status[str(worker_id)] = {
                "status": info.status.value,
                "current_job_id": info.current_job_id,
                "jobs_processed": info.jobs_processed,
                "errors": info.errors,
            }
        
        return {
            "running": self._running,
            "num_workers": self.num_workers,
            "active_workers": sum(1 for w in self._workers if not w.done()),
            "workers": workers_status,
            "total_jobs_processed": self._total_jobs_processed,
            "total_errors": self._total_errors,
        }
    
    async def _process_job(self, job: Job) -> None:
        """
        Process a single job.
        
        This method:
        1. Acquires per-chat lock
        2. Acquires Ollama semaphore (if needed)
        3. Calls the appropriate handler
        4. Handles errors and retries
        
        Args:
            job: The job to process
        """
        worker_id = id(asyncio.current_task()) % 10000  # Simplified worker ID
        worker_info = self._worker_info.get(worker_id)
        
        if worker_info:
            worker_info.status = WorkerStatus.BUSY
            worker_info.current_job_id = job.job_id
        
        try:
            logger.info(
                f"Processing job: {job.job_id}",
                extra={
                    "event": "job_processing",
                    "job_id": job.job_id,
                    "job_type": job.type,
                    "chat_id": job.chat_id,
                }
            )
            
            # Acquire per-chat lock if chat_id is present
            if job.chat_id and self.lock_manager:
                async with self.lock_manager.acquire_chat_lock(
                    job.chat_id,
                    timeout=self.lock_timeout,
                ):
                    await self._execute_job(job, worker_id)
            else:
                await self._execute_job(job, worker_id)
            
            # Mark job as complete
            if self.dispatcher:
                self.dispatcher.mark_complete(job.job_id)
            
            if worker_info:
                worker_info.jobs_processed += 1
                worker_info.last_job_at = datetime.utcnow()
            
            self._total_jobs_processed += 1
            
            logger.info(
                f"Job completed: {job.job_id}",
                extra={"event": "job_completed", "job_id": job.job_id}
            )
            
        except Exception as e:
            self._total_errors += 1
            
            if worker_info:
                worker_info.errors += 1
            
            logger.error(
                f"Job failed: {job.job_id} - {e}",
                extra={
                    "event": "job_failed",
                    "job_id": job.job_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            
            # Let dispatcher handle retry/dead-letter logic
            if self.dispatcher:
                await self.dispatcher.mark_failed(job, e)
        
        finally:
            if worker_info:
                worker_info.status = WorkerStatus.IDLE
                worker_info.current_job_id = None
    
    async def _execute_job(self, job: Job, worker_id: int) -> None:
        """
        Execute the job with appropriate concurrency controls.
        
        Args:
            job: The job to execute
            worker_id: ID of the worker executing the job
        """
        job_type = JobType(job.type) if isinstance(job.type, str) else job.type
        handler = self._handlers.get(job_type)
        
        if handler is None:
            # Default handler - just log
            logger.warning(
                f"No handler registered for job type: {job.type}",
                extra={
                    "event": "no_handler",
                    "job_id": job.job_id,
                    "job_type": job.type,
                }
            )
            # Placeholder: just log the job payload
            logger.info(
                f"Job payload: {job.payload}",
                extra={"event": "job_payload", "job_id": job.job_id}
            )
            return
        
        # Check if this job type needs Ollama concurrency control
        needs_ollama = job_type in (
            JobType.CHAT_MESSAGE,
            JobType.SUBAGENT_TASK,
            JobType.EMBEDDING_GENERATION,
        )
        
        if needs_ollama:
            async with self._ollama_semaphore:
                logger.debug(
                    f"Acquired Ollama semaphore for job: {job.job_id}",
                    extra={"event": "ollama_semaphore_acquired", "job_id": job.job_id}
                )
                await handler(job)
        else:
            await handler(job)
    
    async def _worker_loop(self, worker_id: int) -> None:
        """
        Main loop for a worker.
        
        Continuously pulls jobs from the dispatcher and processes them
        until shutdown is signaled.
        
        Args:
            worker_id: Unique identifier for this worker
        """
        worker_info = WorkerInfo(
            worker_id=worker_id,
            status=WorkerStatus.IDLE,
            started_at=datetime.utcnow(),
        )
        self._worker_info[worker_id] = worker_info
        
        logger.info(
            f"Worker {worker_id} started",
            extra={"event": "worker_started", "worker_id": worker_id}
        )
        
        try:
            while not self._shutdown_event.is_set():
                # Check if dispatcher is available and not shutdown
                if not self.dispatcher or self.dispatcher.is_shutdown:
                    if self.dispatcher and self.dispatcher.queue_depth == 0:
                        break
                    if not self.dispatcher:
                        break
                
                try:
                    # Try to get a job with timeout
                    job = await self.dispatcher.dequeue(timeout=1.0)
                    
                    if job is None:
                        # No job available, continue loop
                        continue
                    
                    # Process the job
                    await self._process_job(job)
                    
                except asyncio.CancelledError:
                    logger.info(
                        f"Worker {worker_id} cancelled",
                        extra={"event": "worker_cancelled", "worker_id": worker_id}
                    )
                    break
                except Exception as e:
                    logger.error(
                        f"Worker {worker_id} error: {e}",
                        extra={"event": "worker_error", "worker_id": worker_id},
                        exc_info=True,
                    )
                    # Brief pause before continuing
                    await asyncio.sleep(0.1)
        
        finally:
            worker_info.status = WorkerStatus.STOPPED
            logger.info(
                f"Worker {worker_id} stopped (processed {worker_info.jobs_processed} jobs)",
                extra={
                    "event": "worker_stopped",
                    "worker_id": worker_id,
                    "jobs_processed": worker_info.jobs_processed,
                }
            )
    
    async def start(self) -> None:
        """
        Start the worker pool.
        
        Spawns the configured number of worker tasks.
        """
        if self._running:
            logger.warning("WorkerPool already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        logger.info(
            f"Starting WorkerPool with {self.num_workers} workers",
            extra={"event": "worker_pool_starting"}
        )
        
        # Spawn worker tasks
        for i in range(self.num_workers):
            worker_id = i + 1
            task = asyncio.create_task(self._worker_loop(worker_id))
            self._workers.append(task)
        
        logger.info(
            f"WorkerPool started with {len(self._workers)} workers",
            extra={"event": "worker_pool_started"}
        )
    
    async def stop(self, timeout: float = 30.0) -> None:
        """
        Stop the worker pool gracefully.
        
        Args:
            timeout: Maximum time to wait for workers to finish
        """
        if not self._running:
            return
        
        logger.info(
            "Stopping WorkerPool",
            extra={"event": "worker_pool_stopping"}
        )
        
        # Signal shutdown
        self._shutdown_event.set()
        self._running = False
        
        # Wait for workers to finish
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"WorkerPool stop timeout, cancelling {len(self._workers)} workers",
                    extra={"event": "worker_pool_stop_timeout"}
                )
                for task in self._workers:
                    if not task.done():
                        task.cancel()
                
                # Wait for cancellation
                await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        
        logger.info(
            "WorkerPool stopped",
            extra={
                "event": "worker_pool_stopped",
                "total_jobs_processed": self._total_jobs_processed,
                "total_errors": self._total_errors,
            }
        )
    
    async def wait_until_stopped(self) -> None:
        """Wait until all workers have stopped."""
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)


# Global worker pool instance (initialized by main app)
_worker_pool: Optional[WorkerPool] = None


def get_worker_pool() -> Optional[WorkerPool]:
    """Get the global worker pool instance."""
    return _worker_pool


def set_worker_pool(pool: WorkerPool) -> None:
    """Set the global worker pool instance."""
    global _worker_pool
    _worker_pool = pool


__all__ = [
    "WorkerPool",
    "WorkerStatus",
    "WorkerInfo",
    "JobHandler",
    "get_worker_pool",
    "set_worker_pool",
]
