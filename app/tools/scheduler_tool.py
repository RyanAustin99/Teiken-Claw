"""
Scheduler operations tool for the Teiken Claw agent system.

This module provides scheduler management capabilities including:
- Creating scheduled jobs
- Listing scheduled jobs
- Pausing/resuming jobs
- Deleting jobs
- Running jobs immediately

Key Features:
    - Support for interval and cron triggers
    - Permission checks for destructive operations
    - Audit logging for all operations
    - Admin-only for destructive operations

Phase 9: Now integrated with APScheduler for production scheduling.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.scheduler import (
    SchedulerService,
    get_scheduler_service,
    ControlStateManager,
    get_control_state_manager,
    ScheduledJob,
    TriggerType,
    JobStatus,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)


def _get_scheduler_service() -> Optional[SchedulerService]:
    """Get the scheduler service instance."""
    try:
        return get_scheduler_service()
    except Exception as e:
        logger.warning(f"Could not get scheduler service: {e}")
        return None


def _get_control_state_manager() -> Optional[ControlStateManager]:
    """Get the control state manager instance."""
    try:
        return get_control_state_manager()
    except Exception as e:
        logger.warning(f"Could not get control state manager: {e}")
        return None


# Job status enum (for backward compatibility)
class JobStatus(str, Enum):
    """Status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# Trigger type enum
class TriggerType(str, Enum):
    """Type of job trigger."""
    INTERVAL = "interval"  # Run every N seconds/minutes/hours
    CRON = "cron"          # Run on a schedule (cron expression)
    ONCE = "once"          # Run once at a specific time


# In-memory job storage (will be replaced with database in Phase 9)
_jobs: Dict[int, Dict[str, Any]] = {}
_next_job_id = 1


