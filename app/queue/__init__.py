# Queue package
"""
Queue module for Teiken Claw.

Contains the job queue system with:
- Job models and priorities
- Priority-based dispatcher
- Worker pool for async processing
- Per-chat/session locks
- Rate limiting and outbound queue
- Dead-letter queue for failed jobs
"""

from app.queue.jobs import (
    Job,
    JobPriority,
    JobSource,
    JobType,
    create_job,
)
from app.queue.dispatcher import (
    JobDispatcher,
    QueueFullError,
    DuplicateJobError,
    get_dispatcher,
    set_dispatcher,
)
from app.queue.locks import (
    LockManager,
    LockInfo,
    LockTimeoutError,
    get_lock_manager,
    set_lock_manager,
)
from app.queue.workers import (
    WorkerPool,
    WorkerStatus,
    WorkerInfo,
    JobHandler,
    get_worker_pool,
    set_worker_pool,
)
from app.queue.throttles import (
    RateLimiter,
    OutboundQueue,
    OutboundMessage,
    MessageStatus,
    get_rate_limiter,
    set_rate_limiter,
    get_outbound_queue,
    set_outbound_queue,
)
from app.queue.dead_letter import (
    DeadLetterQueue,
    DeadLetterError,
    JobNotFoundError,
    ReplayError,
    get_dead_letter_queue,
    set_dead_letter_queue,
)


__all__ = [
    # Jobs
    "Job",
    "JobPriority",
    "JobSource",
    "JobType",
    "create_job",
    # Dispatcher
    "JobDispatcher",
    "QueueFullError",
    "DuplicateJobError",
    "get_dispatcher",
    "set_dispatcher",
    # Locks
    "LockManager",
    "LockInfo",
    "LockTimeoutError",
    "get_lock_manager",
    "set_lock_manager",
    # Workers
    "WorkerPool",
    "WorkerStatus",
    "WorkerInfo",
    "JobHandler",
    "get_worker_pool",
    "set_worker_pool",
    # Throttles
    "RateLimiter",
    "OutboundQueue",
    "OutboundMessage",
    "MessageStatus",
    "get_rate_limiter",
    "set_rate_limiter",
    "get_outbound_queue",
    "set_outbound_queue",
    # Dead Letter
    "DeadLetterQueue",
    "DeadLetterError",
    "JobNotFoundError",
    "ReplayError",
    "get_dead_letter_queue",
    "set_dead_letter_queue",
]
