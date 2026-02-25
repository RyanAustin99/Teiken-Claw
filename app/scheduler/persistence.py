"""
Scheduler persistence for the Teiken Claw scheduler.

This module provides:
- SchedulerPersistence class for job persistence
- Database-backed storage for job configurations
- Job run history tracking
- Integration with SQLAlchemy models

Key Features:
    - Save and load scheduled jobs
    - Track job run history
    - Query job runs by job ID
    - Get last run for a job
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.db.models import SchedulerJobMeta, SchedulerJobRun
from app.scheduler.jobs import (
    ScheduledJob,
    JobRunResult,
    TriggerType,
    TriggerConfig,
    JobAction,
    JobStatus,
)

logger = logging.getLogger(__name__)

# Global persistence instance
_scheduler_persistence: Optional["SchedulerPersistence"] = None


def get_scheduler_persistence() -> Optional["SchedulerPersistence"]:
    """Get the global scheduler persistence instance."""
    return _scheduler_persistence


def set_scheduler_persistence(persistence: "SchedulerPersistence") -> None:
    """Set the global scheduler persistence instance."""
    global _scheduler_persistence
    _scheduler_persistence = persistence


class SchedulerPersistence:
    """
    Persistence layer for scheduled jobs.
    
    Provides database-backed storage for:
    - Job configurations and metadata
    - Job run history
    - Run statistics
    
    Example:
        persistence = SchedulerPersistence()
        
        # Save a job
        await persistence.save_job(scheduled_job)
        
        # Load a job
        job = await persistence.load_job("daily_report")
        
        # List jobs
        jobs = await persistence.list_jobs(enabled_only=True)
        
        # Save a run result
        await persistence.save_job_run("daily_report", run_result)
        
        # Get run history
        runs = await persistence.get_job_runs("daily_report", limit=10)
    """
    
    def __init__(self):
        """Initialize the scheduler persistence."""
        logger.info(
            "SchedulerPersistence initialized",
            extra={"event": "scheduler_persistence_initialized"}
        )
    
    async def save_job(self, job: ScheduledJob) -> bool:
        """
        Save a scheduled job to the database.
        
        Creates a new record or updates an existing one.
        
        Args:
            job: ScheduledJob to save
            
        Returns:
            True if saved successfully
        """
        try:
            async for session in get_async_session():
                # Check if job exists
                stmt = select(SchedulerJobMeta).where(
                    SchedulerJobMeta.job_id == job.job_id
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing record
                    existing.trigger_type = job.trigger_type.value if isinstance(job.trigger_type, TriggerType) else job.trigger_type
                    existing.trigger_config = job.trigger_config.model_dump(exclude_none=True)
                    existing.enabled = job.enabled
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new record
                    meta = SchedulerJobMeta(
                        job_id=job.job_id,
                        trigger_type=job.trigger_type.value if isinstance(job.trigger_type, TriggerType) else job.trigger_type,
                        trigger_config=job.trigger_config.model_dump(exclude_none=True),
                        enabled=job.enabled,
                    )
                    session.add(meta)
                
                await session.commit()
                
                logger.debug(
                    f"Saved job: {job.job_id}",
                    extra={"event": "job_saved", "job_id": job.job_id}
                )
                
                return True
                
        except Exception as e:
            logger.error(
                f"Failed to save job {job.job_id}: {e}",
                extra={"event": "job_save_error", "job_id": job.job_id},
                exc_info=True,
            )
            return False
    
    async def load_job(self, job_id: str) -> Optional[ScheduledJob]:
        """
        Load a scheduled job from the database.
        
        Args:
            job_id: Job identifier
            
        Returns:
            ScheduledJob or None if not found
        """
        try:
            async for session in get_async_session():
                stmt = select(SchedulerJobMeta).where(
                    SchedulerJobMeta.job_id == job_id
                )
                result = await session.execute(stmt)
                meta = result.scalar_one_or_none()
                
                if not meta:
                    return None
                
                # Convert to ScheduledJob
                job = self._meta_to_job(meta)
                
                logger.debug(
                    f"Loaded job: {job_id}",
                    extra={"event": "job_loaded", "job_id": job_id}
                )
                
                return job
                
        except Exception as e:
            logger.error(
                f"Failed to load job {job_id}: {e}",
                extra={"event": "job_load_error", "job_id": job_id},
                exc_info=True,
            )
            return None
    
    async def list_jobs(
        self,
        enabled_only: bool = False,
        trigger_type: Optional[TriggerType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ScheduledJob]:
        """
        List scheduled jobs from the database.
        
        Args:
            enabled_only: Only return enabled jobs
            trigger_type: Filter by trigger type
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of ScheduledJob instances
        """
        try:
            async for session in get_async_session():
                # Build query
                conditions = []
                
                if enabled_only:
                    conditions.append(SchedulerJobMeta.enabled == True)
                
                if trigger_type:
                    conditions.append(
                        SchedulerJobMeta.trigger_type == trigger_type.value
                    )
                
                stmt = select(SchedulerJobMeta)
                
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                
                stmt = stmt.order_by(desc(SchedulerJobMeta.created_at))
                stmt = stmt.limit(limit).offset(offset)
                
                result = await session.execute(stmt)
                metas = result.scalars().all()
                
                jobs = [self._meta_to_job(meta) for meta in metas]
                
                logger.debug(
                    f"Listed {len(jobs)} jobs",
                    extra={
                        "event": "jobs_listed",
                        "count": len(jobs),
                        "enabled_only": enabled_only,
                    }
                )
                
                return jobs
                
        except Exception as e:
            logger.error(
                f"Failed to list jobs: {e}",
                extra={"event": "jobs_list_error"},
                exc_info=True,
            )
            return []
    
    async def delete_job(self, job_id: str) -> bool:
        """
        Delete a scheduled job from the database.
        
        Also deletes associated run history.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if deleted successfully
        """
        try:
            async for session in get_async_session():
                # Find the job
                stmt = select(SchedulerJobMeta).where(
                    SchedulerJobMeta.job_id == job_id
                )
                result = await session.execute(stmt)
                meta = result.scalar_one_or_none()
                
                if not meta:
                    logger.warning(f"Job not found for deletion: {job_id}")
                    return False
                
                # Delete (cascade will handle runs)
                await session.delete(meta)
                await session.commit()
                
                logger.info(
                    f"Deleted job: {job_id}",
                    extra={"event": "job_deleted", "job_id": job_id}
                )
                
                return True
                
        except Exception as e:
            logger.error(
                f"Failed to delete job {job_id}: {e}",
                extra={"event": "job_delete_error", "job_id": job_id},
                exc_info=True,
            )
            return False
    
    async def save_job_run(
        self,
        job_id: str,
        result: JobRunResult,
    ) -> bool:
        """
        Save a job run result to the database.
        
        Args:
            job_id: Job identifier
            result: JobRunResult to save
            
        Returns:
            True if saved successfully
        """
        try:
            async for session in get_async_session():
                # Create run record
                run = SchedulerJobRun(
                    job_id=job_id,
                    status=result.status.value if isinstance(result.status, JobStatus) else result.status,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    error_message=result.error_message,
                )
                
                session.add(run)
                await session.commit()
                
                logger.debug(
                    f"Saved job run: {job_id}/{result.run_id}",
                    extra={
                        "event": "job_run_saved",
                        "job_id": job_id,
                        "run_id": result.run_id,
                    }
                )
                
                return True
                
        except Exception as e:
            logger.error(
                f"Failed to save job run {job_id}: {e}",
                extra={"event": "job_run_save_error", "job_id": job_id},
                exc_info=True,
            )
            return False
    
    async def get_job_runs(
        self,
        job_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobRunResult]:
        """
        Get run history for a job.
        
        Args:
            job_id: Job identifier
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of JobRunResult instances
        """
        try:
            async for session in get_async_session():
                stmt = select(SchedulerJobRun).where(
                    SchedulerJobRun.job_id == job_id
                ).order_by(
                    desc(SchedulerJobRun.started_at)
                ).limit(limit).offset(offset)
                
                result = await session.execute(stmt)
                runs = result.scalars().all()
                
                return [self._run_to_result(run) for run in runs]
                
        except Exception as e:
            logger.error(
                f"Failed to get job runs for {job_id}: {e}",
                extra={"event": "job_runs_get_error", "job_id": job_id},
                exc_info=True,
            )
            return []
    
    async def get_last_run(self, job_id: str) -> Optional[JobRunResult]:
        """
        Get the last run for a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobRunResult or None
        """
        try:
            async for session in get_async_session():
                stmt = select(SchedulerJobRun).where(
                    SchedulerJobRun.job_id == job_id
                ).order_by(
                    desc(SchedulerJobRun.started_at)
                ).limit(1)
                
                result = await session.execute(stmt)
                run = result.scalar_one_or_none()
                
                if run:
                    return self._run_to_result(run)
                
                return None
                
        except Exception as e:
            logger.error(
                f"Failed to get last run for {job_id}: {e}",
                extra={"event": "last_run_get_error", "job_id": job_id},
                exc_info=True,
            )
            return None
    
    async def get_job_count(self, enabled_only: bool = False) -> int:
        """
        Get the count of scheduled jobs.
        
        Args:
            enabled_only: Only count enabled jobs
            
        Returns:
            Number of jobs
        """
        try:
            async for session in get_async_session():
                from sqlalchemy import func
                
                stmt = select(func.count(SchedulerJobMeta.id))
                
                if enabled_only:
                    stmt = stmt.where(SchedulerJobMeta.enabled == True)
                
                result = await session.execute(stmt)
                count = result.scalar() or 0
                
                return count
                
        except Exception as e:
            logger.error(
                f"Failed to get job count: {e}",
                extra={"event": "job_count_error"},
                exc_info=True,
            )
            return 0
    
    async def get_run_stats(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get run statistics.
        
        Args:
            job_id: Optional job ID to filter by
            
        Returns:
            Dict with run statistics
        """
        try:
            async for session in get_async_session():
                from sqlalchemy import func
                
                # Build base query
                base_conditions = []
                if job_id:
                    base_conditions.append(SchedulerJobRun.job_id == job_id)
                
                # Total runs
                stmt = select(func.count(SchedulerJobRun.id))
                if base_conditions:
                    stmt = stmt.where(and_(*base_conditions))
                result = await session.execute(stmt)
                total_runs = result.scalar() or 0
                
                # Successful runs
                stmt = select(func.count(SchedulerJobRun.id)).where(
                    SchedulerJobRun.status == "completed"
                )
                if base_conditions:
                    stmt = stmt.where(and_(*base_conditions))
                result = await session.execute(stmt)
                successful_runs = result.scalar() or 0
                
                # Failed runs
                stmt = select(func.count(SchedulerJobRun.id)).where(
                    SchedulerJobRun.status == "failed"
                )
                if base_conditions:
                    stmt = stmt.where(and_(*base_conditions))
                result = await session.execute(stmt)
                failed_runs = result.scalar() or 0
                
                return {
                    "total_runs": total_runs,
                    "successful_runs": successful_runs,
                    "failed_runs": failed_runs,
                    "success_rate": successful_runs / total_runs if total_runs > 0 else 0,
                }
                
        except Exception as e:
            logger.error(
                f"Failed to get run stats: {e}",
                extra={"event": "run_stats_error"},
                exc_info=True,
            )
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "success_rate": 0,
            }
    
    def _meta_to_job(self, meta: SchedulerJobMeta) -> ScheduledJob:
        """
        Convert a SchedulerJobMeta to ScheduledJob.
        
        Args:
            meta: Database model instance
            
        Returns:
            ScheduledJob instance
        """
        trigger_config = meta.trigger_config or {}
        
        return ScheduledJob(
            job_id=meta.job_id,
            name=meta.job_id,  # Use job_id as name if not stored
            trigger_type=TriggerType(meta.trigger_type),
            trigger_config=TriggerConfig(**trigger_config),
            action=JobAction(type="prompt", content=""),  # Default action
            enabled=meta.enabled,
            created_at=meta.created_at,
            updated_at=meta.updated_at,
        )
    
    def _run_to_result(self, run: SchedulerJobRun) -> JobRunResult:
        """
        Convert a SchedulerJobRun to JobRunResult.
        
        Args:
            run: Database model instance
            
        Returns:
            JobRunResult instance
        """
        return JobRunResult(
            job_id=run.job_id,
            run_id=str(run.id),
            status=JobStatus(run.status),
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
        )


# Export
__all__ = [
    "SchedulerPersistence",
    "get_scheduler_persistence",
    "set_scheduler_persistence",
]
