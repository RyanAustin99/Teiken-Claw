"""
Memory operations tool for the Teiken Claw agent system.

This module provides memory management capabilities including:
- Storing new memories
- Searching memories
- Deleting memories
- Reviewing memories
- Pausing/resuming auto-memory

Key Features:
    - Integration with memory store
    - Permission checks for sensitive operations
    - Audit logging for all operations
    - Support for different memory types and scopes

Security Considerations:
    - Delete operations require admin privileges
    - All operations are logged for audit
    - Memory scope isolation between chats
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.memory.store import MemoryStore, get_memory_store
from app.memory.models import MemoryRecord

logger = logging.getLogger(__name__)

# Default search limit
DEFAULT_SEARCH_LIMIT = 10

# Maximum search limit
MAX_SEARCH_LIMIT = 50

# Memory types
MEMORY_TYPES = {
    "fact": "A factual piece of information",
    "preference": "User preference or setting",
    "context": "Contextual information for conversations",
    "instruction": "User instruction or directive",
    "note": "General note or observation",
}

# Memory scopes
MEMORY_SCOPES = {
    "global": "Available across all chats",
    "chat": "Specific to current chat",
    "session": "Specific to current session",
}


class MemoryTool(Tool):
    """
    Memory operations tool for managing agent memory.
    
    Provides capabilities for:
    - Storing new memories
    - Searching memories
    - Deleting memories
    - Reviewing memories
    - Pausing/resuming auto-memory
    
    Attributes:
        memory_store: The memory store instance
        auto_memory_enabled: Whether auto-memory is enabled
    """
    
    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
        memory_store: Optional[MemoryStore] = None,
        auto_memory_enabled: bool = True,
    ):
        """
        Initialize the memory tool.
        
        Args:
            policy: Tool policy configuration
            memory_store: Memory store instance (uses global if None)
            auto_memory_enabled: Whether auto-memory is enabled
        """
        super().__init__(policy)
        self._memory_store = memory_store or get_memory_store()
        self._auto_memory_enabled = auto_memory_enabled
        
        logger.debug(
            f"MemoryTool initialized with auto_memory={auto_memory_enabled}"
        )
    
    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "memory"
    
    @property
    def description(self) -> str:
        """Tool description for the AI model."""
        return (
            "Memory operations tool for managing persistent memories. "
            "Can store, search, review, and delete memories. "
            "Use this to remember important information about the user, "
            "their preferences, and context for future conversations."
        )
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        """Ollama-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "remember", "search", "forget",
                                "review", "pause", "resume"
                            ],
                            "description": "The memory action to perform"
                        },
                        "content": {
                            "type": "string",
                            "description": "Memory content (for remember action)"
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": list(MEMORY_TYPES.keys()),
                            "description": "Type of memory (default: fact)",
                            "default": "fact"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for the memory"
                        },
                        "scope": {
                            "type": "string",
                            "enum": list(MEMORY_SCOPES.keys()),
                            "description": "Memory scope (default: chat)",
                            "default": "chat"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (for search action)"
                        },
                        "memory_id": {
                            "type": "integer",
                            "description": "Memory ID (for forget action)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Offset for pagination (default: 0)",
                            "default": 0
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute a memory operation.
        
        Args:
            action: The action to perform
            content: Memory content (for remember)
            memory_type: Type of memory
            tags: Tags for the memory
            scope: Memory scope
            query: Search query (for search)
            memory_id: Memory ID (for forget)
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            ToolResult with the operation result
        """
        action = kwargs.get("action", "")
        
        # Get context from metadata
        chat_id = kwargs.get("_chat_id")
        is_admin = kwargs.get("_is_admin", False)
        
        # Audit log
        self._audit_log(action, kwargs, chat_id)
        
        try:
            if action == "remember":
                content = kwargs.get("content", "")
                memory_type = kwargs.get("memory_type", "fact")
                tags = kwargs.get("tags", [])
                scope = kwargs.get("scope", "chat")
                return await self._remember(content, memory_type, tags, scope, chat_id)
            
            elif action == "search":
                query = kwargs.get("query", "")
                scope = kwargs.get("scope", "chat")
                limit = min(kwargs.get("limit", DEFAULT_SEARCH_LIMIT), MAX_SEARCH_LIMIT)
                return await self._search(query, scope, limit, chat_id)
            
            elif action == "forget":
                memory_id = kwargs.get("memory_id")
                return await self._forget(memory_id, chat_id, is_admin)
            
            elif action == "review":
                limit = min(kwargs.get("limit", DEFAULT_SEARCH_LIMIT), MAX_SEARCH_LIMIT)
                offset = kwargs.get("offset", 0)
                return await self._review(limit, offset, chat_id)
            
            elif action == "pause":
                return await self._pause()
            
            elif action == "resume":
                return await self._resume()
            
            else:
                return ToolResult.error(
                    error_code="INVALID_ACTION",
                    error_message=f"Unknown action: {action}. Valid actions: remember, search, forget, review, pause, resume"
                )
        
        except Exception as e:
            logger.error(f"Memory tool execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Memory operation failed: {e}"
            )
    
    async def _remember(
        self,
        content: str,
        memory_type: str,
        tags: List[str],
        scope: str,
        chat_id: Optional[str],
    ) -> ToolResult:
        """
        Store a new memory.
        
        Args:
            content: Memory content
            memory_type: Type of memory
            tags: Tags for the memory
            scope: Memory scope
            chat_id: Chat ID for scope isolation
            
        Returns:
            ToolResult with stored memory info
        """
        if not content:
            return ToolResult.error(
                error_code="MISSING_CONTENT",
                error_message="Memory content is required"
            )
        
        # Validate memory type
        if memory_type not in MEMORY_TYPES:
            return ToolResult.error(
                error_code="INVALID_MEMORY_TYPE",
                error_message=f"Invalid memory type: {memory_type}. Valid types: {', '.join(MEMORY_TYPES.keys())}"
            )
        
        # Validate scope
        if scope not in MEMORY_SCOPES:
            return ToolResult.error(
                error_code="INVALID_SCOPE",
                error_message=f"Invalid scope: {scope}. Valid scopes: {', '.join(MEMORY_SCOPES.keys())}"
            )
        
        logger.info(f"Storing memory: {content[:50]}...")
        
        try:
            # Create memory record
            memory = self._memory_store.create_memory(
                content=content,
                memory_type=memory_type,
                tags=tags,
                scope=scope,
                chat_id=chat_id if scope != "global" else None,
            )
            
            return ToolResult.success(
                content=f"Memory stored successfully (ID: {memory.id})",
                metadata={
                    "memory_id": memory.id,
                    "memory_type": memory_type,
                    "scope": scope,
                    "tags": tags,
                    "action": "remember"
                }
            )
            
        except Exception as e:
            logger.error(f"Error storing memory: {e}", exc_info=True)
            return ToolResult.error(
                error_code="STORE_ERROR",
                error_message=f"Failed to store memory: {e}"
            )
    
    async def _search(
        self,
        query: str,
        scope: str,
        limit: int,
        chat_id: Optional[str],
    ) -> ToolResult:
        """
        Search memories.
        
        Args:
            query: Search query
            scope: Memory scope to search
            limit: Maximum results
            chat_id: Chat ID for scope isolation
            
        Returns:
            ToolResult with search results
        """
        if not query:
            return ToolResult.error(
                error_code="MISSING_QUERY",
                error_message="Search query is required"
            )
        
        logger.info(f"Searching memories: {query[:50]}...")
        
        try:
            # Search memories
            memories = self._memory_store.search_memories(
                query=query,
                scope=scope,
                chat_id=chat_id,
                limit=limit,
            )
            
            if not memories:
                return ToolResult.success(
                    content="No memories found matching your query.",
                    metadata={
                        "query": query,
                        "result_count": 0,
                        "action": "search"
                    }
                )
            
            # Format results
            formatted = self._format_search_results(memories)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "query": query,
                    "result_count": len(memories),
                    "action": "search"
                }
            )
            
        except Exception as e:
            logger.error(f"Error searching memories: {e}", exc_info=True)
            return ToolResult.error(
                error_code="SEARCH_ERROR",
                error_message=f"Failed to search memories: {e}"
            )
    
    async def _forget(
        self,
        memory_id: Optional[int],
        chat_id: Optional[str],
        is_admin: bool,
    ) -> ToolResult:
        """
        Delete a memory.
        
        Args:
            memory_id: Memory ID to delete
            chat_id: Chat ID for ownership check
            is_admin: Whether user is admin
            
        Returns:
            ToolResult with deletion status
        """
        if memory_id is None:
            return ToolResult.error(
                error_code="MISSING_MEMORY_ID",
                error_message="Memory ID is required"
            )
        
        # Get the memory first
        memory = self._memory_store.get_memory(memory_id)
        
        if not memory:
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Memory not found: {memory_id}"
            )
        
        # Check ownership (unless admin)
        if not is_admin and memory.chat_id and memory.chat_id != chat_id:
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to delete this memory"
            )
        
        logger.warning(f"Deleting memory: {memory_id}")
        
        try:
            success = self._memory_store.delete_memory(memory_id)
            
            if success:
                return ToolResult.success(
                    content=f"Memory {memory_id} deleted successfully.",
                    metadata={
                        "memory_id": memory_id,
                        "action": "forget"
                    }
                )
            else:
                return ToolResult.error(
                    error_code="DELETE_FAILED",
                    error_message=f"Failed to delete memory: {memory_id}"
                )
            
        except Exception as e:
            logger.error(f"Error deleting memory: {e}", exc_info=True)
            return ToolResult.error(
                error_code="DELETE_ERROR",
                error_message=f"Failed to delete memory: {e}"
            )
    
    async def _review(
        self,
        limit: int,
        offset: int,
        chat_id: Optional[str],
    ) -> ToolResult:
        """
        Review memories.
        
        Args:
            limit: Maximum results
            offset: Pagination offset
            chat_id: Chat ID for scope isolation
            
        Returns:
            ToolResult with memory list
        """
        logger.info(f"Reviewing memories for chat: {chat_id}")
        
        try:
            # Get memories
            memories = self._memory_store.list_memories(
                chat_id=chat_id,
                limit=limit,
                offset=offset,
            )
            
            # Get total count
            total = self._memory_store.count_memories(chat_id=chat_id)
            
            if not memories:
                return ToolResult.success(
                    content="No memories found.",
                    metadata={
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "action": "review"
                    }
                )
            
            # Format results
            formatted = self._format_memory_list(memories, total, offset, limit)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "total": total,
                    "result_count": len(memories),
                    "limit": limit,
                    "offset": offset,
                    "action": "review"
                }
            )
            
        except Exception as e:
            logger.error(f"Error reviewing memories: {e}", exc_info=True)
            return ToolResult.error(
                error_code="REVIEW_ERROR",
                error_message=f"Failed to review memories: {e}"
            )
    
    async def _pause(self) -> ToolResult:
        """
        Pause auto-memory.
        
        Returns:
            ToolResult with status
        """
        self._auto_memory_enabled = False
        logger.info("Auto-memory paused")
        
        return ToolResult.success(
            content="Auto-memory has been paused. New memories will not be automatically created.",
            metadata={"action": "pause", "auto_memory_enabled": False}
        )
    
    async def _resume(self) -> ToolResult:
        """
        Resume auto-memory.
        
        Returns:
            ToolResult with status
        """
        self._auto_memory_enabled = True
        logger.info("Auto-memory resumed")
        
        return ToolResult.success(
            content="Auto-memory has been resumed. New memories will be automatically created when appropriate.",
            metadata={"action": "resume", "auto_memory_enabled": True}
        )
    
    def _format_search_results(self, memories: List[MemoryRecord]) -> str:
        """Format search results for display."""
        lines = ["## Memory Search Results\n"]
        
        for memory in memories:
            lines.append(f"### Memory #{memory.id}")
            lines.append(f"**Type:** {memory.memory_type}")
            lines.append(f"**Scope:** {memory.scope}")
            if memory.tags:
                lines.append(f"**Tags:** {', '.join(memory.tags)}")
            lines.append(f"**Content:** {memory.content}")
            lines.append(f"**Created:** {memory.created_at.isoformat() if memory.created_at else 'N/A'}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_memory_list(
        self,
        memories: List[MemoryRecord],
        total: int,
        offset: int,
        limit: int
    ) -> str:
        """Format memory list for display."""
        lines = [f"## Memory Review ({total} total)\n"]
        
        if offset > 0:
            lines.append(f"*Showing results {offset + 1}-{offset + len(memories)} of {total}*\n")
        else:
            lines.append(f"*Showing {len(memories)} of {total}*\n")
        
        for memory in memories:
            lines.append(f"### Memory #{memory.id}")
            lines.append(f"**Type:** {memory.memory_type}")
            lines.append(f"**Content:** {memory.content[:200]}{'...' if len(memory.content) > 200 else ''}")
            lines.append("")
        
        if offset + limit < total:
            lines.append(f"*Use offset={offset + limit} to see more results.*")
        
        return "\n".join(lines)
    
    def _audit_log(self, action: str, kwargs: Dict, chat_id: Optional[str]) -> None:
        """
        Log an audit entry for a memory operation.
        
        Args:
            action: The action being performed
            kwargs: Operation arguments
            chat_id: Chat ID
        """
        # Redact sensitive information
        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            if key == "content" and value:
                safe_kwargs[key] = str(value)[:50] + "..." if len(str(value)) > 50 else value
            else:
                safe_kwargs[key] = value
        
        logger.info(
            f"Memory operation: {action}",
            extra={
                "event": "memory_operation",
                "action": action,
                "chat_id": chat_id,
                "kwargs": safe_kwargs,
            }
        )


__all__ = ["MemoryTool"]
