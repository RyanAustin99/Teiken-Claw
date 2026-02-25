"""
Command execution tool for the Teiken Claw agent system.

This module provides secure command execution capabilities including:
- PowerShell command execution (Windows)
- Python code execution (sandboxed)

SECURITY WARNING: This tool is HIGH RISK and must be properly hardened.
All executions are logged and require admin privileges by default.

Key Features:
    - Command allowlist enforcement
    - No shell chaining unless explicitly allowed
    - Timeout and kill on overrun
    - Working directory sandbox
    - No secret environment exposure
    - Output truncation
    - Full audit logging
    - Admin-only by default

Security Considerations:
    - Only allowlisted commands can be executed
    - Shell metacharacters are blocked
    - Environment variables are sanitized
    - Execution timeout prevents runaway processes
    - All operations are logged for audit
"""

import os
import sys
import logging
import asyncio
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from datetime import datetime

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.security.sanitization import Sanitizer, SanitizationError

logger = logging.getLogger(__name__)

# Default timeout in seconds
DEFAULT_TIMEOUT_SEC = 60.0

# Maximum output characters
MAX_OUTPUT_CHARS = 10000

# Safe PowerShell commands allowlist
SAFE_POWERSHELL_COMMANDS: Set[str] = {
    # File system info (read-only)
    "Get-ChildItem", "ls", "dir",
    "Get-Content", "cat", "type",
    "Get-Location", "pwd",
    "Test-Path",
    "Get-Item",
    "Get-ItemProperty",
    
    # System info (read-only)
    "Get-Date",
    "Get-ComputerInfo",
    "Get-Process",
    "Get-Service",
    "Get-NetIPAddress",
    "Get-NetAdapter",
    
    # Text processing
    "Select-String", "sls",
    "Select-Object", "select",
    "Where-Object", "where", "?",
    "Sort-Object", "sort",
    "Measure-Object", "measure",
    "Group-Object", "group",
    "Format-Table", "ft",
    "Format-List", "fl",
    "ConvertTo-Json",
    "ConvertFrom-Json",
    
    # Help
    "Get-Help", "help",
    "Get-Command",
    "Get-Member",
}

# Extended commands (admin only)
EXTENDED_POWERSHELL_COMMANDS: Set[str] = {
    # File system write operations
    "New-Item", "ni",
    "Set-Content", "sc",
    "Add-Content", "ac",
    "Remove-Item", "ri", "rm", "del",
    "Move-Item", "mi", "mv",
    "Copy-Item", "ci", "cp",
    "Rename-Item", "rni",
    "New-Directory", "md", "mkdir",
    
    # Process management
    "Start-Process",
    "Stop-Process", "kill",
    
    # Service management
    "Start-Service",
    "Stop-Service",
    "Restart-Service",
}

# Dangerous commands that are never allowed
FORBIDDEN_COMMANDS: Set[str] = {
    # System modification
    "Set-ExecutionPolicy",
    "Invoke-Expression", "iex",
    "Invoke-WebRequest", "wget", "curl", "iwr",
    "Start-BitsTransfer",
    "Export-Clixml",
    "Import-Clixml",
    "ConvertTo-SecureString",
    "ConvertFrom-SecureString",
    
    # Registry
    "New-ItemProperty",
    "Remove-ItemProperty",
    "Set-ItemProperty",
    
    # User management
    "New-LocalUser",
    "Remove-LocalUser",
    "Set-LocalUser",
    "Add-LocalGroupMember",
    "Remove-LocalGroupMember",
    
    # Network
    "Invoke-Command",
    "Enter-PSSession",
    "New-PSSession",
    "Remove-PSSession",
    
    # Dangerous .NET calls
    "[System.IO.File]::",
    "[System.Diagnostics.Process]::",
    "[System.Reflection.Assembly]::",
}

# Environment variables to never expose
PROTECTED_ENV_VARS: Set[str] = {
    "API_KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIAL",
    "PRIVATE_KEY", "ACCESS_KEY", "AUTH",
    "TELEGRAM_BOT_TOKEN",
    "OLLAMA_API_KEY",
    "DATABASE_PASSWORD",
}


class ExecutionMode(str, Enum):
    """Execution mode for command restrictions."""
    SAFE = "safe"           # Strict allowlist only
    EXTENDED = "extended"   # Expanded allowlist (admin only)
    DISABLED = "disabled"   # Global pause


