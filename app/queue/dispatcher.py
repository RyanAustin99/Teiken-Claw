"""
Job dispatcher for the Teiken Claw queue system.

This module provides:
- JobDispatcher class for managing job queues
- Priority queue implementation with asyncio
- Idempotency key deduplication
- Queue backpressure handling
- Integration with dead-letter queue
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Set, Dict, Any
from contextlib import asynccontextmanager

from app.config.logging import get_logger
from app.queue.jobs import Job, JobPriority

logger = get_logger(__name__)


class QueueFullError(Exception):
    """Raised when the queue is at maximum capacity."""
    pass


class DuplicateJobError(Exception):
    """Raised when a job with the same idempotency key already exists."""
    pass


class JobDispatcher:
    """
    Priority-based job dispatcher.
    
    Manages an in-memory priority queue for job processing with:
    - Priority ordering (lower number = higher priority)
    - Idempotency key deduplication
    - Queue backpressure handling
    - Pending job tracking
    - Dead-letter queue integration
    
    Attributes:
        max_size: Maximum queue capacity
        queue: asyncio.PriorityQueue for job ordering
        pending_jobs: Set of currently processing job IDs
        idempotency_keys: Set of seen idempotency keys for deduplication
        idempotency_ttl: Time-to-live for idempotency keys
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        idempotency_ttl_seconds: int = 3600,
        dead_letter_queue: Optional[Any] = None,
    ):
        """
        Initialize the job dispatcher.
        
        Args:
            max_size: Maximum number of jobs in the queue
            idempotency_ttl_seconds: TTL for idempotency key cache
            dead_letter_queue: Optional DeadLetterQueue instance
        """
        self.max_size = max_size
        self.idempotency_ttl = timedelta(seconds=idempotency_ttl_seconds)
        self._dead_letter_queue = dead_letter_queue
        
        # Priority queue for job ordering
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        
        # Track pending jobs (currently being processed)
        self._pending_jobs: Set[str] = set()
        
        # Idempotency key tracking with timestamps
        self._idempotency_keys: Dict[str, datetime] = {}
        
        # Statistics
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_rejected = 0
        self._total_duplicates = 0
        
        # Shutdown flag
        self._shutdown = False
        
        logger.info(
            f"JobDispatcher initialized with max_size={max_size}",
            extra={"event": "dispatcher_initialized"}
        )
    
    @property
    def queue_depth(self) -> int:
        """Current number of jobs in the queue."""
        return self._queue.qsize()
    
    @property
    def pending_count(self) -> int:
        """Number of jobs currently being processed."""
        return len(self._pending_jobs)
    
    @property
    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        return self.queue_depth >= self.max_size
    
    @property
    def is_shutdown(self) -> bool:
        """Check if dispatcher is shut down."""
        return self._shutdown
    
    def _cleanup_idempotency_keys(self) -> None:
        """Remove expired idempotency keys."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, timestamp in self._idempotency_keys.items()
            if now - timestamp > self.idempotency_ttl
        ]
        for key in expired_keys:
            del self._idempotency_keys[key]
        
        if expired_keys:
            logger.debug(
                f"Cleaned up {len(expired_keys)} expired idempotency keys",
                extra={"event": "idempotency_cleanup"}
            )
    
    async def enqueue(self, job: Job) -> bool:
        """
        Add a job to the queue.
        
        Args:
            job: The Job to enqueue
        
        Returns:
            bool: True if job was enqueued successfully
        
        Raises:
            QueueFullError: If queue is at maximum capacity
            DuplicateJobError: If job with same idempotency key exists
        """
        if self._shutdown:
            logger.warning(
                f"Rejecting job {job.job_id}: dispatcher is shut down",
                extra={"event": "job_rejected_shutdown", "job_id": job.job_id}
            )
            self._total_rejected += 1
            return False
        
        # Cleanup expired idempotency keys
        self._cleanup_idempotency_keys()
        
        # Check for duplicate via idempotency key
        if job.idempotency_key:
            if job.idempotency_key in self._idempotency_keys:
                logger.warning(
                    f"Duplicate job rejected: idempotency_key={job.idempotency_key}",
                    extra={
                        "event": "job_duplicate",
                        "job_id": job.job_id,
                        "idempotency_key": job.idempotency_key,
                    }
                )
                self._total_duplicates += 1
                raise DuplicateJobError(
                    f"Job with idempotency key '{job.idempotency_key}' already exists"
                )
            # Mark this key as seen
            self._idempotency_keys[job.idempotency_key] = datetime.utcnow()
        
        # Check queue capacity
        if self.is_full:
            logger.warning(
                f"Queue full, rejecting job {job.job_id}",
                extra={
                    "event": "job_rejected_full",
                    "job_id": job.job_id,
                    "queue_depth": self.queue_depth,
                    "max_size": self.max_size,
                }
            )
            self._total_rejected += 1
            raise QueueFullError(
                f"Queue is at maximum capacity ({self.max_size})"
            )
        
        # Add to priority queue
        queue_item = job.to_queue_item()
        await self._queue.put(queue_item)
        self._total_enqueued += 1
        
        logger.info(
            f"Job enqueued: {job.job_id}",
            extra={
                "event": "job_enqueued",
                "job_id": job.job_id,
                "source": job.source,
                "type": job.type,
                "priority": job.priority,
                "chat_id": job.chat_id,
                "queue_depth": self.queue_depth,
            }
        )
        
        return True
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Job]:
        """
        Get the next job from the queue.
        
        Args:
            timeout: Maximum time to wait for a job (None = wait forever)
        
        Returns:
            Job: The next job to process, or None if timeout
        """
        if self._shutdown and self.queue_depth == 0:
            return None
        
        try:
            if timeout is not None:
                queue_item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout
                )
            else:
                queue_item = await self._queue.get()
            
            # Unpack the queue item (priority, created_at, job)
            _, _, job = queue_item
            
            # Track as pending
            self._pending_jobs.add(job.job_id)
            self._total_dequeued += 1
            
            logger.debug(
                f"Job dequeued: {job.job_id}",
                extra={
                    "event": "job_dequeued",
                    "job_id": job.job_id,
                    "queue_depth": self.queue_depth,
                    "pending_count": len(self._pending_jobs),
                }
            )
            
            return job
            
        except asyncio.TimeoutError:
            return None
    
    def mark_complete(self, job_id: str) -> None:
        """
        Mark a job as completed (remove from pending).
        
        Args:
            job_id: The job ID to mark as complete
        """
        self._pending_jobs.discard(job_id)
        logger.debug(
            f"Job marked complete: {job_id}",
            extra={
                "event": "job_complete",
                "job_id": job_id,
                "pending_count": len(self._pending_jobs),
            }
        )
    
    async def mark_failed(self, job: Job, error: Exception) -> None:
        """
        Mark a job as failed.
        
        If the job can be retried, it will be re-enqueued.
        Otherwise, it will be sent to the dead-letter queue.
        
        Args:
            job: The failed Job
            error: The exception that caused the failure
        """
        self._pending_jobs.discard(job.job_id)
        
        # Increment attempts
        updated_job = job.increment_attempts()
        
        if updated_job.can_retry():
            # Re-enqueue for retry
            logger.warning(
                f"Job failed, will retry: {job.job_id} (attempt {updated_job.attempts}/{updated_job.max_attempts})",
                extra={
                    "event": "job_retry",
                    "job_id": job.job_id,
                    "attempt": updated_job.attempts,
                    "max_attempts": updated_job.max_attempts,
                    "error": str(error),
                }
            )
            try:
                await self.enqueue(updated_job)
            except (QueueFullError, DuplicateJobError) as e:
                logger.error(
                    f"Failed to re-enqueue job {job.job_id}: {e}",
                    extra={"event": "job_retry_failed", "job_id": job.job_id}
                )
                if self._dead_letter_queue:
                    await self._dead_letter_queue.add(job, error)
        else:
            # Max attempts reached, send to dead-letter
            logger.error(
                f"Job failed permanently: {job.job_id}",
                extra={
                    "event": "job_failed_permanent",
                    "job_id": job.job_id,
                    "attempts": updated_job.attempts,
                    "error": str(error),
                }
            )
            if self._dead_letter_queue:
                await self._dead_letter_queue.add(job, error)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get dispatcher statistics.
        
        Returns:
            dict: Statistics about the dispatcher state
        """
        return {
            "queue_depth": self.queue_depth,
            "max_size": self.max_size,
            "pending_count": len(self._pending_jobs),
            "idempotency_keys_cached": len(self._idempotency_keys),
            "total_enqueued": self._total_enqueued,
            "total_dequeued": self._total_dequeued,
            "total_rejected": self._total_rejected,
            "total_duplicates": self._total_duplicates,
            "is_shutdown": self._shutdown,
        }
    
    async def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the dispatcher.
        
        Args:
            wait: If True, wait for pending jobs to complete
        """
        logger.info(
            "JobDispatcher shutting down",
            extra={
                "event": "dispatcher_shutdown",
                "pending_count": len(self._pending_jobs),
                "queue_depth": self.queue_depth,
            }
        )
        
        self._shutdown = True
        
        if wait:
            # Wait for pending jobs to complete
            while self._pending_jobs:
                logger.debug(
                    f"Waiting for {len(self._pending_jobs)} pending jobs",
                    extra={"event": "dispatcher_shutdown_wait"}
                )
                await asyncio.sleep(0.1)
        
        logger.info(
            "JobDispatcher shutdown complete",
            extra={"event": "dispatcher_shutdown_complete"}
        )
    
    @asynccontextmanager
    async def process_job(self, timeout: Optional[float] = None):
        """
        Context manager for processing a job.
        
        Automatically handles marking jobs as complete or failed.
        
        Args:
            timeout: Maximum time to wait for a job
        
        Yields:
            Job: The job to process, or None if no job available
        """
        job = await self.dequeue(timeout)
        if job is None:
            yield None
            return
        
        try:
            yield job
            self.mark_complete(job.job_id)
        except Exception as e:
            await self.mark_failed(job, e)
            raise


# Global dispatcher instance (initialized by main app)
_dispatcher: Optional[JobDispatcher] = None


def get_dispatcher() -> Optional[JobDispatcher]:
    """Get the global dispatcher instance."""
    return _dispatcher


def set_dispatcher(dispatcher: JobDispatcher) -> None:
    """Set the global dispatcher instance."""
    global _dispatcher
    _dispatcher = dispatcher


__all__ = [
    "JobDispatcher",
    "QueueFullError",
    "DuplicateJobError",
    "get_dispatcher",
    "set_dispatcher",
]
