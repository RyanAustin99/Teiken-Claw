"""
Sub-agent tool for the Teiken Claw agent system.

This module provides the SubAgentTool class that allows agents to
spawn constrained child agents for specialized tasks.

Key Features:
    - SubAgentTool: Tool for spawning sub-agents
    - spawn_subagent: Create a constrained child agent
    - get_subagent_status: Check status of a sub-agent run
    - wait_for_subagent: Wait for sub-agent completion (optional polling)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.tools.base import Tool, ToolPolicy, ToolResult
from app.subagents.manager import (
    SubAgentManager,
    SubAgentNotFound,
    get_subagent_manager,
)
from app.subagents.executor import (
    SubAgentExecutor,
    get_subagent_executor,
)
from app.subagents.summarizer import (
    SubAgentSummarizer,
    get_subagent_summarizer,
)
from app.subagents.models import SubAgentPolicy, SubAgentTask, SubAgentTrigger

logger = logging.getLogger(__name__)


class SubAgentTool(Tool):
    """
    Tool for spawning and managing sub-agents.
    
    Allows parent agents to spawn constrained child agents for
    specialized tasks with limited permissions and resources.
    """
    
    def __init__(
        self,
        manager: Optional[SubAgentManager] = None,
        executor: Optional[SubAgentExecutor] = None,
        summarizer: Optional[SubAgentSummarizer] = None,
        policy: Optional[ToolPolicy] = None,
    ):
        """
        Initialize the sub-agent tool.
        
        Args:
            manager: Sub-agent manager (uses global if None)
            executor: Sub-agent executor (uses global if None)
            summarizer: Sub-agent summarizer (uses global if None)
            policy: Tool policy
        """
        super().__init__(policy=policy)
        
        self.manager = manager or get_subagent_manager()
        self.executor = executor or get_subagent_executor()
        self.summarizer = summarizer or get_subagent_summarizer()
        
        logger.info(
            "SubAgentTool initialized",
            extra={"event": "subagent_tool_init"}
        )
    
    @property
    def name(self) -> str:
        """Tool name."""
        return "spawn_subagent"
    
    @property
    def description(self) -> str:
        """
        Human-readable description.
        
        Returns:
            Description of what this tool does
        """
        return """Spawn a specialized sub-agent to handle a specific task.

Use this tool when:
- A task can be broken down into independent subtasks
- You need specialized capabilities for a specific job
- You want to run multiple tasks in parallel

