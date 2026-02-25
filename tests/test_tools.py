"""
Tests for the tools module.

This module tests:
- Tool base class
- ToolResult model
- ToolPolicy model
- ToolRegistry
- Tool validators
- Mock tools
"""

import asyncio
import pytest
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

from app.tools.base import (
    Tool,
    ToolResult,
    ToolPolicy,
    ToolError,
    ToolTimeoutError,
    ToolDisabledError,
    ToolPermissionError,
)
from app.tools.registry import ToolRegistry, get_tool_registry, reset_tool_registry
from app.tools.policies import (
    check_tool_permission,
    get_paused_behavior,
    get_default_policy,
    merge_policies,
    validate_policy,
)
from app.tools.validators import (
    validate_tool_args,
    coerce_value,
    safe_defaults,
)
from app.tools.mock_tools import (
    EchoTool,
    TimeTool,
    StatusTool,
    DelayTool,
    ErrorTool,
    register_mock_tools,
)


# =============================================================================
# Test Tools
# =============================================================================

class SimpleTestTool(Tool):
    """Simple test tool for testing."""
    
    @property
    def name(self) -> str:
        return "test_tool"
    
    @property
    def description(self) -> str:
        return "A simple test tool"
    
    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A simple test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "A message",
                        },
                        "count": {
                            "type": "integer",
                            "description": "A count",
                            "minimum": 1,
                            "maximum": 10,
                        },
                    },
                    "required": ["message"],
                },
            },
        }
    
    async def execute(self, message: str, count: int = 1) -> ToolResult:
        """Execute the test tool."""
        return ToolResult.success(
            content=f"Message: {message}, Count: {count}",
            metadata={"message": message, "count": count},
        )


# =============================================================================
# ToolResult Tests
# =============================================================================

class TestToolResult:
    """Tests for the ToolResult model."""
    
    def test_success_result(self):
        """Test creating a successful result."""
        result = ToolResult.success(content="Hello!")
        
        assert result.ok is True
        assert result.content == "Hello!"
        assert result.error_code is None
        assert result.error_message is None
    
    def test_error_result(self):
        """Test creating an error result."""
        result = ToolResult.error(
            error_code="TEST_ERROR",
            error_message="Test error occurred",
        )
        
        assert result.ok is False
        assert result.error_code == "TEST_ERROR"
        assert result.error_message == "Test error occurred"
    
    def test_truncate_content(self):
        """Test content truncation."""
        long_content = "x" * 1000
        result = ToolResult.success(content=long_content)
        
        truncated = result.truncate_content(100)
        
        assert len(truncated.content) <= 100
        assert truncated.metadata.get("truncated") is True
        assert truncated.metadata.get("original_length") == 1000
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = ToolResult.success(
            content="Done",
            metadata={"key": "value", "number": 42},
        )
        
        assert result.metadata["key"] == "value"
        assert result.metadata["number"] == 42


# =============================================================================
# ToolPolicy Tests
# =============================================================================

class TestToolPolicy:
    """Tests for the ToolPolicy model."""
    
    def test_default_policy(self):
        """Test default policy values."""
        policy = ToolPolicy()
        
        assert policy.enabled is True
        assert policy.admin_only is False
        assert policy.allowed_chats == []
        assert policy.timeout_sec == 30.0
        assert policy.max_output_chars == 10000
    
    def test_custom_policy(self):
        """Test custom policy values."""
        policy = ToolPolicy(
            enabled=False,
            admin_only=True,
            allowed_chats=["123", "456"],
            timeout_sec=60.0,
            max_output_chars=5000,
        )
        
        assert policy.enabled is False
        assert policy.admin_only is True
        assert policy.allowed_chats == ["123", "456"]
        assert policy.timeout_sec == 60.0
        assert policy.max_output_chars == 5000


# =============================================================================
# Tool Tests
# =============================================================================

class TestTool:
    """Tests for the Tool base class."""
    
    def test_tool_properties(self):
        """Test tool property accessors."""
        tool = SimpleTestTool()
        
        assert tool.name == "test_tool"
        assert tool.description == "A simple test tool"
        assert tool.json_schema["type"] == "function"
    
    @pytest.mark.asyncio
    async def test_tool_execute(self):
        """Test tool execution."""
        tool = SimpleTestTool()
        
        result = await tool.execute(message="Hello", count=3)
        
        assert result.ok is True
        assert "Hello" in result.content
        assert result.metadata["count"] == 3
    
    def test_tool_to_ollama_tool(self):
        """Test Ollama tool format conversion."""
        tool = SimpleTestTool()
        
        ollama_tool = tool.to_ollama_tool()
        
        assert ollama_tool == tool.json_schema


