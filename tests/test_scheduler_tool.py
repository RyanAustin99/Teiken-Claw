"""
Tests for Scheduler Tool.

This module tests the SchedulerTool class for:
- Job creation
- Job listing
- Job pause/resume
- Job deletion
- Job execution
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from app.tools.scheduler_tool import (
    SchedulerTool,
    JobStatus,
    TriggerType,
)
from app.tools.base import ToolPolicy


class TestSchedulerTool:
    """Tests for SchedulerTool class."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    def test_init_default(self):
        """Test initialization with default settings."""
        tool = SchedulerTool()
        assert tool.name == "scheduler"
    
    def test_name_property(self):
        """Test name property."""
        tool = SchedulerTool()
        assert tool.name == "scheduler"
    
    def test_description_property(self):
        """Test description property."""
        tool = SchedulerTool()
        assert "scheduler" in tool.description.lower()
        assert "job" in tool.description.lower()
    
    def test_json_schema(self):
        """Test JSON schema structure."""
        tool = SchedulerTool()
        schema = tool.json_schema
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "scheduler"
        assert "action" in schema["function"]["parameters"]["properties"]
        assert "name" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_execute_missing_action(self):
        """Test execute with missing action."""
        tool = SchedulerTool()
        result = await tool.execute()
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_execute_invalid_action(self):
        """Test execute with invalid action."""
        tool = SchedulerTool()
        result = await tool.execute(action="invalid")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code


class TestSchedulerToolCreate:
    """Tests for job creation."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_create_missing_name(self):
        """Test create with missing name."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            trigger_type="interval",
            trigger_config={"interval_seconds": 60}
        )
        assert not result.ok
        assert "MISSING_NAME" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_invalid_trigger_type(self):
        """Test create with invalid trigger type."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="invalid"
        )
        assert not result.ok
        assert "INVALID_TRIGGER_TYPE" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_interval_missing_seconds(self):
        """Test create interval without seconds."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={}
        )
        assert not result.ok
        assert "MISSING_INTERVAL" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_interval_too_short(self):
        """Test create interval too short."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 30}
        )
        assert not result.ok
        assert "INVALID_INTERVAL" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_cron_missing_expression(self):
        """Test create cron without expression."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="cron",
            trigger_config={}
        )
        assert not result.ok
        assert "MISSING_CRON" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_once_missing_run_at(self):
        """Test create once without run_at."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="once",
            trigger_config={}
        )
        assert not result.ok
        assert "MISSING_RUN_AT" in result.error_code
    
    @pytest.mark.asyncio
    async def test_create_success_interval(self):
        """Test successful interval job creation."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300},
            action_config={"type": "message", "content": "Test"}
        )
        
        assert result.ok
        assert "created successfully" in result.content.lower()
        assert result.metadata["job_id"] == 1
    
    @pytest.mark.asyncio
    async def test_create_success_cron(self):
        """Test successful cron job creation."""
        tool = SchedulerTool()
        result = await tool.execute(
            action="create",
            name="cron_job",
            trigger_type="cron",
            trigger_config={"cron_expression": "0 9 * * *"},
            action_config={"type": "message", "content": "Daily reminder"}
        )
        
        assert result.ok
        assert result.metadata["job_id"] == 1


class TestSchedulerToolList:
    """Tests for job listing."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Test listing with no jobs."""
        tool = SchedulerTool()
        result = await tool.execute(action="list")
        
        assert result.ok
        assert "No scheduled jobs" in result.content
    
    @pytest.mark.asyncio
    async def test_list_with_jobs(self):
        """Test listing with jobs."""
        tool = SchedulerTool()
        
        # Create a job first
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300}
        )
        
        result = await tool.execute(action="list")
        
        assert result.ok
        assert "test_job" in result.content
        assert result.metadata["job_count"] == 1


class TestSchedulerToolPause:
    """Tests for job pause."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_pause_missing_id(self):
        """Test pause with missing job ID."""
        tool = SchedulerTool()
        result = await tool.execute(action="pause")
        assert not result.ok
        assert "MISSING_JOB_ID" in result.error_code
    
    @pytest.mark.asyncio
    async def test_pause_not_found(self):
        """Test pause non-existent job."""
        tool = SchedulerTool()
        result = await tool.execute(action="pause", job_id=999)
        assert not result.ok
        assert "NOT_FOUND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_pause_permission_denied(self):
        """Test pause with permission denied."""
        tool = SchedulerTool()
        
        # Create a job with different chat_id
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300},
            _chat_id="other_chat"
        )
        
        result = await tool.execute(
            action="pause",
            job_id=1,
            _chat_id="current_chat",
            _is_admin=False
        )
        
        assert not result.ok
        assert "PERMISSION_DENIED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_pause_success(self):
        """Test successful job pause."""
        tool = SchedulerTool()
        
        # Create a job
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300}
        )
        
        result = await tool.execute(action="pause", job_id=1)
        
        assert result.ok
        assert "paused" in result.content.lower()


class TestSchedulerToolResume:
    """Tests for job resume."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_resume_missing_id(self):
        """Test resume with missing job ID."""
        tool = SchedulerTool()
        result = await tool.execute(action="resume")
        assert not result.ok
        assert "MISSING_JOB_ID" in result.error_code
    
    @pytest.mark.asyncio
    async def test_resume_success(self):
        """Test successful job resume."""
        tool = SchedulerTool()
        
        # Create and pause a job
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300}
        )
        await tool.execute(action="pause", job_id=1)
        
        result = await tool.execute(action="resume", job_id=1)
        
        assert result.ok
        assert "resumed" in result.content.lower()


