"""
Dead-letter queue management for failed jobs.

This module provides:
- DeadLetterQueue class for storing failed jobs
- Database persistence via JobDeadLetter model
- Replay functionality for retrying failed jobs
- Admin operations for managing dead-letter entries
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.config.settings import settings
from app.db.session import get_session
from app.db.models import JobDeadLetter
from app.queue.jobs import Job, JobSource, JobType

logger = get_logger(__name__)


class DeadLetterError(Exception):
    """Base exception for dead-letter queue errors."""
    pass


class JobNotFoundError(DeadLetterError):
    """Raised when a job is not found in the dead-letter queue."""
    pass


class ReplayError(DeadLetterError):
    """Raised when a job cannot be replayed."""
    pass


class DeadLetterQueue:
    """
    Dead-letter queue for failed jobs.
    
    Stores jobs that have failed after maximum retry attempts.
    Provides functionality to:
    - Store failed jobs with error details
    - List and retrieve dead-letter entries
    - Replay jobs back to the dispatcher
    - Delete or clear entries
    
    Attributes:
        dispatcher: Optional JobDispatcher for replay functionality
    """
    
    def __init__(self, dispatcher: Optional[Any] = None):
        """
        Initialize the dead-letter queue.
        
        Args:
            dispatcher: Optional JobDispatcher instance for replay
        """
        self._dispatcher = dispatcher
        
        # Statistics
        self._total_added = 0
        self._total_replayed = 0
        self._total_deleted = 0
        
        logger.info(
            "DeadLetterQueue initialized",
            extra={"event": "dead_letter_queue_initialized"}
        )
    
    def set_dispatcher(self, dispatcher: Any) -> None:
        """Set the dispatcher for replay functionality."""
        self._dispatcher = dispatcher
    
    async def add(self, job: Job, error: Exception) -> str:
        """
        Add a failed job to the dead-letter queue.
        
        Args:
            job: The failed Job
            error: The exception that caused the failure
        
        Returns:
            str: The database ID of the dead-letter entry
        """
        async with get_session() as session:
            # Create dead-letter entry
            entry = JobDeadLetter(
                job_id=job.job_id,
                payload=job.model_dump_json(),
                error_type=type(error).__name__,
                error_message=str(error),
                attempts=job.attempts,
                created_at=datetime.utcnow(),
                last_attempt_at=datetime.utcnow(),
            )
            
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            
            self._total_added += 1
            
            logger.warning(
                f"Job added to dead-letter queue: {job.job_id}",
                extra={
                    "event": "dead_letter_added",
                    "job_id": job.job_id,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "attempts": job.attempts,
                    "entry_id": entry.id,
                }
            )
            
            return str(entry.id)
    
    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        error_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List dead-letter entries.
        
        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            error_type: Optional filter by error type
        
        Returns:
            list: List of dead-letter entry dictionaries
        """
        async with get_session() as session:
            query = select(JobDeadLetter).order_by(
                JobDeadLetter.created_at.desc()
            ).offset(offset).limit(limit)
            
            if error_type:
                query = query.where(JobDeadLetter.error_type == error_type)
            
            result = await session.execute(query)
            entries = result.scalars().all()
            
            return [
                {
                    "id": entry.id,
                    "job_id": entry.job_id,
                    "payload": entry.payload,
                    "error_type": entry.error_type,
                    "error_message": entry.error_message,
                    "attempts": entry.attempts,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "last_attempt_at": entry.last_attempt_at.isoformat() if entry.last_attempt_at else None,
                }
                for entry in entries
            ]
    
    async def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific dead-letter entry by job ID.
        
        Args:
            job_id: The job ID to look up
        
        Returns:
            dict: Dead-letter entry or None if not found
        """
        async with get_session() as session:
            query = select(JobDeadLetter).where(JobDeadLetter.job_id == job_id)
            result = await session.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry is None:
                return None
            
            return {
                "id": entry.id,
                "job_id": entry.job_id,
                "payload": entry.payload,
                "error_type": entry.error_type,
                "error_message": entry.error_message,
                "attempts": entry.attempts,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "last_attempt_at": entry.last_attempt_at.isoformat() if entry.last_attempt_at else None,
            }
    
    async def get_by_id(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific dead-letter entry by database ID.
        
        Args:
            entry_id: The database ID of the entry
        
        Returns:
            dict: Dead-letter entry or None if not found
        """
        async with get_session() as session:
            query = select(JobDeadLetter).where(JobDeadLetter.id == entry_id)
            result = await session.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry is None:
                return None
            
            return {
                "id": entry.id,
                "job_id": entry.job_id,
                "payload": entry.payload,
                "error_type": entry.error_type,
                "error_message": entry.error_message,
                "attempts": entry.attempts,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "last_attempt_at": entry.last_attempt_at.isoformat() if entry.last_attempt_at else None,
            }
    
    async def replay(self, job_id: str) -> bool:
        """
        Replay a failed job by re-queuing it to the dispatcher.
        
        Args:
            job_id: The job ID to replay
        
        Returns:
            bool: True if replay was successful
        
        Raises:
            JobNotFoundError: If job is not found in dead-letter queue
            ReplayError: If dispatcher is not available or re-queue fails
        """
        if not self._dispatcher:
            raise ReplayError("Dispatcher not available for replay")
        
        # Get the dead-letter entry
        entry = await self.get(job_id)
        if entry is None:
            raise JobNotFoundError(f"Job {job_id} not found in dead-letter queue")
        
        try:
            # Parse the job from stored payload
            payload_dict = json.loads(entry["payload"])
            
            # Create a new Job instance
            job = Job(
                job_id=payload_dict.get("job_id"),
                source=payload_dict.get("source", JobSource.INTERNAL),
                type=payload_dict.get("type", JobType.CUSTOM),
                priority=payload_dict.get("priority", 30),
                chat_id=payload_dict.get("chat_id"),
                session_id=payload_dict.get("session_id"),
                thread_id=payload_dict.get("thread_id"),
                payload=payload_dict.get("payload", {}),
                idempotency_key=payload_dict.get("idempotency_key"),
                attempts=0,  # Reset attempts
                max_attempts=payload_dict.get("max_attempts", 3),
                created_at=datetime.utcnow(),  # New timestamp
                scheduled_at=payload_dict.get("scheduled_at"),
            )
            
            # Enqueue to dispatcher
            await self._dispatcher.enqueue(job)
            
            # Delete from dead-letter queue
            await self.delete(job_id)
            
            self._total_replayed += 1
            
            logger.info(
                f"Job replayed: {job_id}",
                extra={
                    "event": "dead_letter_replayed",
                    "job_id": job_id,
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to replay job {job_id}: {e}",
                extra={
                    "event": "dead_letter_replay_failed",
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise ReplayError(f"Failed to replay job: {e}")
    
    async def delete(self, job_id: str) -> bool:
        """
        Delete a job from the dead-letter queue.
        
        Args:
            job_id: The job ID to delete
        
        Returns:
            bool: True if deleted, False if not found
        """
        async with get_session() as session:
            query = delete(JobDeadLetter).where(JobDeadLetter.job_id == job_id)
            result = await session.execute(query)
            await session.commit()
            
            deleted = result.rowcount > 0
            
            if deleted:
                self._total_deleted += 1
                logger.info(
                    f"Job deleted from dead-letter queue: {job_id}",
                    extra={
                        "event": "dead_letter_deleted",
                        "job_id": job_id,
                    }
                )
            
            return deleted
    
    async def delete_by_id(self, entry_id: int) -> bool:
        """
        Delete a dead-letter entry by database ID.
        
        Args:
            entry_id: The database ID of the entry
        
        Returns:
            bool: True if deleted, False if not found
        """
        async with get_session() as session:
            query = delete(JobDeadLetter).where(JobDeadLetter.id == entry_id)
            result = await session.execute(query)
            await session.commit()
            
            deleted = result.rowcount > 0
            
            if deleted:
                self._total_deleted += 1
                logger.info(
                    f"Dead-letter entry deleted: {entry_id}",
                    extra={
                        "event": "dead_letter_deleted",
                        "entry_id": entry_id,
                    }
                )
            
            return deleted
    
    async def clear(self, older_than_days: Optional[int] = None) -> int:
        """
        Clear dead-letter entries.
        
        Args:
            older_than_days: Only clear entries older than this many days.
                           If None, clears all entries (admin only).
        
        Returns:
            int: Number of entries deleted
        """
        async with get_session() as session:
            if older_than_days is not None:
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(days=older_than_days)
                query = delete(JobDeadLetter).where(
                    JobDeadLetter.created_at < cutoff
                )
            else:
                query = delete(JobDeadLetter)
            
            result = await session.execute(query)
            await session.commit()
            
            deleted_count = result.rowcount
            self._total_deleted += deleted_count
            
            logger.warning(
                f"Cleared {deleted_count} dead-letter entries",
                extra={
                    "event": "dead_letter_cleared",
                    "count": deleted_count,
                    "older_than_days": older_than_days,
                }
            )
            
            return deleted_count
    
    async def count(self, error_type: Optional[str] = None) -> int:
        """
        Count dead-letter entries.
        
        Args:
            error_type: Optional filter by error type
        
        Returns:
            int: Number of entries
        """
        async with get_session() as session:
            if error_type:
                query = select(func.count()).select_from(JobDeadLetter).where(
                    JobDeadLetter.error_type == error_type
                )
            else:
                query = select(func.count()).select_from(JobDeadLetter)
            
            result = await session.execute(query)
            return result.scalar() or 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get dead-letter queue statistics.
        
        Returns:
            dict: Statistics about the dead-letter queue
        """
        return {
            "total_added": self._total_added,
            "total_replayed": self._total_replayed,
            "total_deleted": self._total_deleted,
            "has_dispatcher": self._dispatcher is not None,
        }
    
    async def get_error_summary(self) -> List[Dict[str, Any]]:
        """
        Get a summary of errors by type.
        
        Returns:
            list: List of error types with counts
        """
        async with get_session() as session:
            query = select(
                JobDeadLetter.error_type,
                func.count(JobDeadLetter.id).label("count"),
            ).group_by(JobDeadLetter.error_type).order_by(
                func.count(JobDeadLetter.id).desc()
            )
            
            result = await session.execute(query)
            return [
                {"error_type": row.error_type, "count": row.count}
                for row in result.all()
            ]


# Global dead-letter queue instance (initialized by main app)
_dead_letter_queue: Optional[DeadLetterQueue] = None


def get_dead_letter_queue() -> Optional[DeadLetterQueue]:
    """Get the global dead-letter queue instance."""
    return _dead_letter_queue


def set_dead_letter_queue(queue: DeadLetterQueue) -> None:
    """Set the global dead-letter queue instance."""
    global _dead_letter_queue
    _dead_letter_queue = queue


__all__ = [
    "DeadLetterQueue",
    "DeadLetterError",
    "JobNotFoundError",
    "ReplayError",
    "get_dead_letter_queue",
    "set_dead_letter_queue",
]
