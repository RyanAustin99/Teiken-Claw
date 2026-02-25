"""
Scheduler execution bridge for the Teiken Claw scheduler.

This module provides:
- SchedulerExecutor class for executing scheduled jobs
- Integration with the job dispatcher
- Dead-letter queue integration for failed jobs
- Retry logic for failed job executions

Key Features:
    - Convert scheduled jobs to dispatcher jobs
    - Track execution history
    - Handle success/failure callbacks
    - Retry failed jobs with configurable policy
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

from app.scheduler.jobs import (
    ScheduledJob,
    JobRunResult,
    JobStatus,
    JobActionType,
)
from app.queue.dispatcher import JobDispatcher, get_dispatcher
from app.queue.jobs import Job, JobPriority
from app.queue.dead_letter import DeadLetterQueue, get_dead_letter_queue
from app.scheduler.persistence import SchedulerPersistence, get_scheduler_persistence

logger = logging.getLogger(__name__)

# Global executor instance
_scheduler_executor: Optional["SchedulerExecutor"] = None


def get_scheduler_executor() -> Optional["SchedulerExecutor"]:
    """Get the global scheduler executor instance."""
    return _scheduler_executor


def set_scheduler_executor(executor: "SchedulerExecutor") -> None:
    """Set the global scheduler executor instance."""
    global _scheduler_executor
    _scheduler_executor = executor


class SchedulerExecutor:
    """
    Executor for scheduled jobs.
    
    Bridges the scheduler service with the job dispatcher:
    - Converts scheduled jobs to dispatcher jobs
    - Enqueues jobs for processing
    - Tracks execution history
    - Handles failures with retry logic
    
    Example:
        executor = SchedulerExecutor(dispatcher, dead_letter_queue)
        
        # Execute a job
        result = await executor.execute_job("daily_report", action_config)
        
        # Handle callbacks
        await executor.handle_job_success("daily_report", result)
        await executor.handle_job_failure("daily_report", error)
    """
    
    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_SECONDS = 60
    
    def __init__(
        self,
        dispatcher: Optional[JobDispatcher] = None,
        dead_letter_queue: Optional[DeadLetterQueue] = None,
        persistence: Optional[SchedulerPersistence] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    ):
        """
        Initialize the scheduler executor.
        
        Args:
            dispatcher: Job dispatcher instance
            dead_letter_queue: Dead-letter queue for failed jobs
            persistence: Scheduler persistence layer
            max_retries: Maximum retry attempts for failed jobs
            retry_delay_seconds: Delay between retries
        """
        self.dispatcher = dispatcher
        self.dead_letter_queue = dead_letter_queue
        self.persistence = persistence
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        
        # Track active runs
        self._active_runs: Dict[str, JobRunResult] = {}
        
        # Retry tracking
        self._retry_counts: Dict[str, int] = {}
        
        logger.info(
            f"SchedulerExecutor initialized (max_retries: {max_retries})",
            extra={"event": "scheduler_executor_initialized"}
        )
    
    async def execute_job(
        self,
        job_id: str,
        action: Dict[str, Any],
    ) -> JobRunResult:
        """
        Execute a scheduled job.
        
        Converts the scheduled job action to a dispatcher job
        and enqueues it for processing.
        
        Args:
            job_id: Scheduled job identifier
            action: Action configuration from the scheduled job
            
        Returns:
            JobRunResult with execution status
        """
        run_id = f"run_{uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        
        logger.info(
            f"Executing scheduled job: {job_id}",
            extra={
                "event": "scheduled_job_executing",
                "job_id": job_id,
                "run_id": run_id,
            }
        )
        
        # Create run result
        result = JobRunResult(
            job_id=job_id,
            run_id=run_id,
            status=JobStatus.RUNNING,
            started_at=started_at,
        )
        
        # Track active run
        self._active_runs[run_id] = result
        
        try:
            # Get the scheduled job for context
            scheduled_job = None
            if self.persistence:
                scheduled_job = await self.persistence.load_job(job_id)
            
            # Convert action to dispatcher job
            dispatcher_job = await self._convert_to_dispatcher_job(
                job_id, action, scheduled_job
            )
            
            # Check if dispatcher is available
            if not self.dispatcher:
                # Try to get global dispatcher
                self.dispatcher = get_dispatcher()
            
            if not self.dispatcher:
                raise RuntimeError("Job dispatcher not available")
            
            # Enqueue the job
            enqueued = await self.dispatcher.enqueue(dispatcher_job)
            
            if not enqueued:
                raise RuntimeError("Failed to enqueue job to dispatcher")
            
            # Mark as success (the actual processing happens asynchronously)
            result.mark_success(
                result=f"Job {job_id} enqueued successfully (dispatcher_job_id: {dispatcher_job.id})"
            )
            
            logger.info(
                f"Scheduled job enqueued: {job_id}",
                extra={
                    "event": "scheduled_job_enqueued",
                    "job_id": job_id,
                    "run_id": run_id,
                    "dispatcher_job_id": dispatcher_job.id,
                }
            )
            
            # Handle success callback
            await self.handle_job_success(job_id, result)
            
            return result
            
        except Exception as e:
            error_message = str(e)
            error_type = type(e).__name__
            
            result.mark_failure(error_message, error_type)
            
            logger.error(
                f"Scheduled job execution failed: {job_id} - {error_message}",
                extra={
                    "event": "scheduled_job_failed",
                    "job_id": job_id,
                    "run_id": run_id,
                    "error_type": error_type,
                },
                exc_info=True,
            )
            
            # Handle failure callback
            await self.handle_job_failure(job_id, e)
            
            return result
            
        finally:
            # Remove from active runs
            if run_id in self._active_runs:
                del self._active_runs[run_id]
            
            # Save run result to persistence
            if self.persistence:
                await self.persistence.save_job_run(job_id, result)
    
    async def handle_job_success(
        self,
        job_id: str,
        result: JobRunResult,
    ) -> None:
        """
        Handle successful job execution.
        
        Args:
            job_id: Job identifier
            result: Execution result
        """
        logger.info(
            f"Job success callback: {job_id}",
            extra={
                "event": "job_success_callback",
                "job_id": job_id,
                "run_id": result.run_id,
            }
        )
        
        # Reset retry count on success
        if job_id in self._retry_counts:
            del self._retry_counts[job_id]
        
        # Update job in persistence
        if self.persistence:
            job = await self.persistence.load_job(job_id)
            if job:
                job.run_count += 1
                job.last_run_time = result.started_at
                await self.persistence.save_job(job)
    
    async def handle_job_failure(
        self,
        job_id: str,
        error: Exception,
    ) -> None:
        """
        Handle failed job execution.
        
        Implements retry logic and dead-letter integration.
        
        Args:
            job_id: Job identifier
            error: The exception that caused the failure
        """
        error_message = str(error)
        error_type = type(error).__name__
        
        logger.warning(
            f"Job failure callback: {job_id}",
            extra={
                "event": "job_failure_callback",
                "job_id": job_id,
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        
        # Check retry count
        retry_count = self._retry_counts.get(job_id, 0)
        
        if retry_count < self.max_retries:
            # Schedule retry
            self._retry_counts[job_id] = retry_count + 1
            
            logger.info(
                f"Scheduling retry {retry_count + 1}/{self.max_retries} for job: {job_id}",
                extra={
                    "event": "job_retry_scheduled",
                    "job_id": job_id,
                    "retry_count": retry_count + 1,
                    "max_retries": self.max_retries,
                }
            )
            
            # Note: Actual retry scheduling would be done by the scheduler service
            # This just tracks the retry state
        else:
            # Max retries exceeded - send to dead-letter queue
            logger.error(
                f"Max retries exceeded for job: {job_id}",
                extra={
                    "event": "job_max_retries_exceeded",
                    "job_id": job_id,
                    "retry_count": retry_count,
                }
            )
            
            await self._send_to_dead_letter(job_id, error)
    
    async def _send_to_dead_letter(
        self,
        job_id: str,
        error: Exception,
    ) -> bool:
        """
        Send a failed job to the dead-letter queue.
        
        Args:
            job_id: Job identifier
            error: The exception that caused the failure
            
        Returns:
            True if successfully sent to dead-letter queue
        """
        if not self.dead_letter_queue:
            # Try to get global dead-letter queue
            self.dead_letter_queue = get_dead_letter_queue()
        
        if not self.dead_letter_queue:
            logger.warning(
                f"No dead-letter queue available for job: {job_id}",
                extra={"event": "no_dead_letter_queue", "job_id": job_id}
            )
            return False
        
        try:
            # Get job details
            job_details = {}
            if self.persistence:
                job = await self.persistence.load_job(job_id)
                if job:
                    job_details = job.model_dump()
            
            # Add to dead-letter queue
            await self.dead_letter_queue.add(
                job_id=f"scheduler_{job_id}",
                payload={
                    "scheduler_job_id": job_id,
                    "job_details": job_details,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
                error_type=type(error).__name__,
                error_message=str(error),
            )
            
            logger.info(
                f"Job sent to dead-letter queue: {job_id}",
                extra={
                    "event": "job_sent_to_dead_letter",
                    "job_id": job_id,
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to send job to dead-letter queue: {job_id} - {e}",
                extra={
                    "event": "dead_letter_send_error",
                    "job_id": job_id,
                },
                exc_info=True,
            )
            return False
    
    async def _convert_to_dispatcher_job(
        self,
        job_id: str,
        action: Dict[str, Any],
        scheduled_job: Optional[ScheduledJob] = None,
    ) -> Job:
        """
        Convert a scheduled job action to a dispatcher job.
        
        Args:
            job_id: Scheduled job identifier
            action: Action configuration
            scheduled_job: Optional scheduled job for context
            
        Returns:
            Job instance for the dispatcher
        """
        action_type = action.get("type", "prompt")
        content = action.get("content", "")
        chat_id = action.get("chat_id")
        parameters = action.get("parameters", {})
        
        # Generate dispatcher job ID
        dispatcher_job_id = f"sched_{job_id}_{uuid4().hex[:8]}"
        
        # Build job based on action type
        if action_type == JobActionType.PROMPT.value or action_type == "prompt":
            # Create a prompt job
            job = Job(
                id=dispatcher_job_id,
                chat_id=chat_id or "scheduler",
                user_id="scheduler",
                prompt=content,
                mode=parameters.get("mode", "default"),
                priority=JobPriority.NORMAL,
                metadata={
                    "source": "scheduler",
                    "scheduler_job_id": job_id,
                    "action_type": action_type,
                    **parameters,
                },
            )
        
        elif action_type == JobActionType.SKILL.value or action_type == "skill":
            # Create a skill execution job
            job = Job(
                id=dispatcher_job_id,
                chat_id=chat_id or "scheduler",
                user_id="scheduler",
                prompt=f"Execute skill: {content}",
                mode=parameters.get("mode", "operator"),
                priority=JobPriority.NORMAL,
                metadata={
                    "source": "scheduler",
                    "scheduler_job_id": job_id,
                    "action_type": action_type,
                    "skill_name": content,
                    **parameters,
                },
            )
        
        elif action_type == JobActionType.TOOL_CALL.value or action_type == "tool_call":
            # Create a tool call job
            job = Job(
                id=dispatcher_job_id,
                chat_id=chat_id or "scheduler",
                user_id="scheduler",
                prompt=f"Execute tool: {content}",
                mode=parameters.get("mode", "operator"),
                priority=JobPriority.NORMAL,
                metadata={
                    "source": "scheduler",
                    "scheduler_job_id": job_id,
                    "action_type": action_type,
                    "tool_name": content,
                    "tool_params": parameters.get("tool_params", {}),
                    **parameters,
                },
            )
        
        else:
            # Default to prompt job
            job = Job(
                id=dispatcher_job_id,
                chat_id=chat_id or "scheduler",
                user_id="scheduler",
                prompt=content,
                mode=parameters.get("mode", "default"),
                priority=JobPriority.NORMAL,
                metadata={
                    "source": "scheduler",
                    "scheduler_job_id": job_id,
                    "action_type": action_type,
                    **parameters,
                },
            )
        
        return job
    
    def get_active_runs(self) -> List[JobRunResult]:
        """
        Get list of currently active job runs.
        
        Returns:
            List of JobRunResult instances
        """
        return list(self._active_runs.values())
    
    def get_retry_count(self, job_id: str) -> int:
        """
        Get the current retry count for a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Current retry count
        """
        return self._retry_counts.get(job_id, 0)
    
    def reset_retry_count(self, job_id: str) -> None:
        """
        Reset the retry count for a job.
        
        Args:
            job_id: Job identifier
        """
        if job_id in self._retry_counts:
            del self._retry_counts[job_id]


# Export
__all__ = [
    "SchedulerExecutor",
    "get_scheduler_executor",
    "set_scheduler_executor",
]