# =============================================================================
# ToolRegistry Tests
# =============================================================================

class TestToolRegistry:
    """Tests for the ToolRegistry class."""
    
    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = SimpleTestTool()
        
        registry.register(tool)
        
        assert "test_tool" in registry
        assert len(registry) == 1
    
    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = ToolRegistry()
        tool = SimpleTestTool()
        
        registry.register(tool)
        result = registry.unregister("test_tool")
        
        assert result is True
        assert "test_tool" not in registry
    
    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = ToolRegistry()
        tool = SimpleTestTool()
        registry.register(tool)
        
        retrieved = registry.get("test_tool")
        
        assert retrieved is tool
    
    def test_get_nonexistent_tool(self):
        """Test getting a nonexistent tool."""
        registry = ToolRegistry()
        
        result = registry.get("nonexistent")
        
        assert result is None
    
    def test_get_all_schemas(self):
        """Test getting all tool schemas."""
        registry = ToolRegistry()
        registry.register(SimpleTestTool())
        registry.register(EchoTool())
        
        schemas = registry.get_all_schemas()
        
        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)
    
    def test_get_allowed_tools(self):
        """Test getting allowed tools for a context."""
        registry = ToolRegistry()
        registry.register(SimpleTestTool())
        
        # Create an admin-only tool
        admin_tool = SimpleTestTool()
        admin_tool._policy = ToolPolicy(admin_only=True)
        admin_tool._name = "admin_tool"
        registry.register(admin_tool)
        
        # Non-admin should only see non-admin tools
        allowed = registry.get_allowed_tools(chat_id="123", is_admin=False)
        
        assert len(allowed) == 1
        assert allowed[0].name == "test_tool"
        
        # Admin should see all enabled tools
        allowed_admin = registry.get_allowed_tools(chat_id="123", is_admin=True)
        
        assert len(allowed_admin) == 2
    
    @pytest.mark.asyncio
    async def test_execute_tool_call(self):
        """Test executing a tool call."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        
        tool_call = {
            "function": {
                "name": "echo",
                "arguments": {"message": "Hello!"},
            }
        }
        
        result = await registry.execute_tool_call(tool_call)
        
        assert result.ok is True
        assert result.content == "Hello!"
    
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test executing an unknown tool."""
        registry = ToolRegistry()
        
        tool_call = {
            "function": {
                "name": "unknown",
                "arguments": {},
            }
        }
        
        result = await registry.execute_tool_call(tool_call)
        
        assert result.ok is False
        assert result.error_code == "UNKNOWN_TOOL"


# =============================================================================
# Policy Tests
# =============================================================================

class TestPolicies:
    """Tests for policy functions."""
    
    def test_check_tool_permission_enabled(self):
        """Test permission check for enabled tool."""
        tool = SimpleTestTool()
        
        assert check_tool_permission(tool, "123", False) is True
    
    def test_check_tool_permission_disabled(self):
        """Test permission check for disabled tool."""
        tool = SimpleTestTool()
        tool.policy = ToolPolicy(enabled=False)
        
        assert check_tool_permission(tool, "123", False) is False
    
    def test_check_tool_permission_admin_only(self):
        """Test permission check for admin-only tool."""
        tool = SimpleTestTool()
        tool.policy = ToolPolicy(admin_only=True)
        
        # Non-admin
        assert check_tool_permission(tool, "123", False) is False
        
        # Admin
        assert check_tool_permission(tool, "123", True) is True
    
    def test_check_tool_permission_allowed_chats(self):
        """Test permission check with allowed chats."""
        tool = SimpleTestTool()
        tool.policy = ToolPolicy(allowed_chats=["123", "456"])
        
        # Allowed chat
        assert check_tool_permission(tool, "123", False) is True
        
        # Disallowed chat
        assert check_tool_permission(tool, "789", False) is False
    
    def test_get_paused_behavior(self):
        """Test paused behavior message."""
        tool = SimpleTestTool()
        tool.policy = ToolPolicy(enabled=False)
        
        message = get_paused_behavior(tool)
        
        assert "disabled" in message.lower()
    
    def test_merge_policies(self):
        """Test merging policies."""
        base = ToolPolicy(timeout_sec=30.0)
        
        merged = merge_policies(base, {"timeout_sec": 60.0, "admin_only": True})
        
        assert merged.timeout_sec == 60.0
        assert merged.admin_only is True
    
    def test_validate_policy(self):
        """Test policy validation."""
        valid_policy = ToolPolicy(timeout_sec=30.0, max_output_chars=1000)
        errors = validate_policy(valid_policy)
        
        assert len(errors) == 0
        
        invalid_policy = ToolPolicy(timeout_sec=-1, max_output_chars=0)
        errors = validate_policy(invalid_policy)
        
        assert len(errors) == 2


