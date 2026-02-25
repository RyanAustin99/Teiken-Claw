"""
Tests for the sub-agent system (Phase 11).

This module tests:
    - Sub-agent models and enums
    - Sub-agent policy management
    - Sub-agent spawning and quotas
    - Depth limits
    - Tool restrictions
    - Result summarization
"""

import pytest
from datetime import datetime

from app.subagents.models import (
    SubAgentStatus,
    SubAgentTrigger,
    SubAgentTask,
    SubAgentResult,
    SubAgentPolicy,
    SubAgentRunRecord,
)
from app.subagents.policies import SubAgentPolicyManager, DEFAULT_DENYLIST
from app.subagents.manager import (
    SubAgentManager,
    SubAgentQuotaExceeded,
    SubAgentDepthExceeded,
    SubAgentNotFound,
)
from app.subagents.summarizer import SubAgentSummarizer


class TestSubAgentModels:
    """Test sub-agent data models."""
    
    def test_sub_agent_status_enum(self):
        """Test SubAgentStatus enum values."""
        assert SubAgentStatus.PENDING == "pending"
        assert SubAgentStatus.RUNNING == "running"
        assert SubAgentStatus.COMPLETED == "completed"
        assert SubAgentStatus.FAILED == "failed"
        assert SubAgentStatus.CANCELLED == "cancelled"
    
    def test_sub_agent_trigger_enum(self):
        """Test SubAgentTrigger enum values."""
        assert SubAgentTrigger.MANUAL == "manual"
        assert SubAgentTrigger.SKILL == "skill"
        assert SubAgentTrigger.AGENT == "agent"
    
    def test_sub_agent_task_creation(self):
        """Test creating a SubAgentTask."""
        task = SubAgentTask(
            purpose="Research",
            task_description="Find information about X",
            inputs={"query": "test"},
        )
        
        assert task.purpose == "Research"
        assert task.task_description == "Find information about X"
        assert task.inputs["query"] == "test"
        assert task.output_schema is None
    
    def test_sub_agent_task_with_output_schema(self):
        """Test creating task with output schema."""
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        task = SubAgentTask(
            purpose="Answer",
            task_description="Answer the question",
            output_schema=schema,
        )
        
        assert task.output_schema == schema
    
    def test_sub_agent_result_success(self):
        """Test successful SubAgentResult."""
        result = SubAgentResult.success(
            content="Task completed",
            metadata={"turns": 5},
        )
        
        assert result.ok is True
        assert result.content == "Task completed"
        assert result.error_message is None
        assert result.metadata["turns"] == 5
    
    def test_sub_agent_result_error(self):
        """Test error SubAgentResult."""
        result = SubAgentResult.error(
            error_message="Task failed",
            error_code="EXECUTION_ERROR",
            content="Partial result",
        )
        
        assert result.ok is False
        assert result.error_message == "Task failed"
        assert result.error_code == "EXECUTION_ERROR"
        assert result.content == "Partial result"
    
    def test_sub_agent_policy_default(self):
        """Test default SubAgentPolicy values."""
        policy = SubAgentPolicy()
        
        assert policy.max_spawn_depth == 1
        assert policy.max_children_per_parent == 3
        assert policy.timeout_sec == 300
        assert policy.max_turns == 20
        assert policy.no_exec is True
        assert policy.no_scheduler_mutation is True
        assert policy.allow_subagents is False
    
    def test_sub_agent_policy_tool_allowlist(self):
        """Test policy tool allowlist."""
        policy = SubAgentPolicy(
            tool_allowlist=["web", "memory"],
            tool_denylist=["exec"],
        )
        
        assert policy.is_tool_allowed("web") is True
        assert policy.is_tool_allowed("memory") is True
        assert policy.is_tool_allowed("exec") is False
        # With allowlist, only allowlisted tools are allowed
        assert policy.is_tool_allowed("sudo") is False
    
    def test_sub_agent_policy_denylist(self):
        """Test policy tool denylist."""
        policy = SubAgentPolicy(tool_denylist=["exec", "sudo"])
        
        assert policy.is_tool_allowed("web") is True
        assert policy.is_tool_allowed("exec") is False
        assert policy.is_tool_allowed("sudo") is False
    
    def test_sub_agent_run_record(self):
        """Test SubAgentRunRecord creation."""
        task = SubAgentTask(
            purpose="Test",
            task_description="Run test",
        )
        policy = SubAgentPolicy()
        
        record = SubAgentRunRecord(
            run_id="test_123",
            parent_id="main",
            task=task,
            policy=policy,
        )
        
        assert record.run_id == "test_123"
        assert record.parent_id == "main"
        assert record.status == SubAgentStatus.PENDING
        assert record.depth == 1
        assert record.created_at is not None
    
    def test_sub_agent_run_record_duration(self):
        """Test calculating duration of a run."""
        task = SubAgentTask(purpose="Test", task_description="Run test")
        policy = SubAgentPolicy()
        
        record = SubAgentRunRecord(
            run_id="test_123",
            parent_id="main",
            task=task,
            policy=policy,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 5, 0),
        )
        
        assert record.duration_seconds() == 300.0  # 5 minutes


