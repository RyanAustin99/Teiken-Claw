"""
Core agent runtime for the Teiken Claw AI agent.

This module provides the AgentRuntime class that orchestrates the
agent loop, including tool calling, error handling, and message persistence.

Key Features:
    - Main agent loop with tool calling
    - MAX_TOOL_TURNS guard to prevent infinite loops
    - Duplicate tool call detection
    - Circuit breaker integration
    - Retry logic for transient errors
    - Graceful error handling
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel

from app.config.logging import get_logger
from app.config.settings import settings
from app.agent.ollama_client import OllamaClient, ChatResponse, get_ollama_client
from app.agent.errors import (
    OllamaError,
    OllamaTransportError,
    CircuitBreakerOpenError,
    is_retryable_error,
)
from app.agent.context_builder import ContextBuilder, get_context_builder
from app.agent.result_formatter import format_response
from app.queue.jobs import Job
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry, get_tool_registry

logger = get_logger(__name__)


# Constants
MAX_TOOL_TURNS = 10  # Maximum tool-calling iterations
MAX_RETRIES = 3  # Maximum retries for transient errors
RETRY_DELAY_BASE = 1.0  # Base delay for retries


class AgentResult(BaseModel):
    """
    Result of an agent run.
    
    Attributes:
        ok: Whether the run succeeded
        response: The final response text
        tool_calls: Number of tool calls made
        tool_results: Results from tool executions
        error: Error message if failed
        error_code: Error code if failed
        metadata: Additional metadata
    """
    
    ok: bool = True
    response: str = ""
    tool_calls: int = 0
    tool_results: List[Dict[str, Any]] = []
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    class Config:
        extra = "forbid"


@dataclass
class ToolCallRecord:
    """Record of a tool call for duplicate detection."""
    
    tool_name: str
    arguments_hash: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_call(cls, tool_call: Dict[str, Any]) -> "ToolCallRecord":
        """Create a record from a tool call."""
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = function.get("arguments", {})
        
        # Create hash of arguments for comparison
        args_str = json.dumps(arguments, sort_keys=True)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()
        
        return cls(tool_name=tool_name, arguments_hash=args_hash)


class AgentRuntime:
    """
    Core agent runtime that orchestrates the AI agent loop.
    
    The runtime handles:
    - Building conversation context
    - Calling Ollama with tools
    - Executing tool calls
    - Handling errors gracefully
    - Persisting messages
    
    Attributes:
        ollama_client: Ollama API client
        tool_registry: Tool registry for tool execution
        context_builder: Context builder for message assembly
        max_tool_turns: Maximum tool-calling iterations
    """
    
    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        context_builder: Optional[ContextBuilder] = None,
        max_tool_turns: int = MAX_TOOL_TURNS,
    ):
        """
        Initialize the agent runtime.
        
        Args:
            ollama_client: Ollama client (uses global if None)
            tool_registry: Tool registry (uses global if None)
            context_builder: Context builder (uses default if None)
            max_tool_turns: Maximum tool-calling iterations
        """
        self.ollama_client = ollama_client or get_ollama_client()
        self.tool_registry = tool_registry or get_tool_registry()
        self.context_builder = context_builder or get_context_builder()
        self.max_tool_turns = max_tool_turns
        
        logger.info(
            f"AgentRuntime initialized: max_tool_turns={max_tool_turns}",
            extra={"event": "agent_runtime_initialized"}
        )
    
    async def run(self, job: Job) -> AgentResult:
        """
        Run the agent loop for a job.
        
        This is the main entry point for processing a job.
        
        Args:
            job: Job to process
            
        Returns:
            AgentResult with the final response
        """
        logger.info(
            f"Starting agent run for job: {job.job_id}",
            extra={
                "event": "agent_run_start",
                "job_id": job.job_id,
                "chat_id": job.chat_id,
            }
        )
        
        # Track tool calls for duplicate detection
        tool_call_history: List[ToolCallRecord] = []
        
        # Build initial context
        messages = await self._build_initial_context(job)
        
        # Get available tools
        tools = self._get_tools_for_context(job)
        
        # Main agent loop
        turn = 0
        while turn < self.max_tool_turns + 1:
            turn += 1
            
            logger.debug(
                f"Agent loop turn {turn}",
                extra={"event": "agent_turn", "turn": turn, "job_id": job.job_id}
            )
            
            try:
                # Call Ollama
                response = await self._call_ollama_with_retry(
                    messages=messages,
                    tools=tools,
                )
                
                # Check if we have a final response (no tool calls)
                tool_calls = self._extract_tool_calls(response)
                
                if not tool_calls:
                    # Final response - we're done
                    final_content = response.message.content or ""
                    
                    logger.info(
                        f"Agent run completed: {job.job_id}",
                        extra={
                            "event": "agent_run_complete",
                            "job_id": job.job_id,
                            "turns": turn,
                            "response_length": len(final_content),
                        }
                    )
                    
                    return AgentResult(
                        ok=True,
                        response=final_content,
                        tool_calls=len(tool_call_history),
                        tool_results=[],
                        metadata={"turns": turn},
                    )
                
                # Process tool calls
                tool_results = await self._process_tool_calls(
                    tool_calls=tool_calls,
                    tool_call_history=tool_call_history,
                    context=self._build_tool_context(job),
                )
                
                # Append assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": response.message.content or "",
                    "tool_calls": tool_calls,
                })
                
                # Append tool result messages
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "content": result.get("content", ""),
                        "name": result.get("tool_name", ""),
                    })
                
                # Check if we should continue
                if not self._should_continue(tool_results):
                    # One of the tools indicated we should stop
                    logger.info(
                        f"Tool indicated stop: {job.job_id}",
                        extra={"event": "tool_stop", "job_id": job.job_id}
                    )
                    
                    # Get final response
                    final_response = await self._call_ollama_with_retry(
                        messages=messages,
                        tools=None,  # No tools for final response
                    )
                    
                    return AgentResult(
                        ok=True,
                        response=final_response.message.content or "",
                        tool_calls=len(tool_call_history),
                        tool_results=tool_results,
                        metadata={"turns": turn, "stopped_by_tool": True},
                    )
                
            except CircuitBreakerOpenError as e:
                logger.error(
                    f"Circuit breaker open: {e}",
                    extra={"event": "circuit_breaker_open", "job_id": job.job_id}
                )
                return AgentResult(
                    ok=False,
                    error="Service temporarily unavailable. Please try again later.",
                    error_code="CIRCUIT_BREAKER_OPEN",
                    metadata={"breaker_name": e.breaker_name},
                )
                
            except OllamaTransportError as e:
                logger.error(
                    f"Ollama transport error: {e}",
                    extra={"event": "ollama_transport_error", "job_id": job.job_id}
                )
                return AgentResult(
                    ok=False,
                    error="Failed to connect to AI service. Please try again.",
                    error_code="TRANSPORT_ERROR",
                    metadata={"endpoint": e.endpoint},
                )
                
            except OllamaError as e:
                logger.error(
                    f"Ollama error: {e}",
                    extra={"event": "ollama_error", "job_id": job.job_id}
                )
                return AgentResult(
                    ok=False,
                    error=f"AI service error: {e.message}",
                    error_code="OLLAMA_ERROR",
                    metadata={"details": e.details},
                )
                
            except Exception as e:
                logger.exception(
                    f"Unexpected error in agent loop: {e}",
                    extra={"event": "agent_error", "job_id": job.job_id}
                )
                return AgentResult(
                    ok=False,
                    error="An unexpected error occurred. Please try again.",
                    error_code="INTERNAL_ERROR",
                    metadata={"error_type": type(e).__name__},
                )
        
        # Max turns exceeded
        logger.warning(
            f"Max tool turns exceeded: {job.job_id}",
            extra={"event": "max_turns_exceeded", "job_id": job.job_id, "turns": turn}
        )
        
        return AgentResult(
            ok=False,
            error="Maximum tool calls exceeded. Please simplify your request.",
            error_code="MAX_TURNS_EXCEEDED",
            metadata={"turns": turn, "max_turns": self.max_tool_turns},
        )
    
    async def _build_initial_context(self, job: Job) -> List[Dict[str, Any]]:
        """
        Build the initial message context for a job.
        
        Args:
            job: Job to build context for
            
        Returns:
            List of messages for Ollama
        """
        # Get user message from job payload
        user_message = job.payload.get("text", "") or job.payload.get("message", "")
        
        # Build context
        messages = self.context_builder.build_with_user_message(
            user_message=user_message,
            session_id=job.session_id,
            thread_id=job.thread_id,
            mode=job.payload.get("mode", "default"),
        )
        
        return messages
    
    def _get_tools_for_context(self, job: Job) -> List[Dict[str, Any]]:
        """
        Get available tools for the job context.
        
        Args:
            job: Job to get tools for
            
        Returns:
            List of tool schemas
        """
        chat_id = job.chat_id
        is_admin = job.payload.get("is_admin", False)
        mode = job.payload.get("mode", "default")
        
        return self.tool_registry.get_allowed_schemas(
            mode=mode,
            chat_id=chat_id,
            is_admin=is_admin,
        )
    
    def _build_tool_context(self, job: Job) -> Dict[str, Any]:
        """
        Build context for tool execution.
        
        Args:
            job: Job to build context for
            
        Returns:
            Context dictionary for tool execution
        """
        return {
            "job_id": job.job_id,
            "chat_id": job.chat_id,
            "session_id": job.session_id,
            "thread_id": job.thread_id,
            "is_admin": job.payload.get("is_admin", False),
            "source": job.source,
        }
    
    async def _call_ollama_with_retry(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatResponse:
        """
        Call Ollama with retry logic for transient errors.
        
        Args:
            messages: Conversation messages
            tools: Available tools
            
        Returns:
            ChatResponse from Ollama
            
        Raises:
            OllamaError: If all retries fail
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.ollama_client.chat(
                    messages=messages,
                    tools=tools,
                )
                return response
                
            except OllamaTransportError as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"Ollama call failed, retrying in {delay}s: {e}",
                        extra={"attempt": attempt + 1, "max_attempts": MAX_RETRIES}
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
                    
            except CircuitBreakerOpenError:
                raise
                
            except OllamaError:
                # Non-retryable Ollama errors
                raise
        
        # Should not reach here
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state in Ollama retry logic")
    
    def _extract_tool_calls(self, response: ChatResponse) -> List[Dict[str, Any]]:
        """
        Extract tool calls from an Ollama response.
        
        Args:
            response: ChatResponse from Ollama
            
        Returns:
            List of tool call dictionaries
        """
        tool_calls = response.message.tool_calls
        if not tool_calls:
            return []
        
        # Ensure proper format
        result = []
        for call in tool_calls:
            if isinstance(call, dict):
                result.append(call)
            else:
                # Convert if needed
                result.append({
                    "function": {
                        "name": getattr(call, "name", ""),
                        "arguments": getattr(call, "arguments", {}),
                    }
                })
        
        return result
    
    async def _process_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_call_history: List[ToolCallRecord],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Process a list of tool calls.
        
        Args:
            tool_calls: Tool calls to process
            tool_call_history: History for duplicate detection
            context: Execution context
            
        Returns:
            List of tool result dictionaries
        """
        results = []
        
        for tool_call in tool_calls:
            # Check for duplicate
            record = ToolCallRecord.from_call(tool_call)
            
            if self._is_duplicate_call(record, tool_call_history):
                logger.warning(
                    f"Duplicate tool call detected: {record.tool_name}",
                    extra={
                        "event": "duplicate_tool_call",
                        "tool_name": record.tool_name,
                    }
                )
                # Return error result for duplicate
                results.append({
                    "tool_name": record.tool_name,
                    "content": json.dumps({
                        "error": "Duplicate tool call detected",
                        "error_code": "DUPLICATE_CALL",
                    }),
                    "ok": False,
                })
                continue
            
            # Add to history
            tool_call_history.append(record)
            
            # Execute tool
            result = await self.tool_registry.execute_tool_call(
                tool_call=tool_call,
                context=context,
            )
            
            # Convert to dict for message
            results.append({
                "tool_name": record.tool_name,
                "content": result.content,
                "ok": result.ok,
                "error_code": result.error_code,
                "error_message": result.error_message,
            })
            
            # Log tool execution
            self._log_tool_execution(record.tool_name, result, context)
        
        return results
    
    def _is_duplicate_call(
        self,
        record: ToolCallRecord,
        history: List[ToolCallRecord],
    ) -> bool:
        """
        Check if a tool call is a duplicate.
        
        Args:
            record: Current tool call record
            history: History of previous calls
            
        Returns:
            True if duplicate, False otherwise
        """
        for prev in history:
            if (
                prev.tool_name == record.tool_name
                and prev.arguments_hash == record.arguments_hash
            ):
                return True
        return False
    
    def _should_continue(self, tool_results: List[Dict[str, Any]]) -> bool:
        """
        Determine if the agent loop should continue.
        
        Args:
            tool_results: Results from tool executions
            
        Returns:
            True if should continue, False if should stop
        """
        # Continue if any tool returned an error that should stop
        for result in tool_results:
            if result.get("error_code") == "STOP":
                return False
        return True
    
    def _log_tool_execution(
        self,
        tool_name: str,
        result: ToolResult,
        context: Dict[str, Any],
    ) -> None:
        """
        Log a tool execution for audit purposes.
        
        Args:
            tool_name: Name of the tool
            result: Tool execution result
            context: Execution context
        """
        logger.info(
            f"Tool executed: {tool_name}",
            extra={
                "event": "tool_executed",
                "tool_name": tool_name,
                "ok": result.ok,
                "job_id": context.get("job_id"),
                "chat_id": context.get("chat_id"),
                "error_code": result.error_code,
            }
        )


# Global runtime instance
_runtime: Optional[AgentRuntime] = None


def get_agent_runtime() -> AgentRuntime:
    """
    Get the global agent runtime instance.
    
    Creates a new runtime if one doesn't exist.
    
    Returns:
        Global AgentRuntime instance
    """
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def set_agent_runtime(runtime: AgentRuntime) -> None:
    """
    Set the global agent runtime instance.
    
    Args:
        runtime: AgentRuntime instance to use globally
    """
    global _runtime
    _runtime = runtime


def reset_agent_runtime() -> None:
    """Reset the global agent runtime to None."""
    global _runtime
    _runtime = None


__all__ = [
    "AgentRuntime",
    "AgentResult",
    "ToolCallRecord",
    "MAX_TOOL_TURNS",
    "MAX_RETRIES",
    "get_agent_runtime",
    "set_agent_runtime",
    "reset_agent_runtime",
]
