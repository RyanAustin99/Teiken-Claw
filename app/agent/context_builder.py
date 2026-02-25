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
        
        # 2. Add recent messages (placeholder - just use provided messages)
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
