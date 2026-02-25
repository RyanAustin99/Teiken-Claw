"""
Job representations for the Teiken Claw scheduler.

This module provides Pydantic models for:
- ScheduledJob: Job configuration and metadata
- JobRunResult: Execution result tracking
- JobAction: Action to perform when job runs

Key Features:
    - Type-safe job definitions
    - Support for date, interval, and cron triggers
    - Action configuration for prompts, skills, and agent tasks
    - Execution result tracking with error handling
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


class TriggerType(str, Enum):
    """Type of job trigger."""
    DATE = "date"        # One-time job at specific datetime
    INTERVAL = "interval"  # Recurring job at fixed intervals
    CRON = "cron"        # Cron-style scheduling


class JobStatus(str, Enum):
    """Status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobActionType(str, Enum):
    """Type of action to perform when job runs."""
    PROMPT = "prompt"    # Send a prompt to the agent
    SKILL = "skill"      # Execute a skill
    AGENT_TASK = "agent_task"  # Run an agent task
    TOOL_CALL = "tool_call"  # Execute a tool call


class JobAction(BaseModel):
    """
    Action to perform when a scheduled job runs.
    
    Attributes:
        type: Type of action (prompt, skill, agent_task, tool_call)
        content: Main content (prompt text, skill name, etc.)
        parameters: Optional parameters for the action
        chat_id: Target chat ID for responses
        metadata: Additional metadata
    """
    type: JobActionType = Field(..., description="Type of action to perform")
    content: str = Field(..., description="Main content for the action")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Optional parameters")
    chat_id: Optional[str] = Field(default=None, description="Target chat ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    
    model_config = {
        "use_enum_values": True,
        "json_schema_extra": {
            "examples": [
                {
                    "type": "prompt",
                    "content": "Generate a daily summary of system metrics",
                    "chat_id": "123456789",
                    "parameters": {"mode": "architect"}
                }
            ]
        }
    }


class TriggerConfig(BaseModel):
    """
    Configuration for job triggers.
    
    For DATE trigger:
        - run_at: ISO datetime string or datetime object
    
    For INTERVAL trigger:
        - seconds: Interval in seconds
        - minutes: Interval in minutes
        - hours: Interval in hours
        - days: Interval in days
        - weeks: Interval in weeks
        - start_date: Optional start datetime
        - end_date: Optional end datetime
    
    For CRON trigger:
        - cron_expression: Standard cron expression
        - Or individual fields: year, month, day, week, day_of_week, hour, minute, second
        - timezone: Optional timezone string
    """
    # Date trigger fields
    run_at: Optional[datetime] = Field(default=None, description="Run datetime for date trigger")
    
    # Interval trigger fields
    seconds: Optional[int] = Field(default=None, ge=1, description="Interval seconds")
    minutes: Optional[int] = Field(default=None, ge=1, description="Interval minutes")
    hours: Optional[int] = Field(default=None, ge=1, description="Interval hours")
    days: Optional[int] = Field(default=None, ge=1, description="Interval days")
    weeks: Optional[int] = Field(default=None, ge=1, description="Interval weeks")
    
    # Cron trigger fields
    cron_expression: Optional[str] = Field(default=None, description="Cron expression")
    year: Optional[str] = Field(default=None, description="Cron year field")
    month: Optional[str] = Field(default=None, description="Cron month field")
    day: Optional[str] = Field(default=None, description="Cron day field")
    week: Optional[str] = Field(default=None, description="Cron week field")
    day_of_week: Optional[str] = Field(default=None, description="Cron day of week field")
    hour: Optional[str] = Field(default=None, description="Cron hour field")
    minute: Optional[str] = Field(default=None, description="Cron minute field")
    second: Optional[str] = Field(default=None, description="Cron second field")
    timezone: Optional[str] = Field(default=None, description="Timezone for cron")
    
    # Common fields
    start_date: Optional[datetime] = Field(default=None, description="Start datetime")
    end_date: Optional[datetime] = Field(default=None, description="End datetime")
    jitter: Optional[int] = Field(default=None, description="Random jitter in seconds")
    
    model_config = {
        "extra": "ignore"
    }


class ScheduledJob(BaseModel):
    """
    Scheduled job configuration.
    
    Represents a job that can be scheduled to run at specific times
    using date, interval, or cron triggers.
    
    Attributes:
        job_id: Unique identifier for the job
        name: Human-readable name
        description: Optional description
        trigger_type: Type of trigger (date, interval, cron)
        trigger_config: Trigger configuration
        action: Action to perform when job runs
        enabled: Whether the job is enabled
        created_at: When the job was created
        updated_at: When the job was last updated
        next_run_time: When the job will run next
        last_run_time: When the job last ran
        run_count: Number of times the job has run
        max_instances: Maximum concurrent instances
        misfire_grace_time: Grace period for misfired jobs
        coalesce: Whether to coalesce missed runs
        metadata: Additional metadata
    """
    job_id: str = Field(..., description="Unique job identifier")
    name: str = Field(..., description="Human-readable job name")
    description: Optional[str] = Field(default=None, description="Job description")
    trigger_type: TriggerType = Field(..., description="Type of trigger")
    trigger_config: TriggerConfig = Field(..., description="Trigger configuration")
    action: JobAction = Field(..., description="Action to perform")
    enabled: bool = Field(default=True, description="Whether job is enabled")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    next_run_time: Optional[datetime] = Field(default=None, description="Next scheduled run")
    last_run_time: Optional[datetime] = Field(default=None, description="Last run timestamp")
    run_count: int = Field(default=0, ge=0, description="Number of runs")
    max_instances: int = Field(default=1, ge=1, description="Max concurrent instances")
    misfire_grace_time: int = Field(default=300, ge=0, description="Misfire grace time in seconds")
    coalesce: bool = Field(default=True, description="Coalesce missed runs")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    
    model_config = {
        "use_enum_values": True,
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "daily_summary",
                    "name": "Daily Summary Report",
                    "trigger_type": "cron",
                    "trigger_config": {
                        "cron_expression": "0 9 * * *",
                        "timezone": "America/Chicago"
                    },
                    "action": {
                        "type": "prompt",
                        "content": "Generate a daily summary of system metrics",
                        "chat_id": "123456789"
                    },
                    "enabled": True
                }
            ]
        }
    }
    
    @field_validator('trigger_type', mode='before')
    @classmethod
    def validate_trigger_type(cls, v):
        """Validate and normalize trigger type."""
        if isinstance(v, str):
            return TriggerType(v.lower())
        return v


