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

from app.agent.prompts import build_system_prompt, build_tool_prompt
from app.config.settings import settings
from app.memory.thread_state import ThreadState
from app.memory.store import MemoryStore

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
        self._thread_state = ThreadState()
        self._memory_store = MemoryStore()
        
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
        
        # 1. Build system prompt
        system_prompt = build_system_prompt(mode=mode, soul_config=soul_config)
        
        # Add tool descriptions if provided
        if tools:
            tool_prompt = build_tool_prompt(tools)
            if tool_prompt:
                system_prompt = f"{system_prompt}\n\n{tool_prompt}"
        
        messages.append({
            "role": "system",
            "content": system_prompt,
        })
        estimated_tokens += self._estimate_tokens(system_prompt)
        
        # 2. Add thread context if thread_id provided
        if thread_id:
            thread_context = self._get_thread_context(thread_id)
            if thread_context:
                # Add thread summary as system message
                if thread_context.get("summary"):
                    messages.append({
                        "role": "system",
                        "content": f"Thread Summary: {thread_context['summary']}",
                    })
                    estimated_tokens += self._estimate_tokens(thread_context["summary"])
                
                # Add recent messages from thread
                thread_messages = thread_context.get("messages", [])
                if thread_messages:
                    # Truncate if needed to fit budget
                    available_for_messages = self._available_tokens - estimated_tokens
                    truncated_messages = self._truncate_messages(
                        thread_messages,
                        available_for_messages,
                    )
                    messages.extend(truncated_messages)
        
        # 3. Add relevant memories
        if session_id:
            relevant_memories = self._get_relevant_memories(session_id)
            if relevant_memories:
                memory_content = "\n\n".join([
                    f"Memory: {memory['content']}" 
                    for memory in relevant_memories
                ])
                messages.append({
                    "role": "system",
                    "content": memory_content,
                })
                estimated_tokens += self._estimate_tokens(memory_content)
        
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
        try:
            thread_id_int = int(thread_id)
            return self._thread_state.get_thread_context(thread_id_int)
        except (ValueError, TypeError):
            return None
    
    def _get_relevant_memories(
        self, 
        session_id: str, 
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
            # Use hybrid retrieval if available
            from app.memory.retrieval import get_retriever
            retriever = get_retriever()
            
            # Build query from recent context if not provided
            if not query:
                # Get recent messages to build context
                recent = self._memory_store.get_recent_messages(limit=5, chat_id=session_id)
                if recent:
                    query = " ".join([m.content for m in recent if m.content])
            
            if query:
                # Use hybrid retrieval
                results = retriever.retrieve(
                    query=query,
                    scope="user",
                    limit=5,
                )
                
                return [
                    {
                        "content": r["content"],
                        "type": r["memory_type"],
                        "confidence": r["confidence"],
                        "score": r["combined_score"],
                    }
                    for r in results
                ]
            
            # Fallback to recent memories
            memories = self._memory_store.list_memories(limit=5)
            return [{"content": m.content, "type": m.memory_type} for m in memories]
            
        except Exception as e:
            logger.debug(f"Failed to get relevant memories: {e}")
            return []
    
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