class ExecTool(Tool):
    """
    Command execution tool with security hardening.
    
    Provides capabilities for:
    - PowerShell command execution (Windows)
    - Python code execution (sandboxed)
    
    SECURITY: This tool is admin-only by default and requires
    proper configuration of allowlists.
    
    Attributes:
        mode: Current execution mode
        timeout_sec: Execution timeout in seconds
        working_dir: Working directory for executions
        allowlist: Set of allowed commands
    """
    
    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
        mode: ExecutionMode = ExecutionMode.SAFE,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        working_dir: Optional[str] = None,
        custom_allowlist: Optional[Set[str]] = None,
    ):
        """
        Initialize the exec tool.
        
        Args:
            policy: Tool policy configuration
            mode: Execution mode (safe, extended, disabled)
            timeout_sec: Execution timeout in seconds
            working_dir: Working directory for executions
            custom_allowlist: Additional commands to allow
        """
        # Default to admin-only
        if policy is None:
            policy = ToolPolicy(
                enabled=True,
                admin_only=True,
                timeout_sec=timeout_sec,
            )
        
        super().__init__(policy)
        self._mode = mode
        self._timeout_sec = timeout_sec
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
        self._custom_allowlist = custom_allowlist or set()
        self._sanitizer = Sanitizer(strict_mode=True)
        
        logger.info(
            f"ExecTool initialized with mode={mode}, timeout={timeout_sec}s",
            extra={"event": "exec_tool_init", "mode": mode}
        )
    
    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "exec"
    
    @property
    def description(self) -> str:
        """Tool description for the AI model."""
        return (
            "Command execution tool for running PowerShell commands and Python code. "
            "This tool is restricted to an allowlist of safe commands. "
            "Requires admin privileges by default. "
            "All executions are logged for security auditing."
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
                            "enum": ["powershell", "python"],
                            "description": "The execution action to perform"
                        },
                        "command": {
                            "type": "string",
                            "description": "PowerShell command to execute (for powershell action)"
                        },
                        "code": {
                            "type": "string",
                            "description": "Python code to execute (for python action)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["safe", "extended"],
                            "description": "Execution mode (default: safe)",
                            "default": "safe"
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute a command.
        
        Args:
            action: The action to perform (powershell, python)
            command: PowerShell command to execute
            code: Python code to execute
            mode: Execution mode (safe, extended)
            
        Returns:
            ToolResult with execution result
        """
        # Check if execution is disabled
        if self._mode == ExecutionMode.DISABLED:
            return ToolResult.error(
                error_code="EXEC_DISABLED",
                error_message="Command execution is currently disabled"
            )
        
        action = kwargs.get("action", "")
        mode_str = kwargs.get("mode", "safe")
        mode = ExecutionMode(mode_str) if mode_str in ["safe", "extended"] else ExecutionMode.SAFE
        
        # Extended mode requires admin privileges
        if mode == ExecutionMode.EXTENDED and self._mode != ExecutionMode.EXTENDED:
            return ToolResult.error(
                error_code="MODE_NOT_ALLOWED",
                error_message="Extended mode is not enabled"
            )
        
        # Audit log
        self._audit_log(action, kwargs)
        
        try:
            if action == "powershell":
                command = kwargs.get("command", "")
                return await self._execute_powershell(command, mode)
            
            elif action == "python":
                code = kwargs.get("code", "")
                return await self._execute_python(code)
            
            else:
                return ToolResult.error(
                    error_code="INVALID_ACTION",
                    error_message=f"Unknown action: {action}. Valid actions: powershell, python"
                )
        
        except asyncio.TimeoutError:
            logger.warning(f"Execution timeout for action: {action}")
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Execution timed out after {self._timeout_sec} seconds"
            )
        
        except Exception as e:
            logger.error(f"Exec tool execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Execution failed: {e}"
            )
    
    async def _execute_powershell(self, command: str, mode: ExecutionMode) -> ToolResult:
        """
        Execute a PowerShell command.
        
        Args:
            command: PowerShell command to execute
            mode: Execution mode
            
        Returns:
            ToolResult with command output
        """
        if not command:
            return ToolResult.error(
                error_code="MISSING_COMMAND",
                error_message="Command is required"
            )
        
        # Validate command
        validation_result = self._validate_powershell_command(command, mode)
        if not validation_result["valid"]:
            return ToolResult.error(
                error_code="COMMAND_NOT_ALLOWED",
                error_message=validation_result["reason"]
            )
        
        logger.info(f"Executing PowerShell command: {command[:100]}...")
        
        try:
            # Build PowerShell command
            ps_command = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Restricted",
                "-Command", command
            ]
            
            # Create sanitized environment
            env = self._get_safe_environment()
            
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                *ps_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._working_dir),
                env=env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout_sec
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise
            
            # Decode output
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            # Truncate output
            stdout_text = self._truncate_output(stdout_text)
            stderr_text = self._truncate_output(stderr_text)
            
            # Format result
            result_text = self._format_command_result(
                command, stdout_text, stderr_text, process.returncode
            )
            
            return ToolResult.success(
                content=result_text,
                metadata={
                    "command": command[:200],
                    "return_code": process.returncode,
                    "mode": mode.value,
                    "action": "powershell"
                }
            )
            
        except FileNotFoundError:
            return ToolResult.error(
                error_code="POWERSHELL_NOT_FOUND",
                error_message="PowerShell is not available on this system"
            )
        
        except Exception as e:
            logger.error(f"PowerShell execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Failed to execute command: {e}"
            )
    
    async def _execute_python(self, code: str) -> ToolResult:
        """
        Execute Python code in a sandboxed environment.
        
        Args:
            code: Python code to execute
            
        Returns:
            ToolResult with execution result
        """
        if not code:
            return ToolResult.error(
                error_code="MISSING_CODE",
                error_message="Python code is required"
            )
        
        # Validate code for dangerous patterns
        validation_result = self._validate_python_code(code)
        if not validation_result["valid"]:
            return ToolResult.error(
                error_code="CODE_NOT_ALLOWED",
                error_message=validation_result["reason"]
            )
        
        logger.info(f"Executing Python code: {code[:100]}...")
        
        # Create temporary file for execution
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="teiken_exec_")
            temp_file = Path(temp_dir) / "exec_code.py"
            
            # Wrap code in safe execution context
            wrapped_code = self._wrap_python_code(code)
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(wrapped_code)
            
            # Create sanitized environment
            env = self._get_safe_environment()
            
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(temp_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=temp_dir,
                env=env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout_sec
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise
            
            # Decode output
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            # Truncate output
            stdout_text = self._truncate_output(stdout_text)
            stderr_text = self._truncate_output(stderr_text)
            
            # Format result
            result_text = self._format_code_result(
                code, stdout_text, stderr_text, process.returncode
            )
            
            return ToolResult.success(
                content=result_text,
                metadata={
                    "code_length": len(code),
                    "return_code": process.returncode,
                    "action": "python"
                }
            )
            
        except Exception as e:
            logger.error(f"Python execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Failed to execute code: {e}"
            )
        
        finally:
            # Cleanup temp directory
            if temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp directory: {e}")
    
    def _validate_powershell_command(self, command: str, mode: ExecutionMode) -> Dict[str, Any]:
        """
        Validate a PowerShell command against the allowlist.
        
        Args:
            command: Command to validate
            mode: Execution mode
            
        Returns:
            Dict with 'valid' and optional 'reason'
        """
        # Check for forbidden commands
        command_upper = command.upper()
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden.upper() in command_upper:
                return {
                    "valid": False,
                    "reason": f"Forbidden command detected: {forbidden}"
                }
        
        # Check for shell chaining
        chaining_patterns = [";", "|", "&", "&&", "||", "`", "$(", "${"]
        for pattern in chaining_patterns:
            if pattern in command:
                return {
                    "valid": False,
                    "reason": f"Shell chaining not allowed: {pattern}"
                }
        
        # Extract base command
        command_stripped = command.strip()
        if not command_stripped:
            return {"valid": False, "reason": "Empty command"}
        
        # Get the first word (command name)
        parts = command_stripped.split()
        if not parts:
            return {"valid": False, "reason": "Empty command"}
        
        base_command = parts[0]
        
        # Build allowlist based on mode
        allowlist = SAFE_POWERSHELL_COMMANDS | self._custom_allowlist
        if mode == ExecutionMode.EXTENDED:
            allowlist = allowlist | EXTENDED_POWERSHELL_COMMANDS
        
        # Check if command is in allowlist
        if base_command not in allowlist:
            return {
                "valid": False,
                "reason": f"Command not in allowlist: {base_command}. Allowed commands: {', '.join(sorted(allowlist))}"
            }
        
        return {"valid": True}
    
    def _validate_python_code(self, code: str) -> Dict[str, Any]:
        """
        Validate Python code for dangerous patterns.
        
        Args:
            code: Python code to validate
            
        Returns:
            Dict with 'valid' and optional 'reason'
        """
        # Dangerous patterns to block
        dangerous_patterns = [
            ("import os", "os module import"),
            ("import sys", "sys module import"),
            ("import subprocess", "subprocess module import"),
            ("import shutil", "shutil module import"),
            ("import socket", "socket module import"),
            ("__import__", "__import__ function"),
            ("eval(", "eval function"),
            ("exec(", "exec function"),
            ("compile(", "compile function"),
            ("open(", "file open (use restricted_open)"),
            ("file(", "file function"),
            ("input(", "input function"),
            ("breakpoint(", "breakpoint function"),
            ("exit(", "exit function"),
            ("quit(", "quit function"),
        ]
        
        code_lower = code.lower()
        for pattern, description in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    "valid": False,
                    "reason": f"Dangerous pattern detected: {description}"
                }
        
        return {"valid": True}
    
    def _wrap_python_code(self, code: str) -> str:
        """
        Wrap Python code in a safe execution context.
        
        Args:
            code: Python code to wrap
            
        Returns:
            Wrapped code with safety restrictions
        """
        # Create a restricted builtins dict
        wrapper = '''
import sys
import traceback

# Restricted builtins
_safe_builtins = {
    'print': print,
    'len': len,
    'range': range,
    'enumerate': enumerate,
    'zip': zip,
    'map': map,
    'filter': filter,
    'sorted': sorted,
    'reversed': reversed,
    'sum': sum,
    'min': min,
    'max': max,
    'abs': abs,
    'round': round,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'list': list,
    'dict': dict,
    'set': set,
    'tuple': tuple,
    'type': type,
    'isinstance': isinstance,
    'hasattr': hasattr,
    'getattr': getattr,
    'True': True,
    'False': False,
    'None': None,
}

# Override builtins
__builtins__ = _safe_builtins

# Execute user code
try:
    exec("""
{code}
""", {{'__builtins__': _safe_builtins}})
except Exception as e:
    print(f"Error: {{e}}")
    traceback.print_exc()
'''
        return wrapper.format(code=code)
    
    def _get_safe_environment(self) -> Dict[str, str]:
        """
        Get a sanitized environment for command execution.
        
        Returns:
            Dict with safe environment variables
        """
        safe_env = {}
        
        for key, value in os.environ.items():
            # Skip protected variables
            key_upper = key.upper()
            is_protected = any(
                protected in key_upper
                for protected in PROTECTED_ENV_VARS
            )
            
            if is_protected:
                continue
            
            safe_env[key] = value
        
        return safe_env
    
    def _truncate_output(self, output: str) -> str:
        """Truncate output to maximum characters."""
        if len(output) <= MAX_OUTPUT_CHARS:
            return output
        
        return output[:MAX_OUTPUT_CHARS] + "\n\n... [Output truncated]"
    
    def _format_command_result(
        self,
        command: str,
        stdout: str,
        stderr: str,
        return_code: int
    ) -> str:
        """Format command execution result."""
        lines = [
            f"## PowerShell Execution Result",
            f"**Command:** `{command[:100]}{'...' if len(command) > 100 else ''}`",
            f"**Return Code:** {return_code}",
            "",
        ]
        
        if stdout:
            lines.append("### Output:")
            lines.append("```")
            lines.append(stdout)
            lines.append("```")
            lines.append("")
        
        if stderr:
            lines.append("### Errors:")
            lines.append("```")
            lines.append(stderr)
            lines.append("```")
        
        return "\n".join(lines)
    
    def _format_code_result(
        self,
        code: str,
        stdout: str,
        stderr: str,
        return_code: int
    ) -> str:
        """Format Python code execution result."""
        lines = [
            f"## Python Execution Result",
            f"**Return Code:** {return_code}",
            "",
        ]
        
        if stdout:
            lines.append("### Output:")
            lines.append("```")
            lines.append(stdout)
            lines.append("```")
            lines.append("")
        
        if stderr:
            lines.append("### Errors:")
            lines.append("```")
            lines.append(stderr)
            lines.append("```")
        
        return "\n".join(lines)
    
    def _audit_log(self, action: str, kwargs: Dict) -> None:
        """
        Log an audit entry for command execution.
        
        Args:
            action: The action being performed
            kwargs: Command arguments
        """
        # Redact sensitive information
        safe_kwargs = {}
        for key, value in kwargs.items():
            if key in ("command", "code"):
                safe_kwargs[key] = str(value)[:100] + "..." if len(str(value)) > 100 else value
            else:
                safe_kwargs[key] = value
        
        logger.info(
            f"Command execution: {action}",
            extra={
                "event": "command_execution",
                "action": action,
                "kwargs": safe_kwargs,
                "mode": self._mode.value,
            }
        )


__all__ = ["ExecTool", "ExecutionMode"]
