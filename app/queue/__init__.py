"""Queue package exports.

This module intentionally uses lazy attribute loading to avoid import-time
dependency cycles between queue, agent runtime, and interface modules.
"""

from importlib import import_module
from typing import Any

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

_EXPORT_MAP = {
    # jobs
    "Job": ("app.queue.jobs", "Job"),
    "JobPriority": ("app.queue.jobs", "JobPriority"),
    "JobSource": ("app.queue.jobs", "JobSource"),
    "JobType": ("app.queue.jobs", "JobType"),
    "create_job": ("app.queue.jobs", "create_job"),
    # dispatcher
    "JobDispatcher": ("app.queue.dispatcher", "JobDispatcher"),
    "QueueFullError": ("app.queue.dispatcher", "QueueFullError"),
    "DuplicateJobError": ("app.queue.dispatcher", "DuplicateJobError"),
    "get_dispatcher": ("app.queue.dispatcher", "get_dispatcher"),
    "set_dispatcher": ("app.queue.dispatcher", "set_dispatcher"),
    # locks
    "LockManager": ("app.queue.locks", "LockManager"),
    "LockInfo": ("app.queue.locks", "LockInfo"),
    "LockTimeoutError": ("app.queue.locks", "LockTimeoutError"),
    "get_lock_manager": ("app.queue.locks", "get_lock_manager"),
    "set_lock_manager": ("app.queue.locks", "set_lock_manager"),
    # workers
    "WorkerPool": ("app.queue.workers", "WorkerPool"),
    "WorkerStatus": ("app.queue.workers", "WorkerStatus"),
    "WorkerInfo": ("app.queue.workers", "WorkerInfo"),
    "JobHandler": ("app.queue.workers", "JobHandler"),
    "get_worker_pool": ("app.queue.workers", "get_worker_pool"),
    "set_worker_pool": ("app.queue.workers", "set_worker_pool"),
    # throttles
    "RateLimiter": ("app.queue.throttles", "RateLimiter"),
    "OutboundQueue": ("app.queue.throttles", "OutboundQueue"),
    "OutboundMessage": ("app.queue.throttles", "OutboundMessage"),
    "MessageStatus": ("app.queue.throttles", "MessageStatus"),
    "get_rate_limiter": ("app.queue.throttles", "get_rate_limiter"),
    "set_rate_limiter": ("app.queue.throttles", "set_rate_limiter"),
    "get_outbound_queue": ("app.queue.throttles", "get_outbound_queue"),
    "set_outbound_queue": ("app.queue.throttles", "set_outbound_queue"),
    # dead letter
    "DeadLetterQueue": ("app.queue.dead_letter", "DeadLetterQueue"),
    "DeadLetterError": ("app.queue.dead_letter", "DeadLetterError"),
    "JobNotFoundError": ("app.queue.dead_letter", "JobNotFoundError"),
    "ReplayError": ("app.queue.dead_letter", "ReplayError"),
    "get_dead_letter_queue": ("app.queue.dead_letter", "get_dead_letter_queue"),
    "set_dead_letter_queue": ("app.queue.dead_letter", "set_dead_letter_queue"),
}


def __getattr__(name: str) -> Any:
    """Lazily resolve queue exports to prevent import-time cycles."""
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module 'app.queue' has no attribute '{name}'")
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
