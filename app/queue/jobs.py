"""
Job models and priorities for the Teiken Claw queue system.

This module defines:
- Job Pydantic model for queue jobs
- JobPriority enum for job ordering
- JobSource enum for job origin tracking
- JobType enum for job categorization
- create_job() factory function
"""

from datetime import datetime
from enum import IntEnum, Enum
from typing import Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class JobPriority(IntEnum):
    """
    Job priority levels for queue ordering.
    
    Lower numbers = higher priority (processed first).
    """
    INTERACTIVE = 10      # User-initiated chat messages (highest priority)
    SUBAGENT = 20         # Subagent tasks
    SCHEDULED = 30        # Scheduled/cron jobs
    MAINTENANCE = 40      # Background maintenance tasks (lowest priority)


class JobSource(str, Enum):
    """
    Source of a job - where it originated from.
    """
    TELEGRAM = "telegram"
    CLI = "cli"
    API = "api"
    SCHEDULER = "scheduler"
    SUBAGENT = "subagent"
    INTERNAL = "internal"


class JobType(str, Enum):
    """
    Type of job - what kind of work it represents.
    """
    CHAT_MESSAGE = "chat_message"
    SCHEDULED_TASK = "scheduled_task"
    SUBAGENT_TASK = "subagent_task"
    MEMORY_SYNC = "memory_sync"
    EMBEDDING_GENERATION = "embedding_generation"
    CLEANUP = "cleanup"
    NOTIFICATION = "notification"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class Job(BaseModel):
    """
    Job model for the priority queue.
    
    Represents a unit of work to be processed by the worker pool.
    Jobs are ordered by priority (lower number = higher priority).
    
    Attributes:
        job_id: Unique identifier for the job (UUID)
        source: Where the job originated from
        type: What kind of work this job represents
        priority: Priority level for ordering (lower = higher priority)
        chat_id: Optional Telegram chat ID for context
        session_id: Optional session ID for conversation tracking
        thread_id: Optional thread ID for message threading
        payload: Job-specific data as a dictionary
        idempotency_key: Optional key for deduplication
        attempts: Number of times this job has been attempted
        max_attempts: Maximum number of retry attempts
        created_at: When the job was created
        scheduled_at: Optional scheduled execution time
    """
    
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source: JobSource = Field(default=JobSource.INTERNAL)
    type: JobType = Field(default=JobType.CUSTOM)
    priority: int = Field(default=JobPriority.SCHEDULED)
    chat_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)
    thread_id: Optional[str] = Field(default=None)
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = Field(default=None)
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
    
    def __lt__(self, other: "Job") -> bool:
        """
        Compare jobs for priority queue ordering.
        
        Lower priority number = higher priority = processed first.
        For equal priorities, earlier created_at = processed first.
        """
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at
    
    def __le__(self, other: "Job") -> bool:
        """Less than or equal comparison for priority queue."""
        return self == other or self < other
    
    def __gt__(self, other: "Job") -> bool:
        """Greater than comparison for priority queue."""
        return not self <= other
    
    def __ge__(self, other: "Job") -> bool:
        """Greater than or equal comparison for priority queue."""
        return not self < other
    
    def increment_attempts(self) -> "Job":
        """Return a new Job with attempts incremented."""
        return Job(
            job_id=self.job_id,
            source=self.source,
            type=self.type,
            priority=self.priority,
            chat_id=self.chat_id,
            session_id=self.session_id,
            thread_id=self.thread_id,
            payload=self.payload,
            idempotency_key=self.idempotency_key,
            attempts=self.attempts + 1,
            max_attempts=self.max_attempts,
            created_at=self.created_at,
            scheduled_at=self.scheduled_at,
        )
    
    def can_retry(self) -> bool:
        """Check if this job can be retried."""
        return self.attempts < self.max_attempts
    
    def to_queue_item(self) -> tuple:
        """
        Convert to a tuple for asyncio.PriorityQueue.
        
        Returns a tuple of (priority, created_at, job) for proper ordering.
        """
        return (self.priority, self.created_at, self)

    @property
    def id(self) -> str:
        """Backward-compatible alias for job_id."""
        return self.job_id

    @property
    def message(self) -> str:
        """Backward-compatible message accessor from payload."""
        return self.payload.get("text", "") or self.payload.get("message", "")


def create_job(
    source: JobSource,
    type: JobType,
    payload: Dict[str, Any],
    priority: int = JobPriority.SCHEDULED,
    chat_id: Optional[str] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 3,
    scheduled_at: Optional[datetime] = None,
) -> Job:
    """
    Factory function to create a Job with proper defaults.
    
    Args:
        source: Where the job originated from
        type: What kind of work this job represents
        payload: Job-specific data
        priority: Priority level (default: SCHEDULED)
        chat_id: Optional Telegram chat ID
        session_id: Optional session ID
        thread_id: Optional thread ID
        idempotency_key: Optional key for deduplication
        max_attempts: Maximum retry attempts (default: 3)
        scheduled_at: Optional scheduled execution time
    
    Returns:
        Job: A new Job instance
    
    Example:
        >>> job = create_job(
        ...     source=JobSource.TELEGRAM,
        ...     type=JobType.CHAT_MESSAGE,
        ...     payload={"text": "Hello!"},
        ...     priority=JobPriority.INTERACTIVE,
        ...     chat_id="123456",
        ... )
    """
    return Job(
        source=source,
        type=type,
        payload=payload,
        priority=priority,
        chat_id=chat_id,
        session_id=session_id,
        thread_id=thread_id,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        scheduled_at=scheduled_at,
    )


__all__ = [
    "Job",
    "JobPriority",
    "JobSource",
    "JobType",
    "create_job",
]
