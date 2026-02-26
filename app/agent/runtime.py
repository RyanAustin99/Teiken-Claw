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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
from app.queue.jobs import Job
from app.tools.base import ToolResult
from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.loop import run_tool_loop
from app.tools.registry import ToolRegistry, get_tool_registry

# Memory system imports
from app.memory.store import get_memory_store
from app.memory.thread_state import get_thread_state
from app.memory.extraction_rules import get_extraction_rules

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
        existing_tools = set(self.tool_registry.list_tools())
        required = {"files.write", "files.read", "files.list", "files.exists"}
        if not required.issubset(existing_tools):
            from app.tools import register_production_tools

            register_production_tools(self.tool_registry)
        self.tool_executor = ToolExecutor(self.tool_registry)
        
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
        
        # Check for skill trigger (Phase 10)
        skill_result = await self._check_skill_trigger(job)
        if skill_result:
            return skill_result
        
        # Persist user message to memory
        await self._persist_user_message(job)

        messages = await self._build_initial_context(job)
        tools = self._get_tools_for_context(job)
        workspace_hint = (job.payload or {}).get("workspace_root") or (job.payload or {}).get("workspace_path")
        workspace_root = None
        if workspace_hint:
            try:
                workspace_root = Path(str(workspace_hint)).expanduser().resolve()
            except Exception:
                workspace_root = None
        execution_context = ToolExecutionContext(
            agent_id=job.payload.get("agent_id"),
            session_id=job.session_id,
            scheduler_job_id=(job.payload or {}).get("scheduler_job_id") or (job.payload or {}).get("job_id"),
            scheduler_run_id=(job.payload or {}).get("scheduler_run_id") or (job.payload or {}).get("run_id"),
            chat_id=job.chat_id,
            is_admin=bool(job.payload.get("is_admin", False)),
            tool_profile=str(job.payload.get("tool_profile", "balanced")),
            workspace_root=workspace_root,
            actor="agent_runtime",
            correlation_id=f"job-{job.job_id}",
            max_calls_per_message=3,
            timeout_sec=30.0,
            audit_log=self._audit_tool_event,
        )

        async def _model_call(loop_messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
            response = await self._call_ollama_with_retry(messages=loop_messages, tools=tools)
            native_calls = self._extract_tool_calls(response)
            return response.message.content or "", native_calls

        try:
            loop_result = await run_tool_loop(
                initial_messages=messages,
                model_call=_model_call,
                executor=self.tool_executor,
                execution_context=execution_context,
                max_tool_turns_per_request=self.max_tool_turns,
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

        final_content = loop_result.final_response or ""
        tool_events = loop_result.tool_events
        tool_call_count = len([item for item in tool_events if item.tool != "invalid"])

        if loop_result.turns >= self.max_tool_turns and "maximum tool execution turns" in final_content.lower():
            return AgentResult(
                ok=False,
                error="Maximum tool calls exceeded. Please simplify your request.",
                error_code="MAX_TURNS_EXCEEDED",
                tool_calls=tool_call_count,
                tool_results=[item.model_dump(exclude_none=True) for item in tool_events],
                metadata={"turns": loop_result.turns, "max_turns": self.max_tool_turns},
            )

        await self._persist_assistant_message(
            job=job,
            response=final_content,
            tool_calls=tool_call_count,
        )

        user_message = job.payload.get("text", "") or job.payload.get("message", "")
        session_id = job.session_id or f"chat:{job.chat_id}"
        thread_id = job.thread_id or await self._get_thread_id(job)

        if settings.AUTO_MEMORY_ENABLED and thread_id:
            await self._trigger_memory_extraction(
                session_id=session_id,
                thread_id=thread_id,
                user_message=user_message,
                assistant_message=final_content,
            )

        logger.info(
            f"Agent run completed: {job.job_id}",
            extra={
                "event": "agent_run_complete",
                "job_id": job.job_id,
                "turns": loop_result.turns,
                "response_length": len(final_content),
                "tool_calls": tool_call_count,
            }
        )

        return AgentResult(
            ok=True,
            response=final_content,
            tool_calls=tool_call_count,
            tool_results=[item.model_dump(exclude_none=True) for item in tool_events],
            metadata={"turns": loop_result.turns},
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
        
        # Get mode from job
        mode = job.payload.get("mode", "default")
        
        # Get soul config from job payload or global loader
        soul_config = job.payload.get("soul_config")
        if soul_config is None:
            # Try to get from global soul loader
            try:
                from app.soul import get_soul_loader
                soul_loader = get_soul_loader()
                soul_cfg = soul_loader.get_config()
                if soul_cfg:
                    # Convert to dict for context builder
                    soul_config = {
                        "core": soul_cfg.core,
                        "style": soul_cfg.style,
                        "goals": soul_cfg.goals.dict() if soul_cfg.goals else None,
                        "guardrails": soul_cfg.guardrails.dict() if soul_cfg.guardrails else None,
                        "modes": {k: v.dict() for k, v in soul_cfg.modes.items()} if soul_cfg.modes else {},
                    }
            except Exception:
                pass
        
        # Build context
        messages = self.context_builder.build_with_user_message(
            user_message=user_message,
            session_id=job.session_id,
            thread_id=job.thread_id,
            mode=mode,
            soul_config=soul_config,
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

    def _audit_tool_event(
        self,
        action: str,
        target: Optional[str],
        details: Optional[Dict[str, Any]],
        actor: str,
    ) -> None:
        payload = details or {}
        logger.info(
            "Tool audit event",
            extra={
                "event": action,
                "target": target,
                "actor": actor,
                "details": payload,
            },
        )

    async def _check_skill_trigger(self, job: Job) -> Optional[AgentResult]:
        """
        Check if the job triggers a skill and execute it.
        
        This is called at the start of agent processing to see if
        the message should be handled by a skill instead.
        
        Args:
            job: Job to check
            
        Returns:
            AgentResult if skill was triggered and executed, None otherwise
        """
        from app.skills import (
            get_skill_router,
            get_skill_engine,
        )
        
        # Get user message
        user_message = job.payload.get("text", "") or job.payload.get("message", "")
        if not user_message:
            return None
        
        # Route to check for skill triggers
        router = get_skill_router()
        route_result = router.route_intent(user_message)
        
        if not route_result:
            return None
        
        skill_name, params = route_result
        logger.info(
            f"Skill triggered: {skill_name}",
            extra={
                "event": "skill_triggered",
                "skill_name": skill_name,
                "params": params,
                "job_id": job.job_id,
            }
        )
        
        # Execute the skill
        engine = get_skill_engine()
        try:
            result = engine.execute_skill(skill_name, params)
            
            if result.success:
                # Convert skill result to agent result
                output = result.outputs.get("result", str(result.outputs))
                return AgentResult(
                    ok=True,
                    response=output,
                    tool_calls=0,
                )
            else:
                return AgentResult(
                    ok=False,
                    response="",
                    error=f"Skill error: {result.error}",
                    error_code="skill_error",
                    tool_calls=0,
                )
                
        except Exception as e:
            logger.error(f"Skill execution error: {e}", exc_info=True)
            return AgentResult(
                ok=False,
                response="",
                error=f"Skill execution failed: {str(e)}",
                error_code="skill_execution_error",
                tool_calls=0,
            )

    async def _persist_user_message(self, job: Job) -> None:
        """
        Persist user message to memory store.
        
        Args:
            job: Job containing the user message
        """
        try:
            memory_store = get_memory_store()
            thread_state = get_thread_state()
            
            # Get or create session/thread
            session_id = job.session_id or f"chat:{job.chat_id}"
            thread_id = job.thread_id
            
            if not thread_id:
                # Get current thread for session
                thread_id = thread_state.get_current_thread(session_id)
            
            if not thread_id:
                # Create new thread
                thread_id = thread_state.create_new_thread(
                    session_id=session_id,
                    metadata={"source": job.source, "chat_id": job.chat_id}
                )
            
            # Get user message
            user_message = job.payload.get("text", "") or job.payload.get("message", "")
            
            # Append message to thread
            memory_store.append_message(
                thread_id=thread_id,
                role="user",
                content=user_message,
                metadata={"job_id": job.job_id, "source": job.source}
            )
            
            logger.debug(
                f"Persisted user message for job: {job.job_id}",
                extra={
                    "event": "user_message_persisted",
                    "job_id": job.job_id,
                    "session_id": session_id,
                    "thread_id": thread_id,
                }
            )
        except Exception as e:
            # Don't fail the job if persistence fails
            logger.warning(
                f"Failed to persist user message: {e}",
                extra={"event": "user_message_persist_failed", "job_id": job.job_id}
            )
    
    async def _persist_assistant_message(
        self,
        job: Job,
        response: str,
        tool_calls: int = 0
    ) -> None:
        """
        Persist assistant response to memory store.
        
        Args:
            job: Job containing context
            response: Assistant response text
            tool_calls: Number of tool calls made
        """
        try:
            memory_store = get_memory_store()
            thread_state = get_thread_state()
            
            session_id = job.session_id or f"chat:{job.chat_id}"
            thread_id = job.thread_id or thread_state.get_current_thread(session_id)
            
            if thread_id:
                memory_store.append_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=response,
                    metadata={
                        "job_id": job.job_id,
                        "tool_calls": tool_calls,
                    }
                )
                
                logger.debug(
                    f"Persisted assistant message for job: {job.job_id}",
                    extra={
                        "event": "assistant_message_persisted",
                        "job_id": job.job_id,
                        "thread_id": thread_id,
                    }
                )
        except Exception as e:
            logger.warning(
                f"Failed to persist assistant message: {e}",
                extra={"event": "assistant_message_persist_failed", "job_id": job.job_id}
            )
    
    async def _get_thread_id(self, job: Job) -> Optional[str]:
        """
        Get thread ID for a job.
        
        Args:
            job: Job to get thread ID for
            
        Returns:
            Thread ID or None
        """
        try:
            thread_state = get_thread_state()
            session_id = job.session_id or f"chat:{job.chat_id}"
            
            if job.thread_id:
                return job.thread_id
            
            return thread_state.get_current_thread(session_id)
        except Exception:
            return None
    
    async def _trigger_memory_extraction(
        self,
        session_id: str,
        thread_id: str,
        user_message: str,
        assistant_message: str
    ) -> None:
        """
        Trigger memory extraction pipeline for conversation.
        
        Uses both deterministic rules and LLM-based extraction,
        with deduplication before storing.
        
        Args:
            session_id: Session ID
            thread_id: Thread ID
            user_message: User's message
            assistant_message: Assistant's response
        """
        try:
            extraction_rules = get_extraction_rules()
            memory_store = get_memory_store()
            
            # Combine conversation for analysis
            conversation = f"User: {user_message}\nAssistant: {assistant_message}"
            
            # Extract candidates using deterministic rules
            candidates = extraction_rules.extract_facts(conversation)
            
            # Classify and filter candidates
            classified = extraction_rules.classify_candidates(candidates)
            
            # Also try LLM-based extraction
            llm_candidates = await self._llm_memory_extraction(
                conversation=conversation,
                session_id=session_id,
            )
            
            # Merge candidates from both sources
            all_candidates = classified + llm_candidates
            
            # Store high-confidence memories with deduplication
            for candidate in all_candidates:
                if candidate.get("confidence", 0) >= settings.AUTO_MEMORY_CONFIDENCE_THRESHOLD:
                    content = candidate.get("content", "")
                    
                    if not content.strip():
                        continue
                    
                    # Check for duplicates
                    is_dup, dup_memory, _ = await self._check_memory_duplicate(
                        content=content,
                        scope=session_id,
                    )
                    
                    if is_dup and dup_memory:
                        logger.debug(
                            f"Skipping duplicate memory",
                            extra={
                                "event": "memory_duplicate_skipped",
                                "content_hash": hash(content),
                                "existing_id": dup_memory.id,
                            }
                        )
                        continue
                    
                    # Create memory (embedding will be generated automatically)
                    memory_store.create_memory(
                        memory_type=candidate.get("memory_type") or candidate.get("category", "note"),
                        content=content,
                        tags=candidate.get("tags", []),
                        scope=session_id,
                        confidence=candidate.get("confidence", 0.5),
                        metadata={
                            "thread_id": thread_id, 
                            "source": "auto_extraction",
                            "extraction_method": candidate.get("extraction_method", "rules"),
                        }
                    )
                    
                    logger.debug(
                        f"Created memory from extraction",
                        extra={
                            "event": "memory_created",
                            "memory_type": candidate.get("memory_type") or candidate.get("category"),
                            "confidence": candidate.get("confidence"),
                        }
                    )
        except Exception as e:
            logger.warning(
                f"Memory extraction failed: {e}",
                extra={"event": "memory_extraction_failed", "session_id": session_id}
            )
    
    async def _llm_memory_extraction(
        self,
        conversation: str,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract memories from conversation.
        
        Args:
            conversation: The conversation text
            session_id: Session ID for context
            
        Returns:
            List of memory candidate dictionaries
        """
        try:
            from app.memory.extractor_llm import get_llm_extractor
            
            extractor = get_llm_extractor()
            
            if not extractor.is_enabled:
                return []
            
            # Extract memory using LLM
            result = extractor.extract_memory(
                content=conversation,
                context={"session_id": session_id},
            )
            
            if result.get("memory_type"):
                return [{
                    "memory_type": result["memory_type"],
                    "content": result["content"],
                    "tags": result.get("tags", []),
                    "confidence": result.get("confidence", 0.5),
                    "extraction_method": "llm",
                }]
            
            return []
            
        except Exception as e:
            logger.debug(f"LLM memory extraction failed: {e}")
            return []
    
    async def _check_memory_duplicate(
        self,
        content: str,
        scope: str,
    ) -> Tuple[bool, Optional[Any], Optional[float]]:
        """
        Check if a memory is a duplicate.
        
        Args:
            content: Memory content to check
            scope: Memory scope
            
        Returns:
            Tuple of (is_duplicate, existing_memory, similarity_score)
        """
        try:
            from app.memory.dedupe import get_deduplicator
            
            deduplicator = get_deduplicator()
            
            is_dup, dup_memory, score = deduplicator.check_and_dedupe(
                content=content,
                scope=scope,
                auto_mark=False,
            )
            
            return (is_dup, dup_memory, score)
            
        except Exception as e:
            logger.debug(f"Duplicate check failed: {e}")
            return (False, None, None)


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
