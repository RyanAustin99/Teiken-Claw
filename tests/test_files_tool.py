"""
Tests for Files Tool.

This module tests the FilesTool class for:
- Directory listing
- File reading
- File writing
- File searching
- File deletion
- Path traversal protection
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.files_tool import FilesTool, TEXT_EXTENSIONS, BINARY_EXTENSIONS
from app.tools.base import ToolPolicy


class TestFilesTool:
    """Tests for FilesTool class."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace for testing."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace
    
    @pytest.fixture
    def files_tool(self, temp_workspace):
        """Create a FilesTool with a temporary workspace."""
        return FilesTool(workspace_dir=str(temp_workspace))
    
    def test_init_default(self):
        """Test initialization with default settings."""
        tool = FilesTool()
        assert tool.name == "files"
        assert tool._max_file_size == 10_000_000
    
    def test_init_custom(self, temp_workspace):
        """Test initialization with custom settings."""
        policy = ToolPolicy(timeout_sec=60.0)
        tool = FilesTool(
            policy=policy,
            workspace_dir=str(temp_workspace),
            max_file_size=5_000_000,
        )
        assert tool._max_file_size == 5_000_000
        assert tool._workspace_root == temp_workspace.resolve()
    
    def test_name_property(self):
        """Test name property."""
        tool = FilesTool()
        assert tool.name == "files"
    
    def test_description_property(self):
        """Test description property."""
        tool = FilesTool()
        assert "file" in tool.description.lower()
        assert "workspace" in tool.description.lower()
    
    def test_json_schema(self):
        """Test JSON schema structure."""
        tool = FilesTool()
        schema = tool.json_schema
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "files"
        assert "action" in schema["function"]["parameters"]["properties"]
        assert "path" in schema["function"]["parameters"]["properties"]
    
    @pytest.mark.asyncio
    async def test_execute_missing_action(self, files_tool):
        """Test execute with missing action."""
        result = await files_tool.execute(path="test.txt")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_execute_invalid_action(self, files_tool):
        """Test execute with invalid action."""
        result = await files_tool.execute(action="invalid", path="test.txt")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_list_dir_success(self, files_tool, temp_workspace):
        """Test successful directory listing."""
        # Create test files
        (temp_workspace / "file1.txt").write_text("content1")
        (temp_workspace / "file2.txt").write_text("content2")
        (temp_workspace / "subdir").mkdir()
        
        result = await files_tool.execute(action="list_dir", path=".")
        
        assert result.ok
        assert "file1.txt" in result.content
        assert "file2.txt" in result.content
        assert "subdir" in result.content
    
    @pytest.mark.asyncio
    async def test_list_dir_not_found(self, files_tool):
        """Test listing non-existent directory."""
        result = await files_tool.execute(action="list_dir", path="nonexistent")
        assert not result.ok
        assert "NOT_FOUND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_list_dir_not_directory(self, files_tool, temp_workspace):
        """Test listing a file instead of directory."""
        (temp_workspace / "file.txt").write_text("content")
        
        result = await files_tool.execute(action="list_dir", path="file.txt")
        assert not result.ok
        assert "NOT_DIRECTORY" in result.error_code
    
    @pytest.mark.asyncio
    async def test_read_file_success(self, files_tool, temp_workspace):
        """Test successful file reading."""
        (temp_workspace / "test.txt").write_text("Hello, World!")
        
        result = await files_tool.execute(action="read_file", path="test.txt")
        
        assert result.ok
        assert "Hello, World!" in result.content
    
    @pytest.mark.asyncio
    async def test_read_file_not_found(self, files_tool):
        """Test reading non-existent file."""
        result = await files_tool.execute(action="read_file", path="nonexistent.txt")
        assert not result.ok
        assert "NOT_FOUND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_read_file_binary_rejected(self, files_tool, temp_workspace):
        """Test that binary files are rejected."""
        # Create a file with binary extension
        (temp_workspace / "test.exe").write_bytes(b"\x00\x01\x02\x03")
        
        result = await files_tool.execute(action="read_file", path="test.exe")
        assert not result.ok
        assert result.error_code == "ERR_BINARY_NOT_SUPPORTED"
        assert result.metadata["error"]["legacy_code"] == "BINARY_FILE"
    
    @pytest.mark.asyncio
    async def test_write_file_success(self, files_tool, temp_workspace):
        """Test successful file writing."""
        result = await files_tool.execute(
            action="write_file",
            path="new_file.txt",
            content="New content"
        )
        
        assert result.ok
        assert (temp_workspace / "new_file.txt").exists()
        assert (temp_workspace / "new_file.txt").read_text() == "New content"
    
    @pytest.mark.asyncio
    async def test_write_file_empty_content(self, files_tool):
        """Test writing empty content."""
        result = await files_tool.execute(
            action="write_file",
            path="empty.txt",
            content=""
        )
        assert not result.ok
        assert "EMPTY_CONTENT" in result.error_code
    
    @pytest.mark.asyncio
    async def test_write_file_creates_directories(self, files_tool, temp_workspace):
        """Test that write creates parent directories."""
        result = await files_tool.execute(
            action="write_file",
            path="subdir/nested/file.txt",
            content="Nested content"
        )
        
        assert result.ok
        assert (temp_workspace / "subdir" / "nested" / "file.txt").exists()
    
    @pytest.mark.asyncio
    async def test_write_file_binary_rejected(self, files_tool, temp_workspace):
        """Test that writing binary files is rejected."""
        result = await files_tool.execute(
            action="write_file",
            path="test.exe",
            content="binary content"
        )
        assert not result.ok
        assert result.error_code == "ERR_EXT_NOT_ALLOWED"
        assert result.metadata["error"]["legacy_code"] == "BINARY_FILE"
    
    @pytest.mark.asyncio
    async def test_search_files_by_name(self, files_tool, temp_workspace):
        """Test searching files by name."""
        (temp_workspace / "report.txt").write_text("content")
        (temp_workspace / "data.txt").write_text("content")
        (temp_workspace / "other.txt").write_text("content")
        
        result = await files_tool.execute(
            action="search_files",
            path=".",
            query="report"
        )
        
        assert result.ok
        assert "report.txt" in result.content
    
    @pytest.mark.asyncio
    async def test_search_files_by_content(self, files_tool, temp_workspace):
        """Test searching files by content."""
        (temp_workspace / "file1.txt").write_text("Hello World")
        (temp_workspace / "file2.txt").write_text("Goodbye World")
        (temp_workspace / "file3.txt").write_text("No match here")
        
        result = await files_tool.execute(
            action="search_files",
            path=".",
            query="Hello"
        )
        
        assert result.ok
        assert "file1.txt" in result.content
    
    @pytest.mark.asyncio
    async def test_search_files_missing_query(self, files_tool):
        """Test search with missing query."""
        result = await files_tool.execute(action="search_files", path=".")
        assert not result.ok
        assert "MISSING_QUERY" in result.error_code
    
    @pytest.mark.asyncio
    async def test_delete_file_success(self, files_tool, temp_workspace):
        """Test successful file deletion."""
        (temp_workspace / "to_delete.txt").write_text("delete me")
        
        result = await files_tool.execute(
            action="delete_file",
            path="to_delete.txt"
        )
        
        assert result.ok
        assert not (temp_workspace / "to_delete.txt").exists()
    
    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, files_tool):
        """Test deleting non-existent file."""
        result = await files_tool.execute(
            action="delete_file",
            path="nonexistent.txt"
        )
        assert not result.ok
        assert "NOT_FOUND" in result.error_code
    
    def test_is_text_file(self, files_tool):
        """Test _is_text_file helper."""
        assert files_tool._is_text_file(Path("test.txt"))
        assert files_tool._is_text_file(Path("test.md"))
        assert files_tool._is_text_file(Path("test.json"))
        assert not files_tool._is_text_file(Path("test.exe"))
        assert not files_tool._is_text_file(Path("test.png"))
    
    def test_format_size(self, files_tool):
        """Test _format_size helper."""
        assert "B" in files_tool._format_size(500)
        assert "KB" in files_tool._format_size(5000)
        assert "MB" in files_tool._format_size(5_000_000)


