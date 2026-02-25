"""
Tools package for Teiken Claw.

This package provides the tool system for the AI agent, including:
- Base tool interface and result types
- Tool registry for managing tools
- Policy checking and validation
- Mock tools for development and testing
"""

# Base classes and types
from app.tools.base import (
    Tool,
    ToolResult,
    ToolPolicy,
    ToolError,
    ToolTimeoutError,
    ToolDisabledError,
    ToolPermissionError,
)

# Registry
from app.tools.registry import (
    ToolRegistry,
    get_tool_registry,
    set_tool_registry,
    reset_tool_registry,
)

# Policies
from app.tools.policies import (
    DEFAULT_TOOL_POLICIES,
    check_tool_permission,
    get_paused_behavior,
    get_default_policy,
    merge_policies,
    validate_policy,
)

# Validators
from app.tools.validators import (
    validate_tool_args,
    coerce_value,
    safe_defaults,
)

# Mock tools
from app.tools.mock_tools import (
    EchoTool,
    TimeTool,
    StatusTool,
    DelayTool,
    ErrorTool,
    register_mock_tools,
)

__all__ = [
    # Base classes
    "Tool",
    "ToolResult",
    "ToolPolicy",
    "ToolError",
    "ToolTimeoutError",
    "ToolDisabledError",
    "ToolPermissionError",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "set_tool_registry",
    "reset_tool_registry",
    # Policies
    "DEFAULT_TOOL_POLICIES",
    "check_tool_permission",
    "get_paused_behavior",
    "get_default_policy",
    "merge_policies",
    "validate_policy",
    # Validators
    "validate_tool_args",
    "coerce_value",
    "safe_defaults",
    # Mock tools
    "EchoTool",
    "TimeTool",
    "StatusTool",
    "DelayTool",
    "ErrorTool",
    "register_mock_tools",
]