class TestSchedulerToolDelete:
    """Tests for job deletion."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_delete_missing_id(self):
        """Test delete with missing job ID."""
        tool = SchedulerTool()
        result = await tool.execute(action="delete")
        assert not result.ok
        assert "MISSING_JOB_ID" in result.error_code
    
    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Test delete non-existent job."""
        tool = SchedulerTool()
        result = await tool.execute(action="delete", job_id=999)
        assert not result.ok
        assert "NOT_FOUND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test successful job deletion."""
        tool = SchedulerTool()
        
        # Create a job
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300}
        )
        
        result = await tool.execute(action="delete", job_id=1)
        
        assert result.ok
        assert "deleted" in result.content.lower()
        
        # Verify job is gone
        list_result = await tool.execute(action="list")
        assert list_result.metadata["job_count"] == 0


class TestSchedulerToolRunNow:
    """Tests for immediate job execution."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_run_now_missing_id(self):
        """Test run_now with missing job ID."""
        tool = SchedulerTool()
        result = await tool.execute(action="run_now")
        assert not result.ok
        assert "MISSING_JOB_ID" in result.error_code
    
    @pytest.mark.asyncio
    async def test_run_now_success(self):
        """Test successful immediate execution."""
        tool = SchedulerTool()
        
        # Create a job
        await tool.execute(
            action="create",
            name="test_job",
            trigger_type="interval",
            trigger_config={"interval_seconds": 300}
        )
        
        result = await tool.execute(action="run_now", job_id=1)
        
        assert result.ok
        assert "triggered" in result.content.lower()


class TestSchedulerToolPauseAll:
    """Tests for pause all jobs."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_pause_all_not_admin(self):
        """Test pause_all requires admin."""
        tool = SchedulerTool()
        result = await tool.execute(action="pause_all", _is_admin=False)
        assert not result.ok
        assert "PERMISSION_DENIED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_pause_all_success(self):
        """Test successful pause all."""
        tool = SchedulerTool()
        
        # Create multiple jobs
        for i in range(3):
            await tool.execute(
                action="create",
                name=f"job_{i}",
                trigger_type="interval",
                trigger_config={"interval_seconds": 300}
            )
        
        result = await tool.execute(action="pause_all", _is_admin=True)
        
        assert result.ok
        assert result.metadata["paused_count"] == 3


class TestSchedulerToolResumeAll:
    """Tests for resume all jobs."""
    
    @pytest.fixture(autouse=True)
    def reset_jobs(self):
        """Reset jobs before each test."""
        import app.tools.scheduler_tool as scheduler_module
        scheduler_module._jobs.clear()
        scheduler_module._next_job_id = 1
    
    @pytest.mark.asyncio
    async def test_resume_all_not_admin(self):
        """Test resume_all requires admin."""
        tool = SchedulerTool()
        result = await tool.execute(action="resume_all", _is_admin=False)
        assert not result.ok
        assert "PERMISSION_DENIED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_resume_all_success(self):
        """Test successful resume all."""
        tool = SchedulerTool()
        
        # Create and pause jobs
        for i in range(3):
            await tool.execute(
                action="create",
                name=f"job_{i}",
                trigger_type="interval",
                trigger_config={"interval_seconds": 300}
            )
        await tool.execute(action="pause_all", _is_admin=True)
        
        result = await tool.execute(action="resume_all", _is_admin=True)
        
        assert result.ok
        assert result.metadata["resumed_count"] == 3


class TestJobStatus:
    """Tests for JobStatus enum."""
    
    def test_status_values(self):
        """Test job status values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.PAUSED.value == "paused"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestTriggerType:
    """Tests for TriggerType enum."""
    
    def test_trigger_values(self):
        """Test trigger type values."""
        assert TriggerType.INTERVAL.value == "interval"
        assert TriggerType.CRON.value == "cron"
        assert TriggerType.ONCE.value == "once"


class TestSchedulerToolPolicy:
    """Tests for SchedulerTool policy enforcement."""
    
    def test_policy_applied(self):
        """Test that policy is properly applied."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=45.0,
        )
        tool = SchedulerTool(policy=policy)
        
        assert tool.policy.enabled
        assert tool.policy.timeout_sec == 45.0
    
    def test_to_ollama_tool(self):
        """Test conversion to Ollama tool format."""
        tool = SchedulerTool()
        ollama_tool = tool.to_ollama_tool()
        
        assert ollama_tool == tool.json_schema
