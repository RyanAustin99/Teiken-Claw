"""
Context assembly for the Teiken Claw agent.

This module provides the ContextBuilder class for assembling
the conversation context from various sources.

Key Features:
    - System prompt assembly
    - Message history loading
    - Token budget management
    - Message truncation
"""

import logging
from typing import Any, Dict, List, Optional

from app.agent.prompts import build_tool_prompt
from app.agent.prompt_assembler import PromptAssembler, PromptBundle
from app.config.settings import settings
from app.memory.thread_state import ThreadState
from app.memory.memory_store_v15 import MemoryStoreV15
from app.persona.resolve import PersonaResolutionError, resolve_persona

logger = logging.getLogger(__name__)


# Default token limits
DEFAULT_MAX_TOKENS = 4096
DEFAULT_RESERVED_TOKENS = 512  # Reserved for response


class ContextBuilder:
    """
    Builds conversation context for the agent.
    
    Assembles messages from:
    - System prompt
    - Mode configuration
    - Recent message history
    - Tool definitions
    - Thread context (from memory system)
    - Relevant memories (from memory system)
    
    Attributes:
        max_tokens: Maximum tokens for context
        reserved_tokens: Tokens reserved for response
    """
    
    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reserved_tokens: int = DEFAULT_RESERVED_TOKENS,
        thread_state: Optional[ThreadState] = None,
        memory_store: Optional[MemoryStoreV15] = None,
    ):
        """
        Initialize the context builder.
        
        Args:
            max_tokens: Maximum tokens for context window
            reserved_tokens: Tokens to reserve for response
        """
        self.max_tokens = max_tokens
        self.reserved_tokens = reserved_tokens
        self._available_tokens = max_tokens - reserved_tokens
        self._thread_state = thread_state or ThreadState()
        self._memory_store = memory_store or MemoryStoreV15()
        self._context_max_messages = int(getattr(settings, "MEMORY_CONTEXT_MAX_MESSAGES", 20))
        self._context_max_items = int(getattr(settings, "MEMORY_CONTEXT_MAX_ITEMS", 20))
        self._prompt_assembler = PromptAssembler()
        self._last_prompt_bundle: Optional[PromptBundle] = None
        
        logger.debug(
            f"ContextBuilder initialized: max_tokens={max_tokens}, "
            f"reserved={reserved_tokens}, available={self._available_tokens}"
        )
    
    def build(
        self,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        mode: str = "default",
        soul_config: Optional[Dict[str, Any]] = None,
        tool_profile: str = "balanced",
        tools: Optional[List[Dict[str, Any]]] = None,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build the conversation context.
        
        Args:
            session_id: Session ID for context
            thread_id: Thread ID for context
            mode: Operating mode
            soul_config: Soul/personality configuration
            tools: Available tool schemas
            recent_messages: Recent message history
            
        Returns:
            List of messages for Ollama API
        """
        messages = []
        estimated_tokens = 0
        
        active_thread_pk: Optional[int] = None
        thread_messages: List[Dict[str, Any]] = []
        thread_context: Dict[str, Any] = {}

        # 1. Gather thread context if thread_id provided
        if thread_id:
            thread_context = self._get_thread_context(thread_id)
            if thread_context:
                active_thread_pk = thread_context.get("thread_pk")
                thread_messages = thread_context.get("messages", [])

        # 2. Gather relevant memories (thread-scoped only)
        relevant_memories: List[Dict[str, Any]] = []
        if active_thread_pk is not None:
            query = ""
            if recent_messages:
                tail = recent_messages[-1]
                query = str(tail.get("content", "") or "")
            relevant_memories = self._get_relevant_memories(active_thread_pk, query=query)

        # 3. Resolve persona refs and assemble deterministic system prompt.
        active_mode_ref = str(mode or "").strip() or thread_context.get("active_mode") or getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0")
        soul_ref = thread_context.get("active_soul") or getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")
        if isinstance(soul_config, dict):
            explicit_ref = soul_config.get("ref") or soul_config.get("soul_ref")
            if explicit_ref:
                soul_ref = str(explicit_ref)
        base_file_policy = {
            "max_read_bytes": int(getattr(settings, "FILES_MAX_READ_BYTES", 1_048_576)),
            "max_write_bytes": int(getattr(settings, "FILES_MAX_WRITE_BYTES", 262_144)),
            "allowed_extensions": list(getattr(settings, "FILES_ALLOWED_WRITE_EXTENSIONS", [".md", ".txt", ".json", ".yaml", ".yml", ".log"])),
        }
        try:
            resolved = resolve_persona(
                mode_ref=active_mode_ref,
                soul_ref=soul_ref,
                tool_profile=tool_profile,
                base_file_policy=base_file_policy,
            )
            tool_policy = {
                "allowed_tools": sorted(resolved.effective_allowed_tools) if resolved.effective_allowed_tools is not None else ["*"],
                "max_tool_turns": resolved.max_tool_turns,
            }
            self._last_prompt_bundle = self._prompt_assembler.assemble(
                resolved_soul_ref=resolved.resolved_soul_ref,
                resolved_mode_ref=resolved.resolved_mode_ref,
                soul_hash=resolved.soul.sha256,
                mode_hash=resolved.mode.sha256,
                soul_prompt=resolved.soul.definition.system_prompt,
                soul_principles=resolved.soul.definition.principles,
                mode_overlay_prompt=resolved.mode.definition.overlay_prompt,
                mode_output_requirements=resolved.mode.definition.output_shape.model_dump(mode="json"),
                memory_items=relevant_memories,
                transcript_messages=thread_messages,
                effective_tool_policy=tool_policy,
                effective_file_policy=resolved.effective_file_policy,
                platform_policy_version=str(getattr(settings, "APP_VERSION", "0.0.0")),
            )
            system_prompt = self._last_prompt_bundle.system_prompt
        except PersonaResolutionError as exc:
            logger.warning("Persona resolution failed: %s", exc.message)
            system_prompt = (
                "You are Teiken Claw.\n"
                f"Mode: {active_mode_ref}\n"
                "If persona resolution fails, remain direct and safe."
            )
            self._last_prompt_bundle = None

        if tools:
            tool_prompt = build_tool_prompt(tools)
            if tool_prompt:
                system_prompt = f"{system_prompt}\n\n{tool_prompt}"

        messages.append({"role": "system", "content": system_prompt})
        estimated_tokens += self._estimate_tokens(system_prompt)

        if thread_context:
            header = (
                f"THREAD: id={thread_context.get('thread_id')} "
                f"title={thread_context.get('title')!r} "
                f"memory_enabled={thread_context.get('memory_enabled')} "
                f"mode={thread_context.get('active_mode')} "
                f"soul={thread_context.get('active_soul') or 'default'}"
            )
            messages.append({"role": "system", "content": header})
            estimated_tokens += self._estimate_tokens(header)
            if self._last_prompt_bundle:
                fp = f"PROMPT_FINGERPRINT: {self._last_prompt_bundle.prompt_fingerprint}"
                messages.append({"role": "system", "content": fp})
                estimated_tokens += self._estimate_tokens(fp)

        if thread_messages:
            available_for_messages = self._available_tokens - estimated_tokens
            truncated_messages = self._truncate_messages(thread_messages, available_for_messages)
            messages.extend(truncated_messages)
        
        # 4. Add recent messages (placeholder - just use provided messages)
        if recent_messages:
            # Truncate if needed to fit budget
            available_for_messages = self._available_tokens - estimated_tokens
            truncated_messages = self._truncate_messages(
                recent_messages,
                available_for_messages,
            )
            messages.extend(truncated_messages)
        
        logger.debug(
            f"Built context with {len(messages)} messages",
            extra={
                "event": "context_built",
                "message_count": len(messages),
                "estimated_tokens": estimated_tokens,
            }
        )
        
        return messages
    
    def _get_thread_context(self, thread_id: str) -> Optional[Dict]:
        """Get thread context from memory system."""
        return self._thread_state.get_thread_context(thread_id, max_messages=self._context_max_messages)
    
    def _get_relevant_memories(
        self, 
        thread_pk: int,
        query: Optional[str] = None
    ) -> List[Dict]:
        """
        Get relevant memories from memory system.
        
        Uses hybrid retrieval to find memories relevant to the current context.
        
        Args:
            session_id: Session ID for context
            query: Optional query for semantic search
            
        Returns:
            List of memory dictionaries
        """
        try:
            memories = self._memory_store.list_memories(thread_id=thread_pk, limit=100, include_deleted=False)
            if not memories:
                return []

            query_terms = self._extract_terms(query or "")
            scored: List[tuple[float, Any]] = []
            for memory in memories:
                score = self._memory_match_score(query_terms, memory.category, memory.key, memory.value)
                scored.append((score, memory))
            scored.sort(key=lambda item: (item[0], item[1].updated_at, item[1].id), reverse=True)
            top = [item[1] for item in scored[: self._context_max_items]]
            return [
                {
                    "id": str(m.public_id),
                    "category": m.category,
                    "key": m.key,
                    "value": m.value,
                    "updated_at": str(m.updated_at),
                }
                for m in top
            ]
        except Exception as e:
            logger.debug(f"Failed to get relevant memories: {e}")
            return []

    def _extract_terms(self, text: str) -> set[str]:
        raw = (text or "").lower()
        return {token for token in raw.replace("\n", " ").split(" ") if len(token) > 2}

    def _memory_match_score(self, query_terms: set[str], category: str, key: str, value: str) -> float:
        if not query_terms:
            base = 0.01
        else:
            blob = f"{category} {key} {value}".lower()
            overlap = sum(1 for token in query_terms if token in blob)
            base = overlap / max(1, len(query_terms))
        if category in {"preference", "project_setting"}:
            base += 0.1
        return base
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Uses a simple heuristic: ~4 characters per token.
        
        Args:
            text: Text to estimate
            
        Returns:
            Estimated token count
        """
        # Simple heuristic: ~4 chars per token for English
        return len(text) // 4 + 1

    @property
    def last_prompt_bundle(self) -> Optional[PromptBundle]:
        return self._last_prompt_bundle
    
    def _truncate_messages(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Truncate messages to fit within token budget.
        
        Keeps the most recent messages that fit.
        
        Args:
            messages: Messages to truncate
            max_tokens: Maximum tokens allowed
            
        Returns:
            Truncated message list
        """
        if not messages:
            return []
        
        # Calculate token counts
        message_tokens = []
        total_tokens = 0
        
        for msg in messages:
            content = msg.get("content", "")
            tokens = self._estimate_tokens(content)
            message_tokens.append(tokens)
            total_tokens += tokens
        
        # If all fit, return as-is
        if total_tokens <= max_tokens:
            return messages
        
        # Keep most recent messages that fit
        result = []
        remaining_budget = max_tokens
        
        # Iterate in reverse (most recent first)
        for i in range(len(messages) - 1, -1, -1):
            tokens = message_tokens[i]
            if tokens <= remaining_budget:
                result.insert(0, messages[i])
                remaining_budget -= tokens
            else:
                # Can't fit more
                break
        
        if len(result) < len(messages):
            logger.info(
                f"Truncated messages: {len(messages)} -> {len(result)}",
                extra={
                    "event": "messages_truncated",
                    "original_count": len(messages),
                    "truncated_count": len(result),
                }
            )
        
        return result
    
    def build_with_user_message(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        mode: str = "default",
        soul_config: Optional[Dict[str, Any]] = None,
        tool_profile: str = "balanced",
        tools: Optional[List[Dict[str, Any]]] = None,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build context with a new user message appended.
        
        Args:
            user_message: New user message to add
            session_id: Session ID for context
            thread_id: Thread ID for context
            mode: Operating mode
            soul_config: Soul/personality configuration
            tools: Available tool schemas
            recent_messages: Recent message history
            
        Returns:
            List of messages for Ollama API including new user message
        """
        # Build base context
        messages = self.build(
            session_id=session_id,
            thread_id=thread_id,
            mode=mode,
            soul_config=soul_config,
            tool_profile=tool_profile,
            tools=tools,
            recent_messages=recent_messages,
        )
        
        # Append user message
        messages.append({
            "role": "user",
            "content": user_message,
        })
        
        return messages


def get_context_builder() -> ContextBuilder:
    """
    Get a ContextBuilder instance with default settings.
    
    Returns:
        ContextBuilder instance
    """
    max_tokens = getattr(settings, "OLLAMA_MAX_TOKENS", DEFAULT_MAX_TOKENS)
    return ContextBuilder(max_tokens=max_tokens)


__all__ = [
    "ContextBuilder",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RESERVED_TOKENS",
    "get_context_builder",
]