# =============================================================================
# Validator Tests
# =============================================================================

class TestValidators:
    """Tests for tool validators."""
    
    def test_validate_tool_args_valid(self):
        """Test validating valid arguments."""
        tool = SimpleTestTool()
        
        args = {"message": "Hello", "count": 5}
        validated = validate_tool_args(tool, args)
        
        assert validated["message"] == "Hello"
        assert validated["count"] == 5
    
    def test_validate_tool_args_missing_required(self):
        """Test validating with missing required argument."""
        tool = SimpleTestTool()
        
        args = {"count": 5}
        
        with pytest.raises(ValueError) as exc_info:
            validate_tool_args(tool, args)
        
        assert "Missing required parameter" in str(exc_info.value)
    
    def test_validate_tool_args_coercion(self):
        """Test argument type coercion."""
        tool = SimpleTestTool()
        
        # String to integer coercion
        args = {"message": "Hello", "count": "5"}
        validated = validate_tool_args(tool, args)
        
        assert validated["count"] == 5
        assert isinstance(validated["count"], int)
    
    def test_coerce_value_string(self):
        """Test string coercion."""
        schema = {"type": "string", "minLength": 2, "maxLength": 10}
        
        assert coerce_value("hello", schema, "test") == "hello"
        
        with pytest.raises(ValueError):
            coerce_value("x", schema, "test")  # Too short
    
    def test_coerce_value_integer(self):
        """Test integer coercion."""
        schema = {"type": "integer", "minimum": 0, "maximum": 100}
        
        assert coerce_value(50, schema, "test") == 50
        assert coerce_value("50", schema, "test") == 50
        
        with pytest.raises(ValueError):
            coerce_value(150, schema, "test")  # Too high
    
    def test_coerce_value_boolean(self):
        """Test boolean coercion."""
        schema = {"type": "boolean"}
        
        assert coerce_value(True, schema, "test") is True
        assert coerce_value("true", schema, "test") is True
        assert coerce_value("yes", schema, "test") is True
        assert coerce_value(False, schema, "test") is False
        assert coerce_value("false", schema, "test") is False
    
    def test_safe_defaults(self):
        """Test safe defaults generation."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "unnamed"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
            },
        }
        
        defaults = safe_defaults(schema)
        
        assert defaults["name"] == "unnamed"
        assert defaults["count"] == 0
        assert defaults["enabled"] is False


# =============================================================================
# Mock Tool Tests
# =============================================================================

class TestMockTools:
    """Tests for mock tools."""
    
    @pytest.mark.asyncio
    async def test_echo_tool(self):
        """Test the echo tool."""
        tool = EchoTool()
        
        result = await tool.execute(message="Hello!")
        
        assert result.ok is True
        assert result.content == "Hello!"
    
    @pytest.mark.asyncio
    async def test_time_tool(self):
        """Test the time tool."""
        tool = TimeTool()
        
        result = await tool.execute(format="iso")
        
        assert result.ok is True
        assert "T" in result.content  # ISO format
    
    @pytest.mark.asyncio
    async def test_status_tool(self):
        """Test the status tool."""
        tool = StatusTool()
        
        result = await tool.execute(detailed=False)
        
        assert result.ok is True
        assert "System Status" in result.content
    
    @pytest.mark.asyncio
    async def test_delay_tool(self):
        """Test the delay tool."""
        tool = DelayTool()
        
        import time
        start = time.time()
        result = await tool.execute(seconds=0.1)
        elapsed = time.time() - start
        
        assert result.ok is True
        assert elapsed >= 0.1
    
    @pytest.mark.asyncio
    async def test_error_tool(self):
        """Test the error tool."""
        tool = ErrorTool()
        
        result = await tool.execute(error_type="execution")
        
        assert result.ok is False
        assert result.error_code == "EXECUTION"
    
    def test_register_mock_tools(self):
        """Test registering mock tools."""
        registry = ToolRegistry()
        
        register_mock_tools(registry)
        
        assert len(registry) == 5
        assert "echo" in registry
        assert "time" in registry
        assert "status" in registry
        assert "delay" in registry
        assert "error" in registry


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