class TestFilesToolSecurity:
    """Tests for FilesTool security features."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace for testing."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace
    
    @pytest.fixture
    def files_tool(self, temp_workspace):
        """Create a FilesTool with a temporary workspace."""
        return FilesTool(workspace_dir=str(temp_workspace))
    
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, files_tool, temp_workspace):
        """Test that path traversal is blocked."""
        # Try to read a file outside workspace
        result = await files_tool.execute(
            action="read_file",
            path="../../../etc/passwd"
        )
        assert not result.ok
        assert "SECURITY" in result.error_code or "traversal" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_absolute_path_outside_workspace(self, files_tool):
        """Test that absolute paths outside workspace are blocked."""
        result = await files_tool.execute(
            action="read_file",
            path="/etc/passwd"
        )
        assert not result.ok
    
    @pytest.mark.asyncio
    async def test_null_byte_in_path(self, files_tool):
        """Test that null bytes in path are blocked."""
        result = await files_tool.execute(
            action="read_file",
            path="file\x00.txt"
        )
        assert not result.ok
    
    @pytest.mark.asyncio
    async def test_write_outside_workspace_blocked(self, files_tool):
        """Test that writing outside workspace is blocked."""
        result = await files_tool.execute(
            action="write_file",
            path="../../../tmp/malicious.txt",
            content="malicious"
        )
        assert not result.ok


class TestFilesToolPolicy:
    """Tests for FilesTool policy enforcement."""
    
    def test_policy_applied(self):
        """Test that policy is properly applied."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=45.0,
        )
        tool = FilesTool(policy=policy)
        
        assert tool.policy.enabled
        assert tool.policy.timeout_sec == 45.0
    
    def test_to_ollama_tool(self):
        """Test conversion to Ollama tool format."""
        tool = FilesTool()
        ollama_tool = tool.to_ollama_tool()
        
        assert ollama_tool == tool.json_schema
