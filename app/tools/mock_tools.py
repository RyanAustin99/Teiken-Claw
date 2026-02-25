"""
Mock tools for development and testing.

This module provides simple mock tools that can be used for testing
the agent runtime without requiring external dependencies.

Key Features:
    - EchoTool - echoes input back
    - TimeTool - returns current time
    - StatusTool - returns system status
"""

import asyncio
import platform
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from app.tools.base import Tool, ToolResult, ToolPolicy


class EchoTool(Tool):
    """
    Simple echo tool for testing.
    
    Echoes the input message back to the user.
    Useful for testing the tool-calling loop.
    """
    
    @property
    def name(self) -> str:
        return "echo"
    
    @property
    def description(self) -> str:
        return "Echo the input message back. Use this to test tool functionality."
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo the input message back.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The message to echo back",
                        },
                        "prefix": {
                            "type": "string",
                            "description": "Optional prefix to add to the message",
                            "default": "",
                        },
                    },
                    "required": ["message"],
                },
            },
        }
    
    async def execute(self, message: str, prefix: str = "") -> ToolResult:
        """Echo the message back."""
        result = f"{prefix}{message}" if prefix else message
        return ToolResult.success(
            content=result,
            metadata={"original_message": message, "prefix": prefix},
        )


class TimeTool(Tool):
    """
    Time tool for testing.
    
    Returns the current time in various formats.
    """
    
    @property
    def name(self) -> str:
        return "time"
    
    @property
    def description(self) -> str:
        return "Get the current time. Returns time in ISO format by default."
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "time",
                "description": "Get the current time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "Time format: 'iso', 'unix', or 'readable'",
                            "enum": ["iso", "unix", "readable"],
                            "default": "iso",
                        },
                    },
                },
            },
        }
    
    async def execute(self, format: str = "iso") -> ToolResult:
        """Return the current time."""
        now = datetime.utcnow()
        
        if format == "unix":
            content = str(int(now.timestamp()))
        elif format == "readable":
            content = now.strftime("%A, %B %d, %Y at %I:%M %p UTC")
        else:  # iso
            content = now.isoformat()
        
        return ToolResult.success(
            content=content,
            metadata={"format": format, "timestamp": now.isoformat()},
        )


class StatusTool(Tool):
    """
    System status tool for testing.
    
    Returns information about the system and runtime environment.
    """
    
    @property
    def name(self) -> str:
        return "status"
    
    @property
    def description(self) -> str:
        return "Get the current system status including platform and runtime info."
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "status",
                "description": "Get system status and runtime information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detailed": {
                            "type": "boolean",
                            "description": "Whether to include detailed information",
                            "default": False,
                        },
                    },
                },
            },
        }
    
    async def execute(self, detailed: bool = False) -> ToolResult:
        """Return system status."""
        lines = [
            "System Status",
            "=============",
            f"Platform: {platform.system()} {platform.release()}",
            f"Python: {sys.version.split()[0]}",
            f"Time: {datetime.utcnow().isoformat()}Z",
        ]
        
        if detailed:
            lines.extend([
                "",
                "Detailed Information",
                "-------------------",
                f"Machine: {platform.machine()}",
                f"Processor: {platform.processor()}",
                f"Node: {platform.node()}",
            ])
        
        content = "\n".join(lines)
        
        return ToolResult.success(
            content=content,
            metadata={
                "platform": platform.system(),
                "python_version": sys.version.split()[0],
                "detailed": detailed,
            },
        )


class DelayTool(Tool):
    """
    Delay tool for testing timeouts.
    
    Waits for a specified duration before returning.
    Useful for testing timeout handling.
    """
    
    def __init__(self, policy: Optional[ToolPolicy] = None):
        super().__init__(policy or ToolPolicy(timeout_sec=5.0))
    
    @property
    def name(self) -> str:
        return "delay"
    
    @property
    def description(self) -> str:
        return "Wait for a specified number of seconds. Use for testing timeouts."
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "delay",
                "description": "Wait for a specified duration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {
                            "type": "number",
                            "description": "Number of seconds to wait",
                            "minimum": 0.1,
                            "maximum": 10.0,
                        },
                    },
                    "required": ["seconds"],
                },
            },
        }
    
    async def execute(self, seconds: float) -> ToolResult:
        """Wait for the specified duration."""
        await asyncio.sleep(seconds)
        return ToolResult.success(
            content=f"Waited {seconds} seconds",
            metadata={"wait_seconds": seconds},
        )


class ErrorTool(Tool):
    """
    Error tool for testing error handling.
    
    Always returns an error result.
    Useful for testing error handling in the agent loop.
    """
    
    @property
    def name(self) -> str:
        return "error"
    
    @property
    def description(self) -> str:
        return "Always returns an error. Use for testing error handling."
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "error",
                "description": "Return an error result for testing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "error_type": {
                            "type": "string",
                            "description": "Type of error to simulate",
                            "enum": ["validation", "execution", "timeout"],
                            "default": "execution",
                        },
                    },
                },
            },
        }
    
    async def execute(self, error_type: str = "execution") -> ToolResult:
        """Return an error result."""
        error_messages = {
            "validation": "Validation failed: invalid input",
            "execution": "Execution failed: internal error",
            "timeout": "Operation timed out",
        }
        
        return ToolResult.error(
            error_code=error_type.upper(),
            error_message=error_messages.get(error_type, "Unknown error"),
            metadata={"error_type": error_type},
        )


def register_mock_tools(registry) -> None:
    """
    Register all mock tools with a registry.
    
    Args:
        registry: ToolRegistry instance to register tools with
    """
    registry.register(EchoTool())
    registry.register(TimeTool())
    registry.register(StatusTool())
    registry.register(DelayTool())
    registry.register(ErrorTool())


__all__ = [
    "EchoTool",
    "TimeTool",
    "StatusTool",
    "DelayTool",
    "ErrorTool",
    "register_mock_tools",
]
