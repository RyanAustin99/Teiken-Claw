"""
Base tool interface for the Teiken Claw agent system.

This module defines the abstract base class for all tools and the
associated data models for tool results and policies.

Key Features:
    - ToolResult Pydantic model for structured tool responses
    - Tool abstract base class for implementing tools
    - ToolPolicy model for access control and execution limits
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field


class ToolPolicy(BaseModel):
    """
    Policy configuration for a tool.
    
    Controls access, execution limits, and output constraints.
    
    Attributes:
        enabled: Whether the tool is enabled
        admin_only: Whether the tool requires admin privileges
        allowed_chats: List of chat IDs allowed to use this tool (empty = all)
        timeout_sec: Maximum execution time in seconds
        max_output_chars: Maximum characters in tool output
    """
    
    enabled: bool = Field(default=True, description="Whether the tool is enabled")
    admin_only: bool = Field(default=False, description="Whether admin privileges required")
    allowed_chats: list[str] = Field(
        default_factory=list,
        description="List of allowed chat IDs (empty = all allowed)"
    )
    timeout_sec: float = Field(default=30.0, description="Execution timeout in seconds")
    max_output_chars: int = Field(default=10000, description="Maximum output characters")
    
    class Config:
        extra = "forbid"


class ToolResult(BaseModel):
    """
    Result of a tool execution.
    
    Provides a structured response with success/failure status,
    content, and optional error information.
    
    Attributes:
        ok: Whether the tool execution succeeded
        content: The output content from the tool
        error_code: Optional error code if execution failed
        error_message: Optional human-readable error message
        metadata: Additional metadata about the execution
    """
    
    ok: bool = Field(description="Whether execution succeeded")
    content: str = Field(default="", description="Tool output content")
    error_code: Optional[str] = Field(default=None, description="Error code if failed")
    error_message: Optional[str] = Field(default=None, description="Human-readable error")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        extra = "forbid"
    
    @classmethod
    def success(cls, content: str, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """
        Create a successful tool result.
        
        Args:
            content: The output content
            metadata: Optional additional metadata
            
        Returns:
            ToolResult with ok=True
        """
        return cls(
            ok=True,
            content=content,
            metadata=metadata or {},
        )
    
    @classmethod
    def error(
        cls,
        error_code: str,
        error_message: str,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """
        Create an error tool result.
        
        Args:
            error_code: Machine-readable error code
            error_message: Human-readable error description
            content: Optional partial content
            metadata: Optional additional metadata
            
        Returns:
            ToolResult with ok=False
        """
        return cls(
            ok=False,
            content=content,
            error_code=error_code,
            error_message=error_message,
            metadata=metadata or {},
        )
    
    def truncate_content(self, max_chars: int) -> "ToolResult":
        """
        Return a new ToolResult with truncated content.
        
        Args:
            max_chars: Maximum characters to keep
            
        Returns:
            New ToolResult with truncated content
        """
        if len(self.content) <= max_chars:
            return self
        
        truncated = self.content[:max_chars]
        if not truncated.endswith("..."):
            truncated = truncated[:-3] + "..." if len(truncated) > 3 else truncated + "..."
        
        return ToolResult(
            ok=self.ok,
            content=truncated,
            error_code=self.error_code,
            error_message=self.error_message,
            metadata={
                **self.metadata,
                "truncated": True,
                "original_length": len(self.content),
            },
        )


class Tool(ABC):
    """
    Abstract base class for all tools.
    
    Tools are the primary way the AI agent interacts with external systems.
    Each tool must define its name, description, JSON schema, and execution logic.
    
    Attributes:
        name: Unique identifier for the tool (snake_case recommended)
        description: Human-readable description for the AI model
        json_schema: Ollama-compatible tool definition
        policy: Access control and execution limits
    """
    
    def __init__(self, policy: Optional[ToolPolicy] = None):
        """
        Initialize the tool with optional custom policy.
        
        Args:
            policy: Custom policy (uses default if None)
        """
        self._policy = policy or ToolPolicy()
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this tool.
        
        Should be in snake_case format.
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of what this tool does.
        
        This is shown to the AI model to help it decide when to use the tool.
        """
        pass
    
    @property
    @abstractmethod
    def json_schema(self) -> Dict[str, Any]:
        """
        Ollama-compatible tool definition.
        
        Returns a dictionary with the following structure:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "Tool description",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }
        """
        pass
    
    @property
    def policy(self) -> ToolPolicy:
        """
        Get the tool's policy configuration.
        """
        return self._policy
    
    @policy.setter
    def policy(self, value: ToolPolicy) -> None:
        """
        Set the tool's policy configuration.
        """
        self._policy = value
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool with the given arguments.
        
        Args:
            **kwargs: Tool-specific arguments validated against json_schema
            
        Returns:
            ToolResult with success/failure status and content
        """
        pass
    
    def to_ollama_tool(self) -> Dict[str, Any]:
        """
        Convert to Ollama tool format.
        
        Returns the json_schema directly for compatibility.
        """
        return self.json_schema
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


class ToolError(Exception):
    """
    Base exception for tool-related errors.
    
    Attributes:
        tool_name: Name of the tool that raised the error
        error_code: Machine-readable error code
        message: Human-readable error message
    """
    
    def __init__(
        self,
        tool_name: str,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.error_code = error_code
        self.message = message
        self.details = details or {}
    
    def to_result(self) -> ToolResult:
        """
        Convert the error to a ToolResult.
        """
        return ToolResult.error(
            error_code=self.error_code,
            error_message=self.message,
            metadata={"tool_name": self.tool_name, **self.details},
        )


class ToolTimeoutError(ToolError):
    """Raised when a tool execution times out."""
    
    def __init__(self, tool_name: str, timeout_sec: float):
        super().__init__(
            tool_name=tool_name,
            error_code="TIMEOUT",
            message=f"Tool execution timed out after {timeout_sec}s",
            details={"timeout_sec": timeout_sec},
        )


class ToolDisabledError(ToolError):
    """Raised when attempting to use a disabled tool."""
    
    def __init__(self, tool_name: str):
        super().__init__(
            tool_name=tool_name,
            error_code="DISABLED",
            message="This tool is currently disabled",
        )


class ToolPermissionError(ToolError):
    """Raised when a chat/user lacks permission to use a tool."""
    
    def __init__(self, tool_name: str, chat_id: Optional[str] = None):
        super().__init__(
            tool_name=tool_name,
            error_code="PERMISSION_DENIED",
            message="You do not have permission to use this tool",
            details={"chat_id": chat_id} if chat_id else {},
        )


__all__ = [
    "ToolPolicy",
    "ToolResult",
    "Tool",
    "ToolError",
    "ToolTimeoutError",
    "ToolDisabledError",
    "ToolPermissionError",
]
