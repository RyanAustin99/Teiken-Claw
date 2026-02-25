"""
Sub-agent data models for the Teiken Claw agent system.

This module defines the Pydantic models for sub-agent functionality,
including task specifications, results, policies, and audit records.

Key Features:
    - SubAgentTask: Task specification for child agent
    - SubAgentResult: Result from child agent execution
    - SubAgentPolicy: Policy constraints for child agent
    - SubAgentRunRecord: Audit trail for sub-agent runs
    - SubAgentStatus enum: Status of sub-agent runs
    - SubAgentTrigger enum: Trigger type for sub-agent spawning
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SubAgentStatus(str, Enum):
    """
    Status of a sub-agent run.
    
    Attributes:
        pending: Sub-agent task has been queued but not started
        running: Sub-agent is currently executing
        completed: Sub-agent completed successfully
        failed: Sub-agent encountered an error
        cancelled: Sub-agent was cancelled before completion
    """
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubAgentTrigger(str, Enum):
    """
    Trigger type for sub-agent spawning.
    
    Attributes:
        manual: Sub-agent spawned by explicit user/parent request
        skill: Sub-agent spawned by a skill (Phase 10)
        agent: Sub-agent spawned by another sub-agent
    """
    
    MANUAL = "manual"
    SKILL = "skill"
    AGENT = "agent"


class SubAgentTask(BaseModel):
    """
    Task specification for a sub-agent.
    
    Defines what the child agent should do, including inputs,
    expected outputs, and any context needed.
    
    Attributes:
        purpose: Short description of the sub-agent's purpose
        task_description: Detailed description of the task
        inputs: Input data/context for the task
        output_schema: Optional JSON schema for expected output format
    """
    
    purpose: str = Field(
        description="Short description of the sub-agent's purpose"
    )
    task_description: str = Field(
        description="Detailed description of what the sub-agent should do"
    )
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data and context for the sub-agent"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional JSON schema for expected output format"
    )
    
    class Config:
        extra = "forbid"


class SubAgentResult(BaseModel):
    """
    Result from sub-agent execution.
    
    Contains the output from a child agent run, including success
    status, content, errors, and metadata.
    
    Attributes:
        ok: Whether the sub-agent completed successfully
        content: The output content from the sub-agent
        error_message: Error message if the sub-agent failed
        error_code: Error code if the sub-agent failed
        metadata: Additional metadata about the execution
    """
    
    ok: bool = Field(
        default=True,
        description="Whether the sub-agent completed successfully"
    )
    content: str = Field(
        default="",
        description="The output content from the sub-agent"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the sub-agent failed"
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code if the sub-agent failed"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the execution"
    )
    
    @classmethod
    def success(
        cls,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "SubAgentResult":
        """
        Create a successful sub-agent result.
        
        Args:
            content: The output content
            metadata: Optional additional metadata
            
        Returns:
            SubAgentResult with ok=True
        """
        return cls(
            ok=True,
            content=content,
            metadata=metadata or {},
        )
    
    @classmethod
    def error(
        cls,
        error_message: str,
        error_code: str,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SubAgentResult":
        """
        Create an error sub-agent result.
        
        Args:
            error_message: Human-readable error message
            error_code: Machine-readable error code
            content: Optional partial content
            metadata: Optional additional metadata
            
        Returns:
            SubAgentResult with ok=False
        """
        return cls(
            ok=False,
            content=content,
            error_message=error_message,
            error_code=error_code,
            metadata=metadata or {},
        )


class SubAgentPolicy(BaseModel):
    """
    Policy constraints for a sub-agent.
    
    Defines restrictions and limits for child agent execution,
    including depth limits, tool restrictions, and resource bounds.
    
    Attributes:
        max_spawn_depth: Maximum depth of sub-agent nesting (default: 1)
        max_children_per_parent: Maximum children per parent (default: 3)
        tool_allowlist: List of allowed tool names (empty = all except restricted)
        tool_denylist: List of denied tool names
        timeout_sec: Maximum execution time in seconds (default: 300)
        max_turns: Maximum agent turns for the sub-agent (default: 20)
        no_scheduler_mutation: Whether to prevent scheduler mutations (default: True)
        no_exec: Whether to prevent command execution (default: True)
        max_output_chars: Maximum output characters (default: 10000)
        allow_subagents: Whether sub-agents can spawn their own sub-agents (default: False)
    """
    
    max_spawn_depth: int = Field(
        default=1,
        description="Maximum depth of sub-agent nesting"
    )
    max_children_per_parent: int = Field(
        default=3,
        description="Maximum children per parent agent"
    )
    tool_allowlist: List[str] = Field(
        default_factory=list,
        description="List of allowed tool names (empty = all allowed)"
    )
    tool_denylist: List[str] = Field(
        default_factory=list,
        description="List of denied tool names"
    )
    timeout_sec: int = Field(
        default=300,
        description="Maximum execution time in seconds"
    )
    max_turns: int = Field(
        default=20,
        description="Maximum agent turns for the sub-agent"
    )
    no_scheduler_mutation: bool = Field(
        default=True,
        description="Whether to prevent scheduler mutations"
    )
    no_exec: bool = Field(
        default=True,
        description="Whether to prevent command execution"
    )
    max_output_chars: int = Field(
        default=10000,
        description="Maximum output characters"
    )
    allow_subagents: bool = Field(
        default=False,
        description="Whether sub-agents can spawn their own sub-agents"
    )
    
    class Config:
        extra = "forbid"
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed by this policy.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            True if the tool is allowed, False otherwise
        """
        # If denylist is not empty, check it first
        if self.tool_denylist:
            if tool_name in self.tool_denylist:
                return False
        
        # If allowlist is not empty, tool must be in it
        if self.tool_allowlist:
            return tool_name in self.tool_allowlist
        
        # No restrictions - allow all
        return True


