"""
APScheduler service for the Teiken Claw scheduler.

This module provides:
- SchedulerService class for managing scheduled jobs
- Integration with APScheduler AsyncIOScheduler
- SQLite-backed job persistence
- Support for date, interval, and cron triggers

Key Features:
    - Async job scheduling and execution
    - Job persistence across restarts
    - Graceful startup and shutdown
    - Job management (add, remove, pause, resume)
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable, Union
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED

from app.config.settings import settings
from app.config.constants import DATA_DIR
from app.scheduler.jobs import (
    ScheduledJob,
    JobRunResult,
    TriggerType,
    JobStatus,
    JobAction,
    TriggerConfig,
    JobStats,
)
from app.scheduler.parser import ScheduleParser, ScheduleParseError

logger = logging.getLogger(__name__)

# Global scheduler service instance
_scheduler_service: Optional["SchedulerService"] = None


def get_scheduler_service() -> Optional["SchedulerService"]:
    """Get the global scheduler service instance."""
    return _scheduler_service


def set_scheduler_service(service: "SchedulerService") -> None:
    """Set the global scheduler service instance."""
    global _scheduler_service
    _scheduler_service = service


class SchedulerService:
    """
    APScheduler-based scheduler service.
    
    Provides job scheduling with:
    - SQLite-backed persistence
    - Async execution
    - Multiple trigger types (date, interval, cron)
    - Job management operations
    
    Example:
        scheduler = SchedulerService()
        await scheduler.start()
        
        # Add a cron job
        job = await scheduler.add_job(
            job_id="daily_report",
            name="Daily Report",
            trigger_type="cron",
            trigger_config={"cron_expression": "0 9 * * *"},
            action={"type": "prompt", "content": "Generate daily report"},
        )
        
        # List jobs
        jobs = await scheduler.list_jobs()
        
        # Stop scheduler
        await scheduler.stop()
    """
    
    def __init__(
        self,
        scheduler_db_path: Optional[str] = None,
        max_instances: int = 3,
        job_defaults: Optional[Dict[str, Any]] = None,
        executor_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[JobRunResult]]] = None,
        executor: Optional[Any] = None,
        persistence: Optional[Any] = None,
    ):
        """
        Initialize the scheduler service.
        
        Args:
            scheduler_db_path: Path to SQLite database for job persistence
            max_instances: Maximum concurrent job instances
            job_defaults: Default job configuration
            executor_callback: Async callback for job execution
            executor: Legacy scheduler executor object/callback
            persistence: Legacy scheduler persistence object
        """
        # Database path for job persistence
        if scheduler_db_path is None:
            db_dir = Path(DATA_DIR)
            db_dir.mkdir(parents=True, exist_ok=True)
            scheduler_db_path = str(db_dir / "scheduler.db")
        
        self.scheduler_db_path = scheduler_db_path
        self.max_instances = max_instances
        self.executor = executor
        self.persistence = persistence

        if executor_callback is not None:
            self.executor_callback = executor_callback
        elif executor is not None and hasattr(executor, "execute_job"):
            async def _executor_callback(job_id: str, action: Dict[str, Any]) -> JobRunResult:
                return await executor.execute_job(job_id, action)

            self.executor_callback = _executor_callback
        elif callable(executor):
            self.executor_callback = executor
        else:
            self.executor_callback = None
        
        # Default job configuration
        self.job_defaults = job_defaults or {
            "coalesce": True,  # Combine missed runs
            "max_instances": 1,  # One instance per job
            "misfire_grace_time": 300,  # 5 minutes grace for misfires
        }
        
        # Initialize scheduler components
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._parser = ScheduleParser()
        self._job_registry: Dict[str, ScheduledJob] = {}
        self._is_running = False
        
        logger.info(
            f"SchedulerService initialized (db: {scheduler_db_path})",
            extra={"event": "scheduler_service_initialized"}
        )
    
    async def start(self) -> Dict[str, Any]:
        """
        Start the scheduler.
        
        Initializes the AsyncIOScheduler with SQLite persistence
        and begins processing scheduled jobs.
        
        Returns:
            Dict with startup status
        """
        if self._is_running:
            logger.warning("Scheduler already running")
            return {"status": "already_running"}
        
        try:
            # Configure job stores
            jobstores = {
                "default": SQLAlchemyJobStore(
                    url=f"sqlite:///{self.scheduler_db_path}",
                    tablename="apscheduler_jobs",
                )
            }
            
            # Configure executors
            executors = {
                "default": ThreadPoolExecutor(max_workers=self.max_instances),
            }
            
            # Create scheduler
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=self.job_defaults,
                timezone="UTC",
            )
            
            # Start the scheduler
            self._scheduler.start()
            self._is_running = True
            
            # Load existing jobs into registry
            await self._load_jobs_from_store()
            
            logger.info(
                "Scheduler started",
                extra={
                    "event": "scheduler_started",
                    "job_count": len(self._job_registry),
                }
            )
            
            return {
                "status": "started",
                "job_count": len(self._job_registry),
                "db_path": self.scheduler_db_path,
            }
            
        except Exception as e:
            logger.error(
                f"Failed to start scheduler: {e}",
                extra={"event": "scheduler_start_error"},
                exc_info=True,
            )
            raise
    
    async def stop(self, wait: bool = True) -> Dict[str, Any]:
        """
        Stop the scheduler gracefully.
        
        Args:
            wait: Wait for running jobs to complete
            
        Returns:
            Dict with shutdown status
        """
        if not self._is_running or self._scheduler is None:
            logger.warning("Scheduler not running")
            return {"status": "not_running"}
        
        try:
            # Shutdown scheduler
            self._scheduler.shutdown(wait=wait)
            self._is_running = False
            
            logger.info(
                "Scheduler stopped",
                extra={"event": "scheduler_stopped"}
            )
            
            return {
                "status": "stopped",
                "wait": wait,
            }
            
        except Exception as e:
            logger.error(
                f"Error stopping scheduler: {e}",
                extra={"event": "scheduler_stop_error"},
                exc_info=True,
            )
            raise
    
    async def add_job(
        self,
        job_id: Optional[str] = None,
        name: str = "",
        trigger_type: Union[TriggerType, str] = TriggerType.DATE,
        trigger_config: Optional[Union[TriggerConfig, Dict[str, Any]]] = None,
        action: Optional[Union[JobAction, Dict[str, Any]]] = None,
        enabled: bool = True,
        **kwargs,
    ) -> ScheduledJob:
        """
        Add a new scheduled job.
        
        Args:
            job_id: Unique job identifier (auto-generated if not provided)
            name: Human-readable job name
            trigger_type: Type of trigger (date, interval, cron)
            trigger_config: Trigger configuration
            action: Action to perform when job runs
            enabled: Whether job is enabled
            **kwargs: Additional job configuration
            
        Returns:
            ScheduledJob instance
        """
        if not self._is_running:
            raise RuntimeError("Scheduler not running")
        
        # Generate job ID if not provided
        if job_id is None:
            job_id = f"job_{uuid4().hex[:12]}"
        
        # Normalize trigger type
        if isinstance(trigger_type, str):
            trigger_type = TriggerType(trigger_type.lower())
        
        # Normalize trigger config
        if trigger_config is None:
            trigger_config = {}
        if isinstance(trigger_config, TriggerConfig):
            trigger_config = trigger_config.model_dump(exclude_none=True)
        
        # Normalize action
        if action is None:
            raise ValueError("Action is required")
        if isinstance(action, JobAction):
            action_dict = action.model_dump(exclude_none=True)
        else:
            action_dict = action
            action = JobAction(**action_dict)
        
        # Parse trigger
        trigger = self._parser.parse_trigger(trigger_type, trigger_config)
        
        # Create job record
        scheduled_job = ScheduledJob(
            job_id=job_id,
            name=name or job_id,
            trigger_type=trigger_type,
            trigger_config=TriggerConfig(**trigger_config),
            action=action,
            enabled=enabled,
            created_at=datetime.utcnow(),
            max_instances=kwargs.get("max_instances", 1),
            misfire_grace_time=kwargs.get("misfire_grace_time", 300),
            coalesce=kwargs.get("coalesce", True),
            metadata=kwargs.get("metadata"),
        )
        
        # Add to APScheduler
        try:
            apscheduler_job = self._scheduler.add_job(
                func=self._execute_job,
                trigger=trigger,
                id=job_id,
                name=name or job_id,
                args=[job_id, action_dict],
                kwargs={},
                replace_existing=True,
                max_instances=scheduled_job.max_instances,
                misfire_grace_time=scheduled_job.misfire_grace_time,
                coalesce=scheduled_job.coalesce,
            )
            
            # Update next run time
            scheduled_job.next_run_time = apscheduler_job.next_run_time
            
            # Store in registry
            self._job_registry[job_id] = scheduled_job
            
            logger.info(
                f"Added job: {job_id}",
                extra={
                    "event": "job_added",
                    "job_id": job_id,
                    "trigger_type": trigger_type.value,
                    "next_run": str(scheduled_job.next_run_time),
                }
            )
            
            return scheduled_job
            
        except Exception as e:
            logger.error(
                f"Failed to add job {job_id}: {e}",
                extra={"event": "job_add_error"},
                exc_info=True,
            )
            raise
    
    async def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was removed
        """
        if not self._is_running:
            raise RuntimeError("Scheduler not running")
        
        try:
            self._scheduler.remove_job(job_id)
            
            # Remove from registry
            if job_id in self._job_registry:
                del self._job_registry[job_id]
            
            logger.info(
                f"Removed job: {job_id}",
                extra={"event": "job_removed", "job_id": job_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to remove job {job_id}: {e}",
                extra={"event": "job_remove_error"},
                exc_info=True,
            )
            return False
    
    async def pause_job(self, job_id: str) -> bool:
        """
        Pause a scheduled job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was paused
        """
        if not self._is_running:
            raise RuntimeError("Scheduler not running")
        
        try:
            self._scheduler.pause_job(job_id)
            
            # Update registry
            if job_id in self._job_registry:
                self._job_registry[job_id].enabled = False
            
            logger.info(
                f"Paused job: {job_id}",
                extra={"event": "job_paused", "job_id": job_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to pause job {job_id}: {e}",
                extra={"event": "job_pause_error"},
                exc_info=True,
            )
            return False
    
    async def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was resumed
        """
        if not self._is_running:
            raise RuntimeError("Scheduler not running")
        
        try:
            self._scheduler.resume_job(job_id)
            
            # Update registry
            if job_id in self._job_registry:
                self._job_registry[job_id].enabled = True
            
            logger.info(
                f"Resumed job: {job_id}",
                extra={"event": "job_resumed", "job_id": job_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to resume job {job_id}: {e}",
                extra={"event": "job_resume_error"},
                exc_info=True,
            )
            return False
    
    async def run_job_now(self, job_id: str) -> bool:
        """
        Trigger a job to run immediately.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was triggered
        """
        if not self._is_running:
            raise RuntimeError("Scheduler not running")
        
        try:
            job = self._scheduler.get_job(job_id)
            if job is None:
                logger.warning(f"Job not found: {job_id}")
                return False
            
            # Trigger the job
            self._scheduler.modify_job(job_id, next_run_time=datetime.utcnow())
            
            logger.info(
                f"Triggered job: {job_id}",
                extra={"event": "job_triggered", "job_id": job_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to trigger job {job_id}: {e}",
                extra={"event": "job_trigger_error"},
                exc_info=True,
            )
            return False
    
    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """
        Get a scheduled job by ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            ScheduledJob or None
        """
        return self._job_registry.get(job_id)
    
    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        """
        List all scheduled jobs.
        
        Args:
            enabled_only: Only return enabled jobs
            
        Returns:
            List of ScheduledJob instances
        """
        jobs = list(self._job_registry.values())
        
        if enabled_only:
            jobs = [j for j in jobs if j.enabled]
        
        return jobs
    
    def get_stats(self) -> JobStats:
        """
        Get scheduler statistics.
        
        Returns:
            JobStats instance
        """
        jobs = list(self._job_registry.values())
        
        return JobStats(
            total_jobs=len(jobs),
            enabled_jobs=sum(1 for j in jobs if j.enabled),
            disabled_jobs=sum(1 for j in jobs if not j.enabled),
            next_run_time=min(
                (j.next_run_time for j in jobs if j.next_run_time and j.enabled),
                default=None,
            ),
        )
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running

    @property
    def running(self) -> bool:
        """Property alias for scheduler run state."""
        return self._is_running
    
    @property
    def job_count(self) -> int:
        """Get number of registered jobs."""
        return len(self._job_registry)
    
    async def _execute_job(self, job_id: str, action: Dict[str, Any]) -> None:
        """
        Execute a scheduled job.
        
        This is the internal callback used by APScheduler.
        
        Args:
            job_id: Job identifier
            action: Action configuration
        """
        run_id = f"run_{uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        
        logger.info(
            f"Executing job: {job_id}",
            extra={
                "event": "job_execution_started",
                "job_id": job_id,
                "run_id": run_id,
            }
        )
        
        # Update job run count
        if job_id in self._job_registry:
            self._job_registry[job_id].run_count += 1
            self._job_registry[job_id].last_run_time = started_at
        
        try:
            # Call the executor callback if set
            if self.executor_callback:
                result = await self.executor_callback(job_id, action)
                logger.info(
                    f"Job completed: {job_id}",
                    extra={
                        "event": "job_execution_completed",
                        "job_id": job_id,
                        "run_id": run_id,
                        "status": result.status,
                    }
                )
            else:
                logger.warning(
                    f"No executor callback set for job: {job_id}",
                    extra={"event": "job_no_executor", "job_id": job_id}
                )
            
            # Update next run time from APScheduler
            if self._scheduler:
                apscheduler_job = self._scheduler.get_job(job_id)
                if apscheduler_job and job_id in self._job_registry:
                    self._job_registry[job_id].next_run_time = apscheduler_job.next_run_time
            
        except Exception as e:
            logger.error(
                f"Job execution failed: {job_id} - {e}",
                extra={
                    "event": "job_execution_failed",
                    "job_id": job_id,
                    "run_id": run_id,
                },
                exc_info=True,
            )
    
    async def _load_jobs_from_store(self) -> None:
        """
        Load existing jobs from the job store into the registry.
        
        This is called on startup to restore job metadata.
        """
        if not self._scheduler:
            return
        
        try:
            jobs = self._scheduler.get_jobs()
            
            for job in jobs:
                # Create minimal job record
                # Full job details should be loaded from persistence layer
                scheduled_job = ScheduledJob(
                    job_id=job.id,
                    name=job.name or job.id,
                    trigger_type=self._detect_trigger_type(job.trigger),
                    trigger_config=TriggerConfig(),
                    action=JobAction(type="prompt", content=""),
                    enabled=True,
                    next_run_time=job.next_run_time,
                )
                
                self._job_registry[job.id] = scheduled_job
            
            logger.info(
                f"Loaded {len(jobs)} jobs from store",
                extra={"event": "jobs_loaded_from_store"}
            )
            
        except Exception as e:
            logger.error(
                f"Error loading jobs from store: {e}",
                extra={"event": "job_load_error"},
                exc_info=True,
            )
    
    def _detect_trigger_type(
        self,
        trigger: Union[CronTrigger, IntervalTrigger, DateTrigger],
    ) -> TriggerType:
        """
        Detect trigger type from APScheduler trigger object.
        
        Args:
            trigger: APScheduler trigger instance
            
        Returns:
            TriggerType enum value
        """
        if isinstance(trigger, CronTrigger):
            return TriggerType.CRON
        elif isinstance(trigger, IntervalTrigger):
            return TriggerType.INTERVAL
        elif isinstance(trigger, DateTrigger):
            return TriggerType.DATE
        else:
            return TriggerType.DATE  # Default


# Type hint for Union
from typing import Union


# Export
__all__ = [
    "SchedulerService",
    "get_scheduler_service",
    "set_scheduler_service",
]