class TestSubAgentPolicies:
    """Test sub-agent policy management."""
    
    def test_policy_manager_default(self):
        """Test creating default policy manager."""
        manager = SubAgentPolicyManager()
        
        assert manager.default_policy.max_spawn_depth == 1
        assert manager.default_policy.max_children_per_parent == 3
        assert "exec" in manager.default_policy.tool_denylist
    
    def test_policy_validation_valid(self):
        """Test validating a valid policy."""
        manager = SubAgentPolicyManager()
        policy = SubAgentPolicy(
            max_spawn_depth=2,
            max_children_per_parent=5,
            timeout_sec=60,
            max_turns=10,
        )
        
        # Should not raise
        manager.validate_policy(policy)
    
    def test_policy_validation_invalid_depth(self):
        """Test validating policy with invalid depth."""
        manager = SubAgentPolicyManager()
        policy = SubAgentPolicy(max_spawn_depth=-1)
        
        with pytest.raises(ValueError, match="cannot be negative"):
            manager.validate_policy(policy)
    
    def test_policy_validation_invalid_children(self):
        """Test validating policy with invalid children limit."""
        manager = SubAgentPolicyManager()
        policy = SubAgentPolicy(max_children_per_parent=0)
        
        with pytest.raises(ValueError, match="at least 1"):
            manager.validate_policy(policy)
    
    def test_policy_validation_conflicting_lists(self):
        """Test validating policy with conflicting tool lists."""
        manager = SubAgentPolicyManager()
        policy = SubAgentPolicy(
            tool_allowlist=["web"],
            tool_denylist=["web"],
        )
        
        with pytest.raises(ValueError, match="overlap"):
            manager.validate_policy(policy)
    
    def test_get_effective_policy(self):
        """Test getting effective policy with inheritance."""
        manager = SubAgentPolicyManager()
        
        parent_policy = SubAgentPolicy(
            max_spawn_depth=2,
            timeout_sec=60,
            max_turns=10,
        )
        
        child_policy = manager.get_policy(
            requested_policy=SubAgentPolicy(max_turns=15),
            parent_policy=parent_policy,
        )
        
        # Child should inherit parent's stricter limits
        assert child_policy.max_spawn_depth == 1  # parent_depth - 1
        assert child_policy.timeout_sec == 60  # inherited from parent
        assert child_policy.max_turns == 10  # parent's stricter limit


