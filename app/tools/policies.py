"""
Tool policies for the Teiken Claw agent system.

This module provides policy checking and default configurations
for tool access control.

Key Features:
    - Permission checking based on policies
    - Default policy configurations
    - Paused behavior handling
"""

from typing import Optional, Dict, Any

from app.tools.base import Tool, ToolPolicy


# Default policies for common tool types
DEFAULT_TOOL_POLICIES: Dict[str, ToolPolicy] = {
    # Safe read-only tools
    "echo": ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=10.0,
        max_output_chars=5000,
    ),
    "time": ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=5.0,
        max_output_chars=500,
    ),
    "status": ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=10.0,
        max_output_chars=5000,
    ),
    # Admin-only tools (example)
    "admin_config": ToolPolicy(
        enabled=True,
        admin_only=True,
        timeout_sec=30.0,
        max_output_chars=10000,
    ),
    # Dangerous tools (disabled by default)
    "shell": ToolPolicy(
        enabled=False,
        admin_only=True,
        timeout_sec=60.0,
        max_output_chars=50000,
    ),
    "file_write": ToolPolicy(
        enabled=False,
        admin_only=True,
        timeout_sec=30.0,
        max_output_chars=10000,
    ),
}


def check_tool_permission(
    tool: Tool,
    chat_id: Optional[str] = None,
    is_admin: bool = False,
) -> bool:
    """
    Check if a tool can be used in the given context.
    
    Args:
        tool: Tool instance to check
        chat_id: Chat ID making the request
        is_admin: Whether the user is an admin
        
    Returns:
        True if the tool can be used, False otherwise
    """
    policy = tool.policy
    
    # Check if tool is enabled
    if not policy.enabled:
        return False
    
    # Check admin-only restriction
    if policy.admin_only and not is_admin:
        return False
    
    # Check allowed chats (empty list = all allowed)
    if policy.allowed_chats and chat_id not in policy.allowed_chats:
        return False
    
    return True


def get_paused_behavior(tool: Tool) -> str:
    """
    Get the behavior message when a tool is paused/disabled.
    
    Args:
        tool: Tool instance
        
    Returns:
        Human-readable message about the tool's paused state
    """
    policy = tool.policy
    
    if not policy.enabled:
        return f"The {tool.name} tool is currently disabled."
    
    if policy.admin_only:
        return f"The {tool.name} tool requires admin privileges."
    
    return f"The {tool.name} tool is not available in this context."


def get_default_policy(tool_name: str) -> ToolPolicy:
    """
    Get the default policy for a tool by name.
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        Default ToolPolicy (or a generic default if not found)
    """
    if tool_name in DEFAULT_TOOL_POLICIES:
        return DEFAULT_TOOL_POLICIES[tool_name].model_copy()
    
    # Generic default policy
    return ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=30.0,
        max_output_chars=10000,
    )


def merge_policies(
    base: ToolPolicy,
    override: Optional[Dict[str, Any]] = None,
) -> ToolPolicy:
    """
    Merge a base policy with override values.
    
    Args:
        base: Base ToolPolicy to start with
        override: Optional dictionary of values to override
        
    Returns:
        New ToolPolicy with merged values
    """
    if not override:
        return base.model_copy()
    
    base_dict = base.model_dump()
    base_dict.update(override)
    
    return ToolPolicy(**base_dict)


def validate_policy(policy: ToolPolicy) -> list[str]:
    """
    Validate a tool policy for consistency.
    
    Args:
        policy: ToolPolicy to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if policy.timeout_sec <= 0:
        errors.append("timeout_sec must be positive")
    
    if policy.max_output_chars <= 0:
        errors.append("max_output_chars must be positive")
    
    if policy.timeout_sec > 300:
        errors.append("timeout_sec should not exceed 300 seconds")
    
    return errors


__all__ = [
    "DEFAULT_TOOL_POLICIES",
    "check_tool_permission",
    "get_paused_behavior",
    "get_default_policy",
    "merge_policies",
    "validate_policy",
]
