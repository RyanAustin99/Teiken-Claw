"""
Tools package for Teiken Claw.

This package provides the tool system for the AI agent, including:
- Base tool interface and result types
- Tool registry for managing tools
- Policy checking and validation
- Mock tools for development and testing
- Production tools: Web, Files, Exec, Memory, Scheduler
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
from app.tools.protocol import (
    ToolCall,
    ToolResultEnvelope,
    ParsedToolCalls,
    extract_tool_calls,
    extract_tool_results,
    render_tool_result,
)
from app.tools.executor import (
    ToolExecutionContext,
    ToolExecutor,
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

# Production tools (Phase 8)
from app.tools.web_tool import WebTool
from app.tools.files_tool import (
    FilesTool,
    FilesExistsSubtool,
    FilesListSubtool,
    FilesReadSubtool,
    FilesWriteSubtool,
)
from app.tools.exec_tool import ExecTool, ExecutionMode
from app.tools.memory_tool import MemoryTool
from app.tools.scheduler_tool import SchedulerTool, JobStatus, TriggerType

# Phase 11: Sub-agent tool
from app.tools.subagent_tool import SubAgentTool


def register_production_tools(registry: ToolRegistry) -> None:
    """
    Register all production tools with the given registry.
    
    Args:
        registry: The tool registry to register tools with
    """
    from app.config.settings import settings
    from app.tools.base import ToolPolicy
    
    # Web tool
    web_policy = ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=getattr(settings, 'WEB_TIMEOUT_SEC', 30.0),
    )
    registry.register(WebTool(
        policy=web_policy,
        timeout_sec=getattr(settings, 'WEB_TIMEOUT_SEC', 30.0),
        max_response_size=getattr(settings, 'WEB_MAX_RESPONSE_SIZE', 1_000_000),
        allowed_domains=getattr(settings, 'WEB_ALLOWED_DOMAINS', []),
    ))
    
    # Files tool
    files_policy = ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=30.0,
    )
    registry.register(FilesTool(
        policy=files_policy,
        workspace_dir=getattr(settings, 'WORKSPACE_DIR', './data/workspace'),
        max_file_size=getattr(settings, 'FILES_MAX_READ_BYTES', getattr(settings, 'FILES_MAX_SIZE', 10_000_000)),
    ))
    registry.register(FilesWriteSubtool(policy=files_policy, max_file_size=getattr(settings, 'FILES_MAX_WRITE_BYTES', getattr(settings, 'FILES_MAX_SIZE', 10_000_000))))
    registry.register(FilesReadSubtool(policy=files_policy, max_file_size=getattr(settings, 'FILES_MAX_READ_BYTES', getattr(settings, 'FILES_MAX_SIZE', 10_000_000))))
    registry.register(FilesListSubtool(policy=files_policy, max_file_size=getattr(settings, 'FILES_MAX_READ_BYTES', getattr(settings, 'FILES_MAX_SIZE', 10_000_000))))
    registry.register(FilesExistsSubtool(policy=files_policy, max_file_size=getattr(settings, 'FILES_MAX_READ_BYTES', getattr(settings, 'FILES_MAX_SIZE', 10_000_000))))
    
    # Exec tool (admin only by default)
    exec_policy = ToolPolicy(
        enabled=True,
        admin_only=getattr(settings, 'EXEC_ADMIN_ONLY', True),
        timeout_sec=getattr(settings, 'EXEC_TIMEOUT_SEC', 60.0),
    )
    registry.register(ExecTool(
        policy=exec_policy,
        timeout_sec=getattr(settings, 'EXEC_TIMEOUT_SEC', 60.0),
    ))
    
    # Memory tool
    memory_policy = ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=30.0,
    )
    registry.register(MemoryTool(policy=memory_policy))
    
    # Scheduler tool
    scheduler_policy = ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=30.0,
    )
    registry.register(SchedulerTool(policy=scheduler_policy))
    
    # Sub-agent tool (Phase 11)
    subagent_policy = ToolPolicy(
        enabled=True,
        admin_only=False,
        timeout_sec=60.0,  # Sub-agents can take longer
    )
    registry.register(SubAgentTool(policy=subagent_policy))


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
    # Phase 17 protocol + executor
    "ToolCall",
    "ToolResultEnvelope",
    "ParsedToolCalls",
    "extract_tool_calls",
    "extract_tool_results",
    "render_tool_result",
    "ToolExecutionContext",
    "ToolExecutor",
    # Mock tools
    "EchoTool",
    "TimeTool",
    "StatusTool",
    "DelayTool",
    "ErrorTool",
    "register_mock_tools",
    # Production tools
    "WebTool",
    "FilesTool",
    "FilesWriteSubtool",
    "FilesReadSubtool",
    "FilesListSubtool",
    "FilesExistsSubtool",
    "ExecTool",
    "ExecutionMode",
    "MemoryTool",
    "SchedulerTool",
    "JobStatus",
    "TriggerType",
    # Phase 11: Sub-agent tool
    "SubAgentTool",
    # Registration helpers
    "register_production_tools",
]