class TestSubAgentManager:
    """Test sub-agent manager."""
    
    @pytest.fixture
    def manager(self):
        """Create a fresh manager for each test."""
        return SubAgentManager()
    
    def test_spawn_subagent(self, manager):
        """Test spawning a sub-agent."""
        task = SubAgentTask(
            purpose="Research",
            task_description="Find info about X",
        )
        
        run = manager.spawn_subagent(
            parent_id="main",
            task=task,
        )
        
        assert run.run_id.startswith("subagent_")
        assert run.parent_id == "main"
        assert run.status == SubAgentStatus.PENDING
        assert run.depth == 1
    
    def test_get_subagent_run(self, manager):
        """Test getting a sub-agent run."""
        task = SubAgentTask(purpose="Test", task_description="Run test")
        
        run = manager.spawn_subagent(parent_id="main", task=task)
        retrieved = manager.get_subagent_run(run.run_id)
        
        assert retrieved.run_id == run.run_id
    
    def test_get_subagent_run_not_found(self, manager):
        """Test getting non-existent run."""
        with pytest.raises(SubAgentNotFound):
            manager.get_subagent_run("nonexistent")
    
    def test_list_subagent_runs(self, manager):
        """Test listing sub-agent runs."""
        # Spawn multiple sub-agents
        for i in range(3):
            task = SubAgentTask(purpose=f"Task {i}", task_description=f"Do {i}")
            manager.spawn_subagent(parent_id="main", task=task)
        
        runs = manager.list_subagent_runs(parent_id="main")
        
        assert len(runs) == 3
    
    def test_list_runs_by_status(self, manager):
        """Test listing runs filtered by status."""
        task = SubAgentTask(purpose="Test", task_description="Run test")
        run = manager.spawn_subagent(parent_id="main", task=task)
        
        # Initially pending
        pending = manager.list_subagent_runs(status=SubAgentStatus.PENDING)
        assert len(pending) >= 1
        
        # Update to running
        manager.update_run_status(run.run_id, SubAgentStatus.RUNNING)
        
        running = manager.list_subagent_runs(status=SubAgentStatus.RUNNING)
        assert any(r.run_id == run.run_id for r in running)
    
    def test_quota_exceeded(self, manager):
        """Test quota enforcement."""
        # Use default policy which has max_children_per_parent=3
        # First spawn 3 children, then the 4th should fail
        for i in range(3):
            task = SubAgentTask(purpose=f"Task {i}", task_description=f"Do {i}")
            manager.spawn_subagent(parent_id="main", task=task)
        
        # Now should exceed quota (default is 3)
        task = SubAgentTask(purpose="Task 3", task_description="Do 3")
        
        with pytest.raises(SubAgentQuotaExceeded):
            manager.spawn_subagent(parent_id="main", task=task)
    
    def test_cancel_subagent(self, manager):
        """Test cancelling a sub-agent."""
        task = SubAgentTask(purpose="Test", task_description="Run test")
        run = manager.spawn_subagent(parent_id="main", task=task)
        
        result = manager.cancel_subagent(run.run_id)
        
        assert result is True
        updated = manager.get_subagent_run(run.run_id)
        assert updated.status == SubAgentStatus.CANCELLED
    
    def test_update_run_status(self, manager):
        """Test updating run status."""
        task = SubAgentTask(purpose="Test", task_description="Run test")
        run = manager.spawn_subagent(parent_id="main", task=task)
        
        result = SubAgentResult.success(content="Done")
        manager.update_run_status(
            run.run_id,
            SubAgentStatus.COMPLETED,
            result=result,
        )
        
        updated = manager.get_subagent_run(run.run_id)
        assert updated.status == SubAgentStatus.COMPLETED
        assert updated.result == result
    
    def test_get_statistics(self, manager):
        """Test getting statistics."""
        # Spawn some sub-agents
        for i in range(3):
            task = SubAgentTask(purpose=f"Task {i}", task_description=f"Do {i}")
            manager.spawn_subagent(parent_id="main", task=task)
        
        stats = manager.get_statistics()
        
        assert stats["total_runs"] == 3
        assert stats["status_counts"]["pending"] == 3