class JobRunResult(BaseModel):
    """
    Result of a scheduled job execution.
    
    Tracks the outcome of each job run including timing,
    status, and any errors.
    
    Attributes:
        job_id: ID of the job that ran
        run_id: Unique identifier for this run
        status: Execution status (success, failure, skipped)
        started_at: When the run started
        completed_at: When the run completed
        duration_ms: Duration in milliseconds
        error_message: Error message if failed
        error_type: Error type if failed
        result: Result output if successful
        metadata: Additional metadata
    """
    job_id: str = Field(..., description="Job identifier")
    run_id: str = Field(
        default_factory=lambda: f"run_{uuid4().hex[:12]}",
        description="Unique run identifier"
    )
    status: JobStatus = Field(..., description="Run status")
    started_at: datetime = Field(..., description="Start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Error message")
    error_type: Optional[str] = Field(default=None, description="Error type")
    result: Optional[str] = Field(default=None, description="Result output")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    
    model_config = {
        "use_enum_values": True
    }
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Validate and normalize status."""
        if isinstance(v, str):
            return JobStatus(v.lower())
        return v
    
    def mark_success(self, result: Optional[str] = None) -> None:
        """Mark the run as successful."""
        self.status = JobStatus.SUCCESS
        self.completed_at = datetime.utcnow()
        self.result = result
        if self.started_at:
            self.duration_ms = int(
                (self.completed_at - self.started_at).total_seconds() * 1000
            )
    
    def mark_failure(self, error_message: str, error_type: Optional[str] = None) -> None:
        """Mark the run as failed."""
        self.status = JobStatus.FAILURE
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.error_type = error_type or "ExecutionError"
        if self.started_at:
            self.duration_ms = int(
                (self.completed_at - self.started_at).total_seconds() * 1000
            )
    
    def mark_skipped(self, reason: str) -> None:
        """Mark the run as skipped."""
        self.status = JobStatus.SKIPPED
        self.completed_at = datetime.utcnow()
        self.error_message = reason
        self.error_type = "Skipped"


class JobListFilter(BaseModel):
    """
    Filter options for listing jobs.
    
    Attributes:
        enabled_only: Only return enabled jobs
        trigger_type: Filter by trigger type
        status: Filter by status
        search: Search in name and description
        limit: Maximum number of results
        offset: Offset for pagination
    """
    enabled_only: bool = Field(default=False, description="Only enabled jobs")
    trigger_type: Optional[TriggerType] = Field(default=None, description="Filter by trigger type")
    status: Optional[JobStatus] = Field(default=None, description="Filter by status")
    search: Optional[str] = Field(default=None, description="Search string")
    limit: int = Field(default=50, ge=1, le=500, description="Max results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class JobStats(BaseModel):
    """
    Statistics for scheduled jobs.
    
    Attributes:
        total_jobs: Total number of jobs
        enabled_jobs: Number of enabled jobs
        disabled_jobs: Number of disabled jobs
        total_runs: Total number of runs
        successful_runs: Number of successful runs
        failed_runs: Number of failed runs
        last_run_time: Time of last run
        next_run_time: Time of next scheduled run
    """
    total_jobs: int = Field(default=0, description="Total job count")
    enabled_jobs: int = Field(default=0, description="Enabled job count")
    disabled_jobs: int = Field(default=0, description="Disabled job count")
    total_runs: int = Field(default=0, description="Total run count")
    successful_runs: int = Field(default=0, description="Successful run count")
    failed_runs: int = Field(default=0, description="Failed run count")
    last_run_time: Optional[datetime] = Field(default=None, description="Last run time")
    next_run_time: Optional[datetime] = Field(default=None, description="Next run time")


# Export
__all__ = [
    "TriggerType",
    "JobStatus",
    "JobActionType",
    "JobAction",
    "TriggerConfig",
    "ScheduledJob",
    "JobRunResult",
    "JobListFilter",
    "JobStats",
]
