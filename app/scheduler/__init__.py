# Scheduler package
"""
Scheduler module for Teiken Claw.

Contains task scheduling and cron jobs using APScheduler:
- SchedulerService: Main scheduler service with APScheduler integration
- SchedulerExecutor: Job execution bridge to dispatcher
- ControlStateManager: System pause/resume control
- SchedulerPersistence: Job and run history persistence
- ScheduleParser: Schedule expression parsing
- Job models: ScheduledJob, JobRunResult, etc.

Phase 9 Implementation:
    - APScheduler with AsyncIOScheduler
    - SQLite-backed job persistence
    - Date, interval, and cron triggers
    - Control state management (pause modes)
    - Dead-letter integration for failed jobs
"""

from app.scheduler.jobs import (
    TriggerType,
    JobStatus,
    JobActionType,
    JobAction,
    TriggerConfig,
    ScheduledJob,
    JobRunResult,
    JobListFilter,
    JobStats,
)

from app.scheduler.parser import (
    ScheduleParser,
    ScheduleParseError,
)

from app.scheduler.service import (
    SchedulerService,
    get_scheduler_service,
    set_scheduler_service,
)

from app.scheduler.executor import (
    SchedulerExecutor,
    get_scheduler_executor,
    set_scheduler_executor,
)

from app.scheduler.control_state import (
    ControlState,
    ControlStateManager,
    get_control_state_manager,
    set_control_state_manager,
)

from app.scheduler.persistence import (
    SchedulerPersistence,
    get_scheduler_persistence,
    set_scheduler_persistence,
)


# Export all
__all__ = [
    # Jobs
    "TriggerType",
    "JobStatus",
    "JobActionType",
    "JobAction",
    "TriggerConfig",
    "ScheduledJob",
    "JobRunResult",
    "JobListFilter",
    "JobStats",
    # Parser
    "ScheduleParser",
    "ScheduleParseError",
    # Service
    "SchedulerService",
    "get_scheduler_service",
    "set_scheduler_service",
    # Executor
    "SchedulerExecutor",
    "get_scheduler_executor",
    "set_scheduler_executor",
    # Control State
    "ControlState",
    "ControlStateManager",
    "get_control_state_manager",
    "set_control_state_manager",
    # Persistence
    "SchedulerPersistence",
    "get_scheduler_persistence",
    "set_scheduler_persistence",
]
