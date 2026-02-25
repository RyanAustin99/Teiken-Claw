"""
Tool registry for the Teiken Claw agent system.

This module provides a central registry for all available tools,
including registration, lookup, schema export, and permission checking.

Key Features:
    - ToolRegistry class for managing tools
    - Schema export for Ollama tool definitions
    - Permission checking based on policies
    - Tool execution with error handling
"""

import asyncio
import logging
from typing import Any, Optional, Dict, List

from app.tools.base import (
    Tool,
    ToolResult,
    ToolPolicy,
    ToolError,
    ToolTimeoutError,
    ToolDisabledError,
    ToolPermissionError,
)
from app.tools.policies import check_tool_permission
from app.tools.validators import validate_tool_args

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all available tools.
    
    Manages tool registration, lookup, schema export, and execution.
    
    Attributes:
        tools: Dictionary mapping tool names to Tool instances
    """
    
    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: Dict[str, Tool] = {}
        logger.debug("ToolRegistry initialized")
    
    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
            
        Raises:
            ValueError: If a tool with the same name already exists
        """
        if tool.name in self._tools:
            logger.warning(
                f"Overwriting existing tool: {tool.name}",
                extra={"event": "tool_overwrite", "tool_name": tool.name}
            )
        
        self._tools[tool.name] = tool
        logger.info(
            f"Registered tool: {tool.name}",
            extra={"event": "tool_registered", "tool_name": tool.name}
        )
    
    def unregister(self, name: str) -> bool:
        """
        Remove a tool from the registry.
        
        Args:
            name: Name of the tool to remove
            
        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(
                f"Unregistered tool: {name}",
                extra={"event": "tool_unregistered", "tool_name": name}
            )
            return True
        return False
    
    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.
        
        Args:
            name: Name of the tool
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)
    
    def get_all(self) -> List[Tool]:
        """
        Get all registered tools.
        
        Returns:
            List of all Tool instances
        """
        return list(self._tools.values())
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get Ollama-compatible schemas for all tools.
        
        Returns:
            List of tool schemas in Ollama format
        """
        return [tool.json_schema for tool in self._tools.values()]
    
    def get_allowed_tools(
        self,
        mode: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> List[Tool]:
        """
        Get tools allowed for the given context.
        
        Args:
            mode: Optional mode filter (not implemented yet)
            chat_id: Chat ID for permission checking
            is_admin: Whether the user is an admin
            
        Returns:
            List of allowed Tool instances
        """
        allowed = []
        for tool in self._tools.values():
            if check_tool_permission(tool, chat_id, is_admin):
                allowed.append(tool)
        return allowed
    
    def get_allowed_schemas(
        self,
        mode: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get Ollama schemas for allowed tools.
        
        Args:
            mode: Optional mode filter
            chat_id: Chat ID for permission checking
            is_admin: Whether the user is an admin
            
        Returns:
            List of allowed tool schemas
        """
        return [
            tool.json_schema
            for tool in self.get_allowed_tools(mode, chat_id, is_admin)
        ]
    
    async def execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a tool call from Ollama response.
        
        Args:
            tool_call: Tool call dict from Ollama with 'function' key
            context: Optional execution context (chat_id, is_admin, etc.)
            
        Returns:
            ToolResult from the tool execution
        """
        context = context or {}
        chat_id = context.get("chat_id")
        is_admin = context.get("is_admin", False)
        
        # Parse tool call
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = function.get("arguments", {})
        
        # Get tool
        tool = self.get(tool_name)
        if tool is None:
            logger.warning(
                f"Unknown tool called: {tool_name}",
                extra={"event": "unknown_tool", "tool_name": tool_name}
            )
            return ToolResult.error(
                error_code="UNKNOWN_TOOL",
                error_message=f"Unknown tool: {tool_name}",
            )
        
        # Check permissions
        if not check_tool_permission(tool, chat_id, is_admin):
            logger.warning(
                f"Permission denied for tool: {tool_name}",
                extra={
                    "event": "tool_permission_denied",
                    "tool_name": tool_name,
                    "chat_id": chat_id,
                }
            )
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message="You do not have permission to use this tool",
            )
        
        # Check if enabled
        if not tool.policy.enabled:
            logger.info(
                f"Tool is disabled: {tool_name}",
                extra={"event": "tool_disabled", "tool_name": tool_name}
            )
            return ToolResult.error(
                error_code="DISABLED",
                error_message="This tool is currently disabled",
            )
        
        # Validate arguments
        try:
            validated_args = validate_tool_args(tool, arguments)
        except Exception as e:
            logger.warning(
                f"Tool argument validation failed: {tool_name}",
                extra={
                    "event": "tool_validation_error",
                    "tool_name": tool_name,
                    "error": str(e),
                }
            )
            return ToolResult.error(
                error_code="INVALID_ARGUMENTS",
                error_message=f"Invalid arguments: {e}",
                metadata={"arguments": arguments},
            )
        
        # Execute with timeout
        timeout_sec = tool.policy.timeout_sec
        max_output_chars = tool.policy.max_output_chars
        
        try:
            logger.debug(
                f"Executing tool: {tool_name}",
                extra={
                    "event": "tool_execute_start",
                    "tool_name": tool_name,
                    "arguments": validated_args,
                }
            )
            
            result = await asyncio.wait_for(
                tool.execute(**validated_args),
                timeout=timeout_sec,
            )
            
            # Truncate output if needed
            if len(result.content) > max_output_chars:
                result = result.truncate_content(max_output_chars)
                logger.debug(
                    f"Tool output truncated: {tool_name}",
                    extra={
                        "event": "tool_output_truncated",
                        "tool_name": tool_name,
                        "max_chars": max_output_chars,
                    }
                )
            
            logger.info(
                f"Tool executed: {tool_name}",
                extra={
                    "event": "tool_execute_success",
                    "tool_name": tool_name,
                    "ok": result.ok,
                }
            )
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(
                f"Tool execution timed out: {tool_name}",
                extra={
                    "event": "tool_timeout",
                    "tool_name": tool_name,
                    "timeout_sec": timeout_sec,
                }
            )
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Tool execution timed out after {timeout_sec}s",
            )
            
        except Exception as e:
            logger.error(
                f"Tool execution failed: {tool_name}",
                extra={
                    "event": "tool_execute_error",
                    "tool_name": tool_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Tool execution failed: {e}",
            )
    
    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    def __repr__(self) -> str:
        return f"<ToolRegistry tools={len(self._tools)}>"


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.
    
    Creates a new registry if one doesn't exist.
    
    Returns:
        Global ToolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def set_tool_registry(registry: ToolRegistry) -> None:
    """
    Set the global tool registry instance.
    
    Args:
        registry: ToolRegistry instance to use globally
    """
    global _registry
    _registry = registry


def reset_tool_registry() -> None:
    """Reset the global tool registry to None."""
    global _registry
    _registry = None


__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "set_tool_registry",
    "reset_tool_registry",
]