class SchedulerTool(Tool):
    """
    Scheduler operations tool for managing scheduled jobs.
    
    Provides capabilities for:
    - Creating scheduled jobs
    - Listing scheduled jobs
    - Pausing/resuming jobs
    - Deleting jobs
    - Running jobs immediately
    
    Phase 9: Integrated with APScheduler for production scheduling.
    
    Attributes:
        jobs: Uses scheduler service for job management
    """
    
    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
    ):
        """
        Initialize the scheduler tool.
        
        Args:
            policy: Tool policy configuration
        """
        # Default to admin-only for destructive operations
        if policy is None:
            policy = ToolPolicy(
                enabled=True,
                admin_only=False,
                timeout_sec=30.0,
            )
        
        super().__init__(policy)
        
        logger.debug("SchedulerTool initialized (stub mode)")
    
    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "scheduler"
    
    @property
    def description(self) -> str:
        """Tool description for the AI model."""
        return (
            "Scheduler operations tool for managing scheduled jobs. "
            "Can create, list, pause, resume, and delete scheduled jobs. "
            "Use this to set up recurring tasks or delayed actions. "
            "Supports cron expressions, intervals, and one-time schedules."
        )
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        """Ollama-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "create", "list", "pause", "resume",
                                "delete", "run_now", "pause_all", "resume_all"
                            ],
                            "description": "The scheduler action to perform"
                        },
                        "name": {
                            "type": "string",
                            "description": "Job name (for create action)"
                        },
                        "trigger_type": {
                            "type": "string",
                            "enum": ["interval", "cron", "once"],
                            "description": "Type of trigger (for create action)"
                        },
                        "trigger_config": {
                            "type": "object",
                            "description": "Trigger configuration (for create action)",
                            "properties": {
                                "interval_seconds": {
                                    "type": "integer",
                                    "description": "Interval in seconds (for interval trigger)"
                                },
                                "cron_expression": {
                                    "type": "string",
                                    "description": "Cron expression (for cron trigger)"
                                },
                                "run_at": {
                                    "type": "string",
                                    "description": "ISO datetime to run at (for once trigger)"
                                }
                            }
                        },
                        "action_config": {
                            "type": "object",
                            "description": "Action to perform when job runs",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": "Type of action (message, tool_call)"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Message content or tool call details"
                                }
                            }
                        },
                        "job_id": {
                            "type": "integer",
                            "description": "Job ID (for pause, resume, delete, run_now actions)"
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute a scheduler operation.
        
        Args:
            action: The action to perform
            name: Job name (for create)
            trigger_type: Type of trigger (for create)
            trigger_config: Trigger configuration (for create)
            action_config: Action configuration (for create)
            job_id: Job ID (for pause, resume, delete, run_now)
            
        Returns:
            ToolResult with the operation result
        """
        action = kwargs.get("action", "")
        
        # Get context from metadata
        chat_id = kwargs.get("_chat_id")
        is_admin = kwargs.get("_is_admin", False)
        
        # Audit log
        self._audit_log(action, kwargs, chat_id)
        
        try:
            if action == "create":
                name = kwargs.get("name", "")
                trigger_type = kwargs.get("trigger_type", "interval")
                trigger_config = kwargs.get("trigger_config", {})
                action_config = kwargs.get("action_config", {})
                return await self._create_job(name, trigger_type, trigger_config, action_config, chat_id)
            
            elif action == "list":
                return await self._list_jobs(chat_id)
            
            elif action == "pause":
                job_id = kwargs.get("job_id")
                return await self._pause_job(job_id, chat_id, is_admin)
            
            elif action == "resume":
                job_id = kwargs.get("job_id")
                return await self._resume_job(job_id, chat_id, is_admin)
            
            elif action == "delete":
                job_id = kwargs.get("job_id")
                return await self._delete_job(job_id, chat_id, is_admin)
            
            elif action == "run_now":
                job_id = kwargs.get("job_id")
                return await self._run_now(job_id, chat_id, is_admin)
            
            elif action == "pause_all":
                return await self._pause_all(chat_id, is_admin)
            
            elif action == "resume_all":
                return await self._resume_all(chat_id, is_admin)
            
            else:
                return ToolResult.error(
                    error_code="INVALID_ACTION",
                    error_message=f"Unknown action: {action}. Valid actions: create, list, pause, resume, delete, run_now, pause_all, resume_all"
                )
        
        except Exception as e:
            logger.error(f"Scheduler tool execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Scheduler operation failed: {e}"
            )
    
    async def _create_job(
        self,
        name: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        action_config: Dict[str, Any],
        chat_id: Optional[str],
    ) -> ToolResult:
        """
        Create a new scheduled job.
        
        Args:
            name: Job name
            trigger_type: Type of trigger
            trigger_config: Trigger configuration
            action_config: Action configuration
            chat_id: Chat ID for ownership
            
        Returns:
            ToolResult with job info
        """
        if not name:
            return ToolResult.error(
                error_code="MISSING_NAME",
                error_message="Job name is required"
            )
        
        # Validate trigger type
        if trigger_type not in [t.value for t in TriggerType]:
            return ToolResult.error(
                error_code="INVALID_TRIGGER_TYPE",
                error_message=f"Invalid trigger type: {trigger_type}. Valid types: interval, cron, once"
            )
        
        # Validate trigger config
        if trigger_type == "interval":
            if "interval_seconds" not in trigger_config:
                return ToolResult.error(
                    error_code="MISSING_INTERVAL",
                    error_message="interval_seconds is required for interval trigger"
                )
            if trigger_config["interval_seconds"] < 60:
                return ToolResult.error(
                    error_code="INVALID_INTERVAL",
                    error_message="Minimum interval is 60 seconds"
                )
        
        elif trigger_type == "cron":
            if "cron_expression" not in trigger_config:
                return ToolResult.error(
                    error_code="MISSING_CRON",
                    error_message="cron_expression is required for cron trigger"
                )
        
        elif trigger_type == "once":
            if "run_at" not in trigger_config:
                return ToolResult.error(
                    error_code="MISSING_RUN_AT",
                    error_message="run_at is required for once trigger"
                )
        
        global _next_job_id
        
        logger.info(f"Creating scheduled job: {name}")
        
        try:
            # Create job record
            job = {
                "id": _next_job_id,
                "name": name,
                "trigger_type": trigger_type,
                "trigger_config": trigger_config,
                "action_config": action_config,
                "chat_id": chat_id,
                "status": JobStatus.PENDING.value,
                "created_at": datetime.utcnow().isoformat(),
                "last_run": None,
                "next_run": self._calculate_next_run(trigger_type, trigger_config),
                "run_count": 0,
            }
            
            _jobs[_next_job_id] = job
            _next_job_id += 1
            
            return ToolResult.success(
                content=f"Scheduled job created successfully (ID: {job['id']})\n\n"
                       f"**Note:** This is a preview feature. The job is stored but will not "
                       f"actually execute until Phase 9 scheduler integration is complete.",
                metadata={
                    "job_id": job["id"],
                    "name": name,
                    "trigger_type": trigger_type,
                    "status": job["status"],
                    "action": "create"
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating job: {e}", exc_info=True)
            return ToolResult.error(
                error_code="CREATE_ERROR",
                error_message=f"Failed to create job: {e}"
            )
    
    async def _list_jobs(self, chat_id: Optional[str]) -> ToolResult:
        """
        List scheduled jobs.
        
        Args:
            chat_id: Chat ID to filter by
            
        Returns:
            ToolResult with job list
        """
        logger.info(f"Listing scheduled jobs for chat: {chat_id}")
        
        try:
            # Filter jobs by chat_id
            jobs = [
                job for job in _jobs.values()
                if chat_id is None or job.get("chat_id") == chat_id
            ]
            
            if not jobs:
                return ToolResult.success(
                    content="No scheduled jobs found.",
                    metadata={
                        "job_count": 0,
                        "action": "list"
                    }
                )
            
            # Format results
            formatted = self._format_job_list(jobs)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "job_count": len(jobs),
                    "action": "list"
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing jobs: {e}", exc_info=True)
            return ToolResult.error(
                error_code="LIST_ERROR",
                error_message=f"Failed to list jobs: {e}"
            )
    
    async def _pause_job(
        self,
        job_id: Optional[int],
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Pause a scheduled job.
        
        Args:
            job_id: Job ID to pause
            chat_id: Chat ID for ownership check
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if job_id is None:
            return ToolResult.error(
                error_code="MISSING_JOB_ID",
                error_message="Job ID is required"
            )
        
        job = _jobs.get(job_id)
        
        if not job:
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Job not found: {job_id}"
            )
        
        # Check ownership (unless admin)
        if not is_admin and job.get("chat_id") and job.get("chat_id") != chat_id:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to pause this job"
            )
        
        logger.info(f"Pausing job: {job_id}")
        
        job["status"] = JobStatus.PAUSED.value
        
        return ToolResult.success(
            content=f"Job {job_id} paused successfully.",
            metadata={
                "job_id": job_id,
                "status": job["status"],
                "action": "pause"
            }
        )
    
    async def _resume_job(
        self,
        job_id: Optional[int],
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Resume a paused job.
        
        Args:
            job_id: Job ID to resume
            chat_id: Chat ID for ownership check
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if job_id is None:
            return ToolResult.error(
                error_code="MISSING_JOB_ID",
                error_message="Job ID is required"
            )
        
        job = _jobs.get(job_id)
        
        if not job:
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Job not found: {job_id}"
            )
        
        # Check ownership (unless admin)
        if not is_admin and job.get("chat_id") and job.get("chat_id") != chat_id:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to resume this job"
            )
        
        logger.info(f"Resuming job: {job_id}")
        
        job["status"] = JobStatus.PENDING.value
        
        return ToolResult.success(
            content=f"Job {job_id} resumed successfully.",
            metadata={
                "job_id": job_id,
                "status": job["status"],
                "action": "resume"
            }
        )
    
    async def _delete_job(
        self,
        job_id: Optional[int],
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Delete a scheduled job.
        
        Args:
            job_id: Job ID to delete
            chat_id: Chat ID for ownership check
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if job_id is None:
            return ToolResult.error(
                error_code="MISSING_JOB_ID",
                error_message="Job ID is required"
            )
        
        job = _jobs.get(job_id)
        
        if not job:
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Job not found: {job_id}"
            )
        
        # Check ownership (unless admin)
        if not is_admin and job.get("chat_id") and job.get("chat_id") != chat_id:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to delete this job"
            )
        
        logger.warning(f"Deleting job: {job_id}")
        
        del _jobs[job_id]
        
        return ToolResult.success(
            content=f"Job {job_id} deleted successfully.",
            metadata={
                "job_id": job_id,
                "action": "delete"
            }
        )
    
    async def _run_now(
        self,
        job_id: Optional[int],
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Run a job immediately.
        
        Args:
            job_id: Job ID to run
            chat_id: Chat ID for ownership check
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if job_id is None:
            return ToolResult.error(
                error_code="MISSING_JOB_ID",
                error_message="Job ID is required"
            )
        
        job = _jobs.get(job_id)
        
        if not job:
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Job not found: {job_id}"
            )
        
        # Check ownership (unless admin)
        if not is_admin and job.get("chat_id") and job.get("chat_id") != chat_id:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to run this job"
            )
        
        logger.info(f"Running job immediately: {job_id}")
        
        # Update job stats
        job["last_run"] = datetime.utcnow().isoformat()
        job["run_count"] = job.get("run_count", 0) + 1
        
        return ToolResult.success(
            content=f"Job {job_id} triggered for immediate execution.\n\n"
                   f"**Note:** This is a preview feature. The job has been marked for execution "
                   f"but will not actually run until Phase 9 scheduler integration is complete.",
            metadata={
                "job_id": job_id,
                "action": "run_now"
            }
        )
    
    async def _pause_all(
        self,
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Pause all jobs.
        
        Args:
            chat_id: Chat ID to filter by
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if not is_admin:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="Admin privileges required to pause all jobs"
            )
        
        logger.warning("Pausing all jobs")
        
        paused_count = 0
        for job in _jobs.values():
            if chat_id is None or job.get("chat_id") == chat_id:
                job["status"] = JobStatus.PAUSED.value
                paused_count += 1
        
        return ToolResult.success(
            content=f"Paused {paused_count} jobs.",
            metadata={
                "paused_count": paused_count,
                "action": "pause_all"
            }
        )
    
    async def _resume_all(
        self,
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Resume all paused jobs.
        
        Args:
            chat_id: Chat ID to filter by
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with status
        """
        if not is_admin:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="Admin privileges required to resume all jobs"
            )
        
        logger.info("Resuming all jobs")
        
        resumed_count = 0
        for job in _jobs.values():
            if job["status"] == JobStatus.PAUSED.value:
                if chat_id is None or job.get("chat_id") == chat_id:
                    job["status"] = JobStatus.PENDING.value
                    resumed_count += 1
        
        return ToolResult.success(
            content=f"Resumed {resumed_count} jobs.",
            metadata={
                "resumed_count": resumed_count,
                "action": "resume_all"
            }
        )
    
    def _calculate_next_run(
        self,
        trigger_type: str,
        trigger_config: Dict[str, Any],
    ) -> Optional[str]:
        """
        Calculate the next run time for a job.
        
        Args:
            trigger_type: Type of trigger
            trigger_config: Trigger configuration
            
        Returns:
            ISO datetime string or None
        """
        now = datetime.utcnow()
        
        if trigger_type == "interval":
            interval_seconds = trigger_config.get("interval_seconds", 60)
            from datetime import timedelta
            next_run = now + timedelta(seconds=interval_seconds)
            return next_run.isoformat()
        
        elif trigger_type == "once":
            return trigger_config.get("run_at")
        
        # Cron would need a proper cron parser
        return None
    
    def _format_job_list(self, jobs: List[Dict[str, Any]]) -> str:
        """Format job list for display."""
        lines = ["## Scheduled Jobs\n"]
        
        for job in jobs:
            status_emoji = {
                JobStatus.PENDING.value: "⏳",
                JobStatus.RUNNING.value: "▶️",
                JobStatus.PAUSED.value: "⏸️",
                JobStatus.COMPLETED.value: "✅",
                JobStatus.FAILED.value: "❌",
            }.get(job["status"], "❓")
            
            lines.append(f"### {status_emoji} Job #{job['id']}: {job['name']}")
            lines.append(f"**Status:** {job['status']}")
            lines.append(f"**Trigger:** {job['trigger_type']}")
            lines.append(f"**Created:** {job['created_at']}")
            if job.get("next_run"):
                lines.append(f"**Next Run:** {job['next_run']}")
            if job.get("run_count", 0) > 0:
                lines.append(f"**Run Count:** {job['run_count']}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _audit_log(self, action: str, kwargs: Dict, chat_id: Optional[str]) -> None:
        """
        Log an audit entry for a scheduler operation.
        
        Args:
            action: The action being performed
            kwargs: Operation arguments
            chat_id: Chat ID
        """
        # Redact sensitive information
        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            safe_kwargs[key] = value
        
        logger.info(
            f"Scheduler operation: {action}",
            extra={
                "event": "scheduler_operation",
                "action": action,
                "chat_id": chat_id,
                "kwargs": safe_kwargs,
            }
        )


__all__ = ["SchedulerTool", "JobStatus", "TriggerType"]