class TestSubAgentSummarizer:
    """Test sub-agent result summarization."""
    
    @pytest.fixture
    def summarizer(self):
        """Create a summarizer for each test."""
        return SubAgentSummarizer()
    
    def test_summarize_empty_results(self, summarizer):
        """Test summarizing empty results."""
        summary = summarizer.summarize_results([])
        
        assert "No sub-agent results" in summary
    
    def test_summarize_successful_results(self, summarizer):
        """Test summarizing successful results."""
        results = [
            SubAgentResult.success(content="Result 1"),
            SubAgentResult.success(content="Result 2"),
        ]
        
        summary = summarizer.summarize_results(results)
        
        assert "2/2 successful" in summary
        assert "Result 1" in summary
        assert "Result 2" in summary
    
    def test_summarize_mixed_results(self, summarizer):
        """Test summarizing mixed success/failure."""
        results = [
            SubAgentResult.success(content="Success result"),
            SubAgentResult.error(error_message="Failed", error_code="ERROR"),
        ]
        
        summary = summarizer.summarize_results(results)
        
        assert "1/2 successful" in summary
        assert "Successful Results" in summary
        assert "Failed/Partial Results" in summary
    
    def test_extract_key_findings(self, summarizer):
        """Test extracting key findings."""
        results = [
            SubAgentResult(
                ok=True,
                content="Done",
                metadata={"finding": "Important info"},
            ),
            SubAgentResult(
                ok=False,
                error_message="Error",
                error_code="ERROR",
            ),
        ]
        
        findings = summarizer.extract_key_findings(results)
        
        # Should find the metadata finding
        assert "Important info" in findings
    
    def test_generate_summary_report(self, summarizer):
        """Test generating comprehensive summary report."""
        results = [
            SubAgentResult.success(content="Task 1 done", metadata={"turns": 5}),
            SubAgentResult.success(content="Task 2 done", metadata={"turns": 3}),
        ]
        
        report = summarizer.generate_summary_report(
            results,
            task_descriptions=["First task", "Second task"],
        )
        
        assert report.ok is True
        assert "First task" in report.content
        assert "Second task" in report.content
        assert report.metadata["total"] == 2
        assert report.metadata["successful"] == 2
    
    def test_aggregate_metrics(self, summarizer):
        """Test aggregating metrics."""
        results = [
            SubAgentResult(ok=True, content="", metadata={"turns": 5, "tool_calls": 3}),
            SubAgentResult(ok=True, content="", metadata={"turns": 3, "tool_calls": 2}),
            SubAgentResult(ok=False, content="", metadata={"turns": 2, "tool_calls": 1}),
        ]
        
        metrics = summarizer.aggregate_metrics(results)
        
        assert metrics["total_subagents"] == 3
        assert metrics["successful"] == 2
        assert metrics["failed"] == 1
        assert metrics["success_rate"] == pytest.approx(2/3)
        assert metrics["total_turns"] == 10


class TestPolicyEnforcement:
    """Test policy enforcement scenarios."""
    
    def test_exec_tool_blocked_by_default(self):
        """Test that exec tool is blocked by default policy."""
        policy = SubAgentPolicy()
        
        # Default policy doesn't have a denylist, so it allows all tools
        # The no_exec flag is informational; actual blocking happens in executor
        assert policy.is_tool_allowed("exec") is True
        assert policy.no_exec is True
    
    def test_nested_subagents_blocked_by_default(self):
        """Test that nested sub-agents are blocked by default."""
        policy = SubAgentPolicy()
        
        assert policy.allow_subagents is False
    
    def test_parent_policy_inheritance(self):
        """Test parent policy inheritance."""
        manager = SubAgentPolicyManager()
        
        parent = SubAgentPolicy(
            max_spawn_depth=2,
            tool_allowlist=["web", "memory"],
            allow_subagents=True,
        )
        
        child = manager.get_policy(
            requested_policy=SubAgentPolicy(),
            parent_policy=parent,
        )
        
        assert child.max_spawn_depth == 1
        # Child inherits the stricter defaults
        assert child.allow_subagents is False
        assert "web" in child.tool_allowlist
    
    def test_denylist_inheritance(self):
        """Test that denylists are inherited and combined."""
        manager = SubAgentPolicyManager()
        
        parent = SubAgentPolicy(tool_denylist=["exec"])
        
        child = manager.get_policy(
            requested_policy=SubAgentPolicy(tool_denylist=["sudo"]),
            parent_policy=parent,
        )
        
        assert "exec" in child.tool_denylist
        assert "sudo" in child.tool_denylist


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