class SubAgentRunRecord(BaseModel):
    """
    Audit trail for a sub-agent run.
    
    Tracks the complete lifecycle of a sub-agent execution,
    including parent/child relationships, timing, and results.
    
    Attributes:
        run_id: Unique identifier for this sub-agent run
        parent_id: ID of the parent agent/job that spawned this sub-agent
        task: The task specification
        policy: The policy constraints applied
        status: Current status of the sub-agent run
        trigger: What triggered this sub-agent spawn
        depth: Current depth in the sub-agent tree
        created_at: When the sub-agent was created
        started_at: When the sub-agent started executing
        completed_at: When the sub-agent completed
        result: The result from execution (if completed)
        error_message: Error message if failed
        trace_id: Distributed tracing ID for tracking
    """
    
    run_id: str = Field(
        description="Unique identifier for this sub-agent run"
    )
    parent_id: str = Field(
        description="ID of the parent agent/job that spawned this sub-agent"
    )
    task: SubAgentTask = Field(
        description="The task specification"
    )
    policy: SubAgentPolicy = Field(
        description="The policy constraints applied"
    )
    status: SubAgentStatus = Field(
        default=SubAgentStatus.PENDING,
        description="Current status of the sub-agent run"
    )
    trigger: SubAgentTrigger = Field(
        default=SubAgentTrigger.MANUAL,
        description="What triggered this sub-agent spawn"
    )
    depth: int = Field(
        default=1,
        description="Current depth in the sub-agent tree"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the sub-agent was created"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When the sub-agent started executing"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the sub-agent completed"
    )
    result: Optional[SubAgentResult] = Field(
        default=None,
        description="The result from execution (if completed)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Distributed tracing ID for tracking"
    )
    child_run_ids: List[str] = Field(
        default_factory=list,
        description="IDs of child sub-agent runs spawned by this one"
    )
    
    class Config:
        extra = "forbid"
    
    def duration_seconds(self) -> Optional[float]:
        """
        Get the duration of the sub-agent run in seconds.
        
        Returns:
            Duration in seconds, or None if not completed
        """
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return None


__all__ = [
    "SubAgentStatus",
    "SubAgentTrigger",
    "SubAgentTask",
    "SubAgentResult",
    "SubAgentPolicy",
    "SubAgentRunRecord",
]