The sub-agent will have restricted access based on the allowed_tools parameter.
Sub-agents are subject to resource limits (max_turns, timeout_sec)."""
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        """
        Ollama-compatible tool definition.
        
        Returns:
            Tool definition in Ollama format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "purpose": {
                            "type": "string",
                            "description": "Short description of the sub-agent's purpose (e.g., 'research', 'file_analysis')",
                        },
                        "task_description": {
                            "type": "string",
                            "description": "Detailed description of what the sub-agent should do",
                        },
                        "inputs": {
                            "type": "object",
                            "description": "Input data/context for the sub-agent",
                            "default": {},
                        },
                        "allowed_tools": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tool names the sub-agent can use (empty = all tools except restricted)",
                            "default": [],
                        },
                        "max_turns": {
                            "type": "integer",
                            "description": "Maximum agent turns for the sub-agent",
                            "default": 20,
                        },
                        "timeout_sec": {
                            "type": "integer",
                            "description": "Maximum execution time in seconds",
                            "default": 300,
                        },
                        "output_schema": {
                            "type": "object",
                            "description": "Optional JSON schema for expected output format",
                        },
                        "wait_for_result": {
                            "type": "boolean",
                            "description": "Whether to wait for the sub-agent to complete (True) or return immediately with run ID (False)",
                            "default": True,
                        },
                    },
                    "required": ["purpose", "task_description"],
                },
            },
        }
    
    async def spawn_subagent(
        self,
        purpose: str,
        task_description: str,
        inputs: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        max_turns: int = 20,
        timeout_sec: int = 300,
        output_schema: Optional[Dict[str, Any]] = None,
        wait_for_result: bool = True,
        parent_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Spawn a sub-agent to handle a specific task.
        
        Args:
            purpose: Short description of the sub-agent's purpose
            task_description: Detailed task description
            inputs: Input data for the task
            allowed_tools: List of allowed tool names
            max_turns: Maximum agent turns
            timeout_sec: Maximum execution time
            output_schema: Optional output schema
            wait_for_result: Whether to wait for completion
            parent_id: Parent agent/job ID
            
        Returns:
            Dictionary with run_id and optionally result
        """
        logger.info(
            f"Spawning sub-agent: purpose={purpose}, parent={parent_id}",
            extra={
                "event": "spawn_subagent",
                "purpose": purpose,
                "parent_id": parent_id,
            }
        )
        
        # Create task
        task = SubAgentTask(
            purpose=purpose,
            task_description=task_description,
            inputs=inputs or {},
            output_schema=output_schema,
        )
        
        # Create policy
        policy = SubAgentPolicy(
            max_spawn_depth=1,
            max_children_per_parent=3,
            tool_allowlist=allowed_tools or [],
            tool_denylist=["exec", "run_code", "sudo"],  # Always deny dangerous tools
            timeout_sec=timeout_sec,
            max_turns=max_turns,
            no_scheduler_mutation=False,  # Allow scheduler access
            no_exec=True,  # Always prevent exec
            max_output_chars=10000,
            allow_subagents=False,  # Don't allow nested sub-agents by default
        )
        
        try:
            # Spawn the sub-agent
            run_record = self.manager.spawn_subagent(
                parent_id=parent_id,
                task=task,
                policy=policy,
                trigger=SubAgentTrigger.AGENT,
            )
            
            if not wait_for_result:
                return {
                    "run_id": run_record.run_id,
                    "status": run_record.status.value,
                    "message": f"Sub-agent spawned: {run_record.run_id}",
                }
            
            # Execute and wait for result
            result = await self.executor.execute_subagent(
                run_id=run_record.run_id,
                task=task,
                policy=policy,
            )
            
            return {
                "run_id": run_record.run_id,
                "status": "completed",
                "ok": result.ok,
                "content": result.content,
                "error": result.error,
                "error_code": result.error_code,
            }
            
        except Exception as e:
            logger.exception(f"Failed to spawn sub-agent: {e}")
            return {
                "run_id": None,
                "status": "failed",
                "ok": False,
                "error": str(e),
                "error_code": "SPAWN_FAILED",
            }
    
    async def get_subagent_status(self, run_id: str) -> Dict[str, Any]:
        """
        Get the status of a sub-agent run.
        
        Args:
            run_id: ID of the sub-agent run
            
        Returns:
            Status dictionary
        """
        try:
            run = self.manager.get_subagent_run(run_id)
            
            return {
                "run_id": run.run_id,
                "status": run.status.value,
                "purpose": run.task.purpose,
                "depth": run.depth,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "duration_seconds": run.duration_seconds(),
                "result": {
                    "ok": run.result.ok if run.result else None,
                    "content": run.result.content[:500] if run.result and run.result.content else None,
                } if run.result else None,
                "error": run.error_message,
            }
            
        except SubAgentNotFound:
            return {
                "run_id": run_id,
                "status": "not_found",
                "error": f"Sub-agent run not found: {run_id}",
            }
    
    async def wait_for_subagent(
        self,
        run_id: str,
        poll_interval_sec: float = 2.0,
        max_wait_sec: float = 300.0,
    ) -> Dict[str, Any]:
        """
        Wait for a sub-agent to complete.
        
        Polls the sub-agent status until completed or timeout.
        
        Args:
            run_id: ID of the sub-agent run
            poll_interval_sec: How often to poll
            max_wait_sec: Maximum time to wait
            
        Returns:
            Final status dictionary
        """
        import time
        from app.subagents.models import SubAgentStatus
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait_sec:
            status_result = await self.get_subagent_status(run_id)
            status = status_result.get("status")
            
            if status in ("completed", "failed", "cancelled"):
                return status_result
            
            await asyncio.sleep(poll_interval_sec)
        
        # Timeout
        return {
            "run_id": run_id,
            "status": "timeout",
            "error": f"Waited {max_wait_sec}s for sub-agent completion",
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the sub-agent tool.
        
        Args:
            **kwargs: Arguments from Ollama tool call
            
        Returns:
            ToolResult with execution results
        """
        try:
            # Extract arguments
            purpose = kwargs.get("purpose")
            task_description = kwargs.get("task_description")
            inputs = kwargs.get("inputs", {})
            allowed_tools = kwargs.get("allowed_tools")
            max_turns = kwargs.get("max_turns", 20)
            timeout_sec = kwargs.get("timeout_sec", 300)
            output_schema = kwargs.get("output_schema")
            wait_for_result = kwargs.get("wait_for_result", True)
            
            if not purpose or not task_description:
                return ToolResult.error(
                    error_code="INVALID_ARGS",
                    error_message="purpose and task_description are required",
                )
            
            # Get parent_id from context if available
            parent_id = kwargs.get("parent_id", "main")
            
            # Spawn sub-agent
            result = await self.spawn_subagent(
                purpose=purpose,
                task_description=task_description,
                inputs=inputs,
                allowed_tools=allowed_tools,
                max_turns=max_turns,
                timeout_sec=timeout_sec,
                output_schema=output_schema,
                wait_for_result=wait_for_result,
                parent_id=parent_id,
            )
            
            # Format result
            if result.get("ok", False) or result.get("status") == "completed":
                content = result.get("content", "")
                
                # Add status info
                if not content:
                    content = f"Sub-agent completed: {result.get('run_id')}"
                
                return ToolResult.success(
                    content=content,
                    metadata={
                        "run_id": result.get("run_id"),
                        "status": result.get("status"),
                        "purpose": purpose,
                    }
                )
            else:
                return ToolResult.error(
                    error_code=result.get("error_code", "SUBAGENT_ERROR"),
                    error_message=result.get("error", "Sub-agent failed"),
                    metadata={
                        "run_id": result.get("run_id"),
                        "status": result.get("status"),
                    }
                )
                
        except Exception as e:
            logger.exception(f"SubAgentTool execution failed: {e}")
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Sub-agent tool failed: {e}",
            )


# Global tool instance
_subagent_tool: Optional[SubAgentTool] = None


def get_subagent_tool() -> SubAgentTool:
    """
    Get the global sub-agent tool instance.
    
    Returns:
        Global SubAgentTool instance
    """
    global _subagent_tool
    if _subagent_tool is None:
        _subagent_tool = SubAgentTool()
    return _subagent_tool


def set_subagent_tool(tool: SubAgentTool) -> None:
    """
    Set the global sub-agent tool instance.
    
    Args:
        tool: SubAgentTool to use globally
    """
    global _subagent_tool
    _subagent_tool = tool


__all__ = [
    "SubAgentTool",
    "get_subagent_tool",
    "set_subagent_tool",
]
