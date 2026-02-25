"""
Tests for Exec Tool.

This module tests the ExecTool class for:
- PowerShell command execution
- Python code execution
- Command allowlist enforcement
- Security hardening
"""

import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from app.tools.exec_tool import (
    ExecTool,
    ExecutionMode,
    SAFE_POWERSHELL_COMMANDS,
    EXTENDED_POWERSHELL_COMMANDS,
    FORBIDDEN_COMMANDS,
)
from app.tools.base import ToolPolicy


class TestExecTool:
    """Tests for ExecTool class."""
    
    def test_init_default(self):
        """Test initialization with default settings."""
        tool = ExecTool()
        assert tool.name == "exec"
        assert tool._mode == ExecutionMode.SAFE
        assert tool._timeout_sec == 60.0
        assert tool.policy.admin_only  # Default is admin only
    
    def test_init_custom(self):
        """Test initialization with custom settings."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=30.0,
        )
        tool = ExecTool(
            policy=policy,
            mode=ExecutionMode.EXTENDED,
            timeout_sec=30.0,
        )
        assert tool._mode == ExecutionMode.EXTENDED
        assert tool._timeout_sec == 30.0
    
    def test_name_property(self):
        """Test name property."""
        tool = ExecTool()
        assert tool.name == "exec"
    
    def test_description_property(self):
        """Test description property."""
        tool = ExecTool()
        assert "exec" in tool.description.lower()
        assert "powershell" in tool.description.lower()
    
    def test_json_schema(self):
        """Test JSON schema structure."""
        tool = ExecTool()
        schema = tool.json_schema
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "exec"
        assert "action" in schema["function"]["parameters"]["properties"]
        assert "command" in schema["function"]["parameters"]["properties"]
        assert "code" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_execute_missing_action(self):
        """Test execute with missing action."""
        tool = ExecTool()
        result = await tool.execute()
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_execute_invalid_action(self):
        """Test execute with invalid action."""
        tool = ExecTool()
        result = await tool.execute(action="invalid")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_disabled_mode(self):
        """Test that disabled mode blocks execution."""
        tool = ExecTool(mode=ExecutionMode.DISABLED)
        result = await tool.execute(action="powershell", command="Get-Process")
        assert not result.ok
        assert "DISABLED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_powershell_missing_command(self):
        """Test PowerShell with missing command."""
        tool = ExecTool()
        result = await tool.execute(action="powershell")
        assert not result.ok
        assert "MISSING_COMMAND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_python_missing_code(self):
        """Test Python with missing code."""
        tool = ExecTool()
        result = await tool.execute(action="python")
        assert not result.ok
        assert "MISSING_CODE" in result.error_code


class TestExecToolAllowlist:
    """Tests for command allowlist enforcement."""
    
    def test_safe_commands_defined(self):
        """Test that safe commands are defined."""
        assert "Get-Process" in SAFE_POWERSHELL_COMMANDS
        assert "Get-ChildItem" in SAFE_POWERSHELL_COMMANDS
        assert "Get-Content" in SAFE_POWERSHELL_COMMANDS
    
    def test_extended_commands_defined(self):
        """Test that extended commands are defined."""
        assert "New-Item" in EXTENDED_POWERSHELL_COMMANDS
        assert "Remove-Item" in EXTENDED_POWERSHELL_COMMANDS
    
    def test_forbidden_commands_defined(self):
        """Test that forbidden commands are defined."""
        assert "Invoke-Expression" in FORBIDDEN_COMMANDS
        assert "Set-ExecutionPolicy" in FORBIDDEN_COMMANDS
    
    def test_validate_safe_command(self):
        """Test validation of safe command."""
        tool = ExecTool(mode=ExecutionMode.SAFE)
        result = tool._validate_powershell_command("Get-Process", ExecutionMode.SAFE)
        assert result["valid"]
    
    def test_validate_forbidden_command(self):
        """Test validation rejects forbidden command."""
        tool = ExecTool()
        result = tool._validate_powershell_command(
            "Invoke-Expression 'test'",
            ExecutionMode.SAFE
        )
        assert not result["valid"]
        assert "Forbidden" in result["reason"]
    
    def test_validate_shell_chaining(self):
        """Test validation rejects shell chaining."""
        tool = ExecTool()
        result = tool._validate_powershell_command(
            "Get-Process | Select-Object Name",
            ExecutionMode.SAFE
        )
        assert not result["valid"]
        assert "chaining" in result["reason"].lower()
    
    def test_validate_extended_command_in_safe_mode(self):
        """Test that extended commands fail in safe mode."""
        tool = ExecTool(mode=ExecutionMode.SAFE)
        result = tool._validate_powershell_command(
            "Remove-Item test.txt",
            ExecutionMode.SAFE
        )
        assert not result["valid"]
        assert "allowlist" in result["reason"].lower()
    
    def test_validate_extended_command_in_extended_mode(self):
        """Test that extended commands pass in extended mode."""
        tool = ExecTool(mode=ExecutionMode.EXTENDED)
        result = tool._validate_powershell_command(
            "Remove-Item test.txt",
            ExecutionMode.EXTENDED
        )
        assert result["valid"]


class TestExecToolPythonValidation:
    """Tests for Python code validation."""
    
    def test_validate_safe_python(self):
        """Test validation of safe Python code."""
        tool = ExecTool()
        result = tool._validate_python_code("print('Hello')")
        assert result["valid"]
    
    def test_validate_dangerous_import_os(self):
        """Test validation rejects os import."""
        tool = ExecTool()
        result = tool._validate_python_code("import os")
        assert not result["valid"]
        assert "os module" in result["reason"]
    
    def test_validate_dangerous_import_subprocess(self):
        """Test validation rejects subprocess import."""
        tool = ExecTool()
        result = tool._validate_python_code("import subprocess")
        assert not result["valid"]
    
    def test_validate_dangerous_eval(self):
        """Test validation rejects eval."""
        tool = ExecTool()
        result = tool._validate_python_code("eval('test')")
        assert not result["valid"]
    
    def test_validate_dangerous_exec(self):
        """Test validation rejects exec."""
        tool = ExecTool()
        result = tool._validate_python_code("exec('test')")
        assert not result["valid"]
    
    def test_validate_dangerous_open(self):
        """Test validation rejects open."""
        tool = ExecTool()
        result = tool._validate_python_code("open('file.txt')")
        assert not result["valid"]


class TestExecToolEnvironment:
    """Tests for environment sanitization."""
    
    def test_get_safe_environment(self):
        """Test that safe environment is created."""
        tool = ExecTool()
        env = tool._get_safe_environment()
        
        # Should have some environment variables
        assert len(env) > 0
        
        # Should not have protected variables
        for key in env:
            key_upper = key.upper()
            assert "SECRET" not in key_upper
            assert "PASSWORD" not in key_upper
            assert "TOKEN" not in key_upper
    
    def test_protected_env_vars_not_exposed(self):
        """Test that protected env vars are not exposed."""
        tool = ExecTool()
        
        # Set a protected env var
        import os
        os.environ["TEST_SECRET_KEY"] = "secret_value"
        
        try:
            env = tool._get_safe_environment()
            assert "TEST_SECRET_KEY" not in env
        finally:
            del os.environ["TEST_SECRET_KEY"]


class TestExecToolOutput:
    """Tests for output handling."""
    
    def test_truncate_output_short(self):
        """Test truncation of short output."""
        tool = ExecTool()
        output = "Short output"
        result = tool._truncate_output(output)
        assert result == output
    
    def test_truncate_output_long(self):
        """Test truncation of long output."""
        tool = ExecTool()
        output = "x" * 15000
        result = tool._truncate_output(output)
        assert len(result) < len(output)
        assert "truncated" in result.lower()
    
    def test_format_command_result(self):
        """Test command result formatting."""
        tool = ExecTool()
        result = tool._format_command_result(
            "Get-Process",
            "Process output",
            "",
            0
        )
        assert "Get-Process" in result
        assert "Process output" in result
        assert "0" in result
    
    def test_format_code_result(self):
        """Test code result formatting."""
        tool = ExecTool()
        result = tool._format_code_result(
            "print('test')",
            "test\n",
            "",
            0
        )
        assert "test" in result
        assert "0" in result


class TestExecToolPolicy:
    """Tests for ExecTool policy enforcement."""
    
    def test_default_admin_only(self):
        """Test that default policy is admin only."""
        tool = ExecTool()
        assert tool.policy.admin_only
    
    def test_custom_policy(self):
        """Test custom policy application."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=30.0,
        )
        tool = ExecTool(policy=policy)
        
        assert not tool.policy.admin_only
        assert tool.policy.timeout_sec == 30.0
    
    def test_to_ollama_tool(self):
        """Test conversion to Ollama tool format."""
        tool = ExecTool()
        ollama_tool = tool.to_ollama_tool()
        
        assert ollama_tool == tool.json_schema


class TestExecutionMode:
    """Tests for ExecutionMode enum."""
    
    def test_mode_values(self):
        """Test execution mode values."""
        assert ExecutionMode.SAFE.value == "safe"
        assert ExecutionMode.EXTENDED.value == "extended"
        assert ExecutionMode.DISABLED.value == "disabled"
    
    def test_mode_from_string(self):
        """Test creating mode from string."""
        assert ExecutionMode("safe") == ExecutionMode.SAFE
        assert ExecutionMode("extended") == ExecutionMode.EXTENDED
        assert ExecutionMode("disabled") == ExecutionMode.DISABLED
