"""
Sub-agent execution for the Teiken Claw agent system.

This module provides the SubAgentExecutor class for executing child
agents with constrained runtime context, tool restrictions, and
resource limits.

Key Features:
    - SubAgentExecutor: Executes sub-agent with policy constraints
    - Tool restriction enforcement
    - Timeout handling
    - Max turns enforcement
    - Result aggregation
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.subagents.manager import SubAgentManager, get_subagent_manager
from app.subagents.models import (
    SubAgentPolicy,
    SubAgentResult,
    SubAgentRunRecord,
    SubAgentStatus,
    SubAgentTask,
)
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry, get_tool_registry

logger = logging.getLogger(__name__)


class SubAgentExecutor:
    """
    Executor for sub-agent runs.
    
    Handles constrained execution of child agents, including
    tool restrictions, timeout enforcement, and result aggregation.
    
    Attributes:
        manager: Sub-agent manager for run tracking
        tool_registry: Tool registry for tool execution
    """
    
    def __init__(
        self,
        manager: Optional[SubAgentManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        """
        Initialize the sub-agent executor.
        
        Args:
            manager: Sub-agent manager (uses global if None)
            tool_registry: Tool registry (uses global if None)
        """
        self.manager = manager or get_subagent_manager()
        self.tool_registry = tool_registry or get_tool_registry()
        
        logger.info(
            "SubAgentExecutor initialized",
            extra={"event": "subagent_executor_init"}
        )
    
    async def execute_subagent(
        self,
        run_id: str,
        task: SubAgentTask,
        policy: SubAgentPolicy,
    ) -> SubAgentResult:
        """
        Execute a sub-agent with the given task and policy.
        
        Creates a constrained runtime context, runs the agent loop
        with tool restrictions, and captures results.
        
        Args:
            run_id: ID of the run to execute
            task: Task specification
            policy: Policy constraints
            
        Returns:
            SubAgentResult from the execution
        """
        logger.info(
            f"Starting sub-agent execution: run_id={run_id}",
            extra={
                "event": "subagent_execute_start",
                "run_id": run_id,
                "purpose": task.purpose,
                "max_turns": policy.max_turns,
                "timeout_sec": policy.timeout_sec,
            }
        )
        
        # Update status to running
        self.manager.update_run_status(
            run_id=run_id,
            status=SubAgentStatus.RUNNING,
        )
        
        try:
            # Create constrained tool registry for this sub-agent
            allowed_tools = self._get_allowed_tools(policy)
            
            # Build initial context with task description
            messages = self._build_subagent_context(task, allowed_tools)
            
            # Get tool schemas for allowed tools
            tool_schemas = self._get_tool_schemas(allowed_tools)
            
            # Execute agent loop with constraints
            result = await self._execute_agent_loop(
                run_id=run_id,
                messages=messages,
                tools=tool_schemas,
                policy=policy,
            )
            
            # Update status to completed
            self.manager.update_run_status(
                run_id=run_id,
                status=SubAgentStatus.COMPLETED,
                result=result,
            )
            
            logger.info(
                f"Sub-agent execution completed: run_id={run_id}, ok={result.ok}",
                extra={
                    "event": "subagent_execute_complete",
                    "run_id": run_id,
                    "ok": result.ok,
                    "content_length": len(result.content),
                }
            )
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(
                f"Sub-agent execution timed out: run_id={run_id}",
                extra={
                    "event": "subagent_timeout",
                    "run_id": run_id,
                    "timeout_sec": policy.timeout_sec,
                }
            )
            
            error_result = SubAgentResult.error(
                error=f"Sub-agent execution timed out after {policy.timeout_sec}s",
                error_code="TIMEOUT",
            )
            
            self.manager.update_run_status(
                run_id=run_id,
                status=SubAgentStatus.FAILED,
                result=error_result,
                error_message=f"Timeout after {policy.timeout_sec}s",
            )
            
            return error_result
            
        except Exception as e:
            logger.exception(
                f"Sub-agent execution failed: run_id={run_id}",
                extra={
                    "event": "subagent_error",
                    "run_id": run_id,
                    "error": str(e),
                }
            )
            
            error_result = SubAgentResult.error(
                error=f"Sub-agent execution failed: {e}",
                error_code="EXECUTION_ERROR",
            )
            
            self.manager.update_run_status(
                run_id=run_id,
                status=SubAgentStatus.FAILED,
                result=error_result,
                error_message=str(e),
            )
            
            return error_result
    
    def _get_allowed_tools(self, policy: SubAgentPolicy) -> List[str]:
        """
        Get list of allowed tools based on policy.
        
        Args:
            policy: Policy with tool restrictions
            
        Returns:
            List of allowed tool names
        """
        all_tools = self.tool_registry.get_all()
        allowed = []
        
        for tool in all_tools:
            tool_name = tool.name
            
            # Check if tool is allowed by policy
            if policy.is_tool_allowed(tool_name):
                # Additional safety checks
                if policy.no_exec and tool_name in ("exec", "run_code"):
                    continue
                if policy.no_scheduler_mutation and tool_name in ("scheduler_create", "scheduler_update", "scheduler_delete"):
                    continue
                    
                allowed.append(tool_name)
        
        logger.debug(
            f"Allowed tools for sub-agent: {allowed}",
            extra={
                "event": "subagent_tools_allowed",
                "tool_count": len(allowed),
            }
        )
        
        return allowed
    
    def _get_tool_schemas(self, tool_names: List[str]) -> List[Dict[str, Any]]:
        """
        Get Ollama tool schemas for allowed tools.
        
        Args:
            tool_names: List of allowed tool names
            
        Returns:
            List of tool schemas
        """
        schemas = []
        for name in tool_names:
            tool = self.tool_registry.get(name)
            if tool:
                schemas.append(tool.json_schema)
        
        return schemas
    
    def _build_subagent_context(
        self,
        task: SubAgentTask,
        allowed_tools: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Build initial context for sub-agent.
        
        Args:
            task: Task specification
            allowed_tools: List of allowed tool names
            
        Returns:
            List of messages for the agent
        """
        # Build system prompt with task and constraints
        system_prompt = self._build_system_prompt(task, allowed_tools)
        
        # Add user task as first message
        user_message = f"Task: {task.task_description}"
        if task.inputs:
            user_message += f"\n\nInput data:\n{task._format_inputs()}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        return messages
    
    def _build_system_prompt(
        self,
        task: SubAgentTask,
        allowed_tools: List[str],
    ) -> str:
        """
        Build system prompt for sub-agent.
        
        Args:
            task: Task specification
            allowed_tools: List of allowed tool names
            
        Returns:
            System prompt string
        """
        tool_list = ", ".join(allowed_tools) if allowed_tools else "none"
        
        prompt = f"""You are a specialized sub-agent tasked with: {task.purpose}

AVAILABLE TOOLS: {tool_list}

IMPORTANT CONSTRAINTS:
- You must complete the task using only the available tools
- Do not ask for clarification - make reasonable assumptions
- Be concise and focused on completing the specific task
- If you cannot complete the task with available tools, explain why

Task: {task.task_description}
"""
        
        if task.output_schema:
            prompt += f"\nOutput should conform to this schema:\n{task.output_schema}"
        
        return prompt
    
    async def _execute_agent_loop(
        self,
        run_id: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        policy: SubAgentPolicy,
    ) -> SubAgentResult:
        """
        Execute the agent loop with tool restrictions.
        
        Args:
            run_id: Run ID for logging
            messages: Initial messages
            tools: Allowed tool schemas
            policy: Policy constraints
            
        Returns:
            SubAgentResult from execution
        """
        from app.agent.runtime import AgentResult
        from app.agent.ollama_client import OllamaClient, get_ollama_client
        
        # Get Ollama client
        ollama_client = get_ollama_client()
        
        turn = 0
        max_turns = policy.max_turns
        tool_results_accumulated: List[Dict[str, Any]] = []
        
        while turn < max_turns:
            turn += 1
            
            try:
                # Call Ollama
                response = await asyncio.wait_for(
                    ollama_client.chat(messages=messages, tools=tools),
                    timeout=policy.timeout_sec,
                )
                
                # Check for tool calls
                tool_calls = self._extract_tool_calls(response)
                
                if not tool_calls:
                    # Final response - we're done
                    content = response.message.content or ""
                    
                    # Truncate if needed
                    if len(content) > policy.max_output_chars:
                        content = content[:policy.max_output_chars] + "..."
                    
                    return SubAgentResult.success(
                        content=content,
                        metadata={
                            "turns": turn,
                            "tool_calls": len(tool_results_accumulated),
                        }
                    )
                
                # Process tool calls
                for tool_call in tool_calls:
                    tool_result = await self._execute_tool_call(
                        tool_call=tool_call,
                        policy=policy,
                    )
                    
                    tool_results_accumulated.append({
                        "tool_name": tool_call.get("function", {}).get("name", ""),
                        "result": tool_result,
                    })
                    
                    # Add tool result to messages
                    messages.append({
                        "role": "assistant",
                        "content": response.message.content or "",
                        "tool_calls": [tool_call],
                    })
                    
                    messages.append({
                        "role": "tool",
                        "content": tool_result.content,
                        "name": tool_call.get("function", {}).get("name", ""),
                    })
                
                # Check termination conditions
                if self._should_terminate(tool_results_accumulated, turn, max_turns):
                    # Return accumulated results
                    summary = self._summarize_results(tool_results_accumulated)
                    return SubAgentResult.success(
                        content=summary,
                        metadata={
                            "turns": turn,
                            "tool_calls": len(tool_results_accumulated),
                            "terminated_early": True,
                        }
                    )
                
            except asyncio.TimeoutError:
                # Timeout during agent call
                if tool_results_accumulated:
                    # Return partial results
                    summary = self._summarize_results(tool_results_accumulated)
                    return SubAgentResult.success(
                        content=summary,
                        metadata={
                            "turns": turn,
                            "tool_calls": len(tool_results_accumulated),
                            "partial": True,
                        }
                    )
                raise
        
        # Max turns exceeded
        if tool_results_accumulated:
            summary = self._summarize_results(tool_results_accumulated)
            return SubAgentResult.success(
                content=summary,
                metadata={
                    "turns": turn,
                    "tool_calls": len(tool_results_accumulated),
                    "max_turns_reached": True,
                }
            )
        
        return SubAgentResult.error(
            error="Max turns exceeded without results",
            error_code="MAX_TURNS_EXCEEDED",
        )
    
    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        """Extract tool calls from response."""
        if not hasattr(response, "message"):
            return []
        
        tool_calls = response.message.tool_calls
        if not tool_calls:
            return []
        
        result = []
        for call in tool_calls:
            if isinstance(call, dict):
                result.append(call)
            else:
                result.append({
                    "function": {
                        "name": getattr(call, "name", ""),
                        "arguments": getattr(call, "arguments", {}),
                    }
                })
        
        return result
    
    async def _execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        policy: SubAgentPolicy,
    ) -> ToolResult:
        """
        Execute a single tool call with policy constraints.
        
        Args:
            tool_call: Tool call to execute
            policy: Policy constraints
            
        Returns:
            ToolResult from execution
        """
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = function.get("arguments", {})
        
        # Get tool from registry
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return ToolResult.error(
                error_code="UNKNOWN_TOOL",
                error_message=f"Tool not found: {tool_name}",
            )
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                tool.execute(**arguments),
                timeout=min(policy.timeout_sec, 30),  # Cap individual tool timeout
            )
            
            # Truncate output if needed
            if len(result.content) > policy.max_output_chars:
                result = result.truncate_content(policy.max_output_chars)
            
            return result
            
        except asyncio.TimeoutError:
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Tool {tool_name} timed out",
            )
        except Exception as e:
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Tool {tool_name} failed: {e}",
            )
    
    def _should_terminate(
        self,
        tool_results: List[Dict[str, Any]],
        current_turn: int,
        max_turns: int,
    ) -> bool:
        """
        Check if agent loop should terminate.
        
        Args:
            tool_results: Accumulated tool results
            current_turn: Current turn number
            max_turns: Maximum allowed turns
            
        Returns:
            True if should terminate
        """
        # Check if last tool indicated completion
        if tool_results:
            last_result = tool_results[-1].get("result")
            if last_result and last_result.metadata.get("should_stop"):
                return True
        
        return False
    
    def _summarize_results(
        self,
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """
        Summarize accumulated tool results.
        
        Args:
            tool_results: List of tool results
            
        Returns:
            Summary string
        """
        if not tool_results:
            return "No results generated."
        
        lines = ["Sub-agent execution results:\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("tool_name", "unknown")
            tool_result = result.get("result")
            
            lines.append(f"\n{i}. {tool_name}:")
            
            if tool_result:
                if tool_result.ok:
                    content = tool_result.content
                    # Truncate long outputs
                    if len(content) > 500:
                        content = content[:500] + "..."
                    lines.append(f"   {content}")
                else:
                    lines.append(f"   ERROR: {tool_result.error_message}")
        
        return "\n".join(lines)


# Global executor instance
_executor: Optional[SubAgentExecutor] = None


def get_subagent_executor() -> SubAgentExecutor:
    """
    Get the global sub-agent executor instance.
    
    Returns:
        Global SubAgentExecutor instance
    """
    global _executor
    if _executor is None:
        _executor = SubAgentExecutor()
    return _executor


def set_subagent_executor(executor: SubAgentExecutor) -> None:
    """
    Set the global sub-agent executor instance.
    
    Args:
        executor: SubAgentExecutor to use globally
    """
    global _executor
    _executor = executor


__all__ = [
    "SubAgentExecutor",
    "get_subagent_executor",
    "set_subagent_executor",
]
