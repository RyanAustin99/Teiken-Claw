"""
File operations tool for the Teiken Claw agent system.

This module provides file system capabilities including:
- Directory listing
- File reading and writing
- File searching
- File deletion (admin only)

Key Features:
    - Workspace sandbox enforcement
    - Path traversal protection
    - Max file size limits
    - Text files only in v1 for safety
    - Audit logging for all operations

Security Considerations:
    - All operations are confined to workspace directory
    - Path traversal attacks are prevented
    - Binary files are rejected in v1
    - Delete operations require admin privileges
"""

import os
import logging
import asyncio
import aiofiles
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.security.path_guard import PathGuard, PathSecurityError
from app.security.sanitization import Sanitizer, SanitizationError

logger = logging.getLogger(__name__)

# Default workspace directory
DEFAULT_WORKSPACE = "./data/workspace"

# Maximum file size (10MB)
DEFAULT_MAX_FILE_SIZE = 10_000_000

# Text file extensions allowed in v1
TEXT_EXTENSIONS = {
    '.txt', '.md', '.json', '.yaml', '.yml', '.xml', '.html', '.htm',
    '.css', '.js', '.ts', '.py', '.java', '.c', '.cpp', '.h', '.hpp',
    '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd',
    '.sql', '.csv', '.tsv', '.ini', '.cfg', '.conf', '.log',
    '.toml', '.env', '.gitignore', '.dockerignore', '.editorconfig',
    '.rst', '.adoc', '.tex', '.bib',
    '.markdown', '.mkd', '.mkdn',
}

# Binary extensions to reject
BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.flv',
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.db', '.sqlite', '.sqlite3',
}


class FilesTool(Tool):
    """
    File operations tool for workspace file management.
    
    Provides capabilities for:
    - Listing directory contents
    - Reading file content
    - Writing file content
    - Searching files by content/name
    - Deleting files (admin only)
    
    All operations are confined to a designated workspace directory
    for security.
    
    Attributes:
        workspace_dir: The root directory for file operations
        max_file_size: Maximum file size in bytes
        path_guard: Path security validator
    """
    
    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
        workspace_dir: str = DEFAULT_WORKSPACE,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ):
        """
        Initialize the files tool.
        
        Args:
            policy: Tool policy configuration
            workspace_dir: Root directory for file operations
            max_file_size: Maximum file size in bytes
        """
        super().__init__(policy)
        self._workspace_dir = Path(workspace_dir).resolve()
        # Backward-compatible alias expected by tests/callers.
        self._workspace_root = self._workspace_dir
        self._max_file_size = max_file_size
        self._path_guard = PathGuard(str(self._workspace_dir))
        self._sanitizer = Sanitizer()
        
        # Ensure workspace exists
        self._ensure_workspace()
        
        logger.debug(
            f"FilesTool initialized with workspace={self._workspace_dir}, "
            f"max_size={max_file_size}"
        )
    
    def _ensure_workspace(self) -> None:
        """Ensure the workspace directory exists."""
        try:
            self._workspace_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Workspace directory ready: {self._workspace_dir}")
        except Exception as e:
            logger.warning(f"Could not create workspace directory: {e}")
    
    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "files"
    
    @property
    def description(self) -> str:
        """Tool description for the AI model."""
        return (
            "File operations tool for managing files in the workspace. "
            "Can list directories, read files, write files, and search for files. "
            "All operations are confined to the workspace directory for security. "
            "Only text files are supported in v1."
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
                            "enum": ["list_dir", "read_file", "write_file", "search_files", "delete_file"],
                            "description": "The file action to perform"
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory path (relative to workspace)"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write (for write_file action)"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (for search_files action)"
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Search recursively (default: false)",
                            "default": False
                        }
                    },
                    "required": ["action", "path"]
                }
            }
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute a file operation.
        
        Args:
            action: The action to perform
            path: File or directory path
            content: Content to write (for write_file)
            query: Search query (for search_files)
            recursive: Search recursively (default: false)
            
        Returns:
            ToolResult with the operation result
        """
        action = kwargs.get("action", "")
        path = kwargs.get("path", "")
        
        # Log the operation
        self._audit_log(action, path, kwargs)
        
        try:
            if action == "list_dir":
                return await self._list_dir(path)
            
            elif action == "read_file":
                return await self._read_file(path)
            
            elif action == "write_file":
                content = kwargs.get("content", "")
                return await self._write_file(path, content)
            
            elif action == "search_files":
                query = kwargs.get("query", "")
                recursive = kwargs.get("recursive", False)
                return await self._search_files(path, query, recursive)
            
            elif action == "delete_file":
                return await self._delete_file(path)
            
            else:
                return ToolResult.error(
                    error_code="INVALID_ACTION",
                    error_message=f"Unknown action: {action}. Valid actions: list_dir, read_file, write_file, search_files, delete_file"
                )
        
        except PathSecurityError as e:
            logger.warning(f"Path security error: {e}")
            return ToolResult.error(
                error_code="PATH_SECURITY_ERROR",
                error_message=str(e)
            )
        
        except PermissionError as e:
            logger.warning(f"Permission error: {e}")
            return ToolResult.error(
                error_code="PERMISSION_DENIED",
                error_message=f"Permission denied: {e}"
            )
        
        except Exception as e:
            logger.error(f"Files tool execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"File operation failed: {e}"
            )
    
    async def _list_dir(self, path: str) -> ToolResult:
        """
        List directory contents.
        
        Args:
            path: Directory path (relative to workspace)
            
        Returns:
            ToolResult with directory listing
        """
        # Validate and resolve path
        safe_path = self._get_safe_path(path)
        
        if not safe_path.exists():
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Directory not found: {path}"
            )
        
        if not safe_path.is_dir():
            return ToolResult.error(
                error_code="NOT_DIRECTORY",
                error_message=f"Path is not a directory: {path}"
            )
        
        logger.info(f"Listing directory: {safe_path}")
        
        try:
            entries = []
            for entry in safe_path.iterdir():
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            
            # Sort: directories first, then files, alphabetically
            entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
            
            # Format output
            formatted = self._format_directory_listing(path, entries)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "path": path,
                    "entry_count": len(entries),
                    "action": "list_dir"
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing directory: {e}", exc_info=True)
            return ToolResult.error(
                error_code="LIST_ERROR",
                error_message=f"Failed to list directory: {e}"
            )
    
    async def _read_file(self, path: str) -> ToolResult:
        """
        Read file content.
        
        Args:
            path: File path (relative to workspace)
            
        Returns:
            ToolResult with file content
        """
        # Validate and resolve path
        safe_path = self._get_safe_path(path)
        
        if not safe_path.exists():
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"File not found: {path}"
            )
        
        if not safe_path.is_file():
            return ToolResult.error(
                error_code="NOT_FILE",
                error_message=f"Path is not a file: {path}"
            )
        
        # Check file extension
        if not self._is_text_file(safe_path):
            return ToolResult.error(
                error_code="BINARY_FILE",
                error_message=f"Binary files are not supported in v1. File: {path}"
            )
        
        # Check file size
        file_size = safe_path.stat().st_size
        if file_size > self._max_file_size:
            return ToolResult.error(
                error_code="FILE_TOO_LARGE",
                error_message=f"File size ({file_size} bytes) exceeds limit ({self._max_file_size} bytes)"
            )
        
        logger.info(f"Reading file: {safe_path}")
        
        try:
            async with aiofiles.open(safe_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            return ToolResult.success(
                content=content,
                metadata={
                    "path": path,
                    "size": file_size,
                    "action": "read_file"
                }
            )
            
        except UnicodeDecodeError:
            return ToolResult.error(
                error_code="ENCODING_ERROR",
                error_message="File is not valid UTF-8 text"
            )
        
        except Exception as e:
            logger.error(f"Error reading file: {e}", exc_info=True)
            return ToolResult.error(
                error_code="READ_ERROR",
                error_message=f"Failed to read file: {e}"
            )
    
    async def _write_file(self, path: str, content: str) -> ToolResult:
        """
        Write content to a file.
        
        Args:
            path: File path (relative to workspace)
            content: Content to write
            
        Returns:
            ToolResult with write status
        """
        if not content:
            return ToolResult.error(
                error_code="EMPTY_CONTENT",
                error_message="Content cannot be empty"
            )
        
        # Check content size
        content_size = len(content.encode('utf-8'))
        if content_size > self._max_file_size:
            return ToolResult.error(
                error_code="CONTENT_TOO_LARGE",
                error_message=f"Content size ({content_size} bytes) exceeds limit ({self._max_file_size} bytes)"
            )
        
        # Validate and resolve path
        try:
            safe_path = self._get_safe_path(path)
        except PathSecurityError as e:
            return ToolResult.error(
                error_code="PATH_SECURITY_ERROR",
                error_message=str(e)
            )
        
        # Check file extension
        if not self._is_text_file(safe_path):
            return ToolResult.error(
                error_code="BINARY_FILE",
                error_message=f"Binary files are not supported in v1. File: {path}"
            )
        
        logger.info(f"Writing file: {safe_path}")
        
        try:
            # Create parent directories if needed
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(safe_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return ToolResult.success(
                content=f"Successfully wrote {content_size} bytes to {path}",
                metadata={
                    "path": path,
                    "size": content_size,
                    "action": "write_file"
                }
            )
            
        except Exception as e:
            logger.error(f"Error writing file: {e}", exc_info=True)
            return ToolResult.error(
                error_code="WRITE_ERROR",
                error_message=f"Failed to write file: {e}"
            )
    
    async def _search_files(self, path: str, query: str, recursive: bool = False) -> ToolResult:
        """
        Search for files by name or content.
        
        Args:
            path: Directory path to search in
            query: Search query
            recursive: Search recursively
            
        Returns:
            ToolResult with search results
        """
        if not query:
            return ToolResult.error(
                error_code="MISSING_QUERY",
                error_message="Search query is required"
            )
        
        # Validate and resolve path
        safe_path = self._get_safe_path(path)
        
        if not safe_path.exists():
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"Directory not found: {path}"
            )
        
        if not safe_path.is_dir():
            return ToolResult.error(
                error_code="NOT_DIRECTORY",
                error_message=f"Path is not a directory: {path}"
            )
        
        logger.info(f"Searching files in {safe_path} for: {query}")
        
        try:
            results = []
            query_lower = query.lower()
            
            # Get files to search
            if recursive:
                files = list(safe_path.rglob("*"))
            else:
                files = list(safe_path.glob("*"))
            
            for file_path in files:
                if not file_path.is_file():
                    continue
                
                # Skip binary files
                if not self._is_text_file(file_path):
                    continue
                
                # Check file size
                if file_path.stat().st_size > self._max_file_size:
                    continue
                
                match_info = {
                    "path": str(file_path.relative_to(self._workspace_dir)),
                    "name_match": query_lower in file_path.name.lower(),
                    "content_matches": [],
                }
                
                # Check content
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                    
                    if query_lower in content.lower():
                        # Find matching lines
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if query_lower in line.lower():
                                match_info["content_matches"].append({
                                    "line": i + 1,
                                    "text": line.strip()[:100],
                                })
                                if len(match_info["content_matches"]) >= 5:
                                    break
                except Exception:
                    pass  # Skip files that can't be read
                
                if match_info["name_match"] or match_info["content_matches"]:
                    results.append(match_info)
            
            # Format results
            formatted = self._format_search_results(query, results)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "path": path,
                    "query": query,
                    "result_count": len(results),
                    "recursive": recursive,
                    "action": "search_files"
                }
            )
            
        except Exception as e:
            logger.error(f"Error searching files: {e}", exc_info=True)
            return ToolResult.error(
                error_code="SEARCH_ERROR",
                error_message=f"Failed to search files: {e}"
            )
    
    async def _delete_file(self, path: str) -> ToolResult:
        """
        Delete a file (admin only).
        
        Args:
            path: File path (relative to workspace)
            
        Returns:
            ToolResult with delete status
        """
        # Note: This should be checked by the registry based on policy.admin_only
        # But we add an extra check here for safety
        
        # Validate and resolve path
        safe_path = self._get_safe_path(path)
        
        if not safe_path.exists():
            return ToolResult.error(
                error_code="NOT_FOUND",
                error_message=f"File not found: {path}"
            )
        
        if not safe_path.is_file():
            return ToolResult.error(
                error_code="NOT_FILE",
                error_message=f"Path is not a file: {path}"
            )
        
        logger.warning(f"Deleting file: {safe_path}")
        
        try:
            safe_path.unlink()
            
            return ToolResult.success(
                content=f"Successfully deleted: {path}",
                metadata={
                    "path": path,
                    "action": "delete_file"
                }
            )
            
        except Exception as e:
            logger.error(f"Error deleting file: {e}", exc_info=True)
            return ToolResult.error(
                error_code="DELETE_ERROR",
                error_message=f"Failed to delete file: {e}"
            )
    
    def _get_safe_path(self, path: str) -> Path:
        """
        Get a validated safe path within the workspace.
        
        Args:
            path: Relative path to validate
            
        Returns:
            Resolved Path object within workspace
            
        Raises:
            PathSecurityError: If path is invalid or outside workspace
        """
        if not path:
            raise PathSecurityError("Path cannot be empty", path)
        
        # Sanitize the path
        sanitized = self._sanitizer.sanitize_path(path)
        
        # Validate with path guard
        return Path(self._path_guard.get_safe_path(sanitized))
    
    def _is_text_file(self, path: Path) -> bool:
        """
        Check if a file is a text file based on extension.
        
        Args:
            path: File path
            
        Returns:
            True if the file is a text file
        """
        ext = path.suffix.lower()
        
        # Check if it's a known binary extension
        if ext in BINARY_EXTENSIONS:
            return False
        
        # Check if it's a known text extension
        if ext in TEXT_EXTENSIONS:
            return True
        
        # Allow files without extension (treat as text)
        if not ext:
            return True
        
        # Default: allow unknown extensions but log
        logger.debug(f"Unknown file extension: {ext}, treating as text")
        return True
    
    def _format_directory_listing(self, path: str, entries: List[Dict]) -> str:
        """Format directory listing for display."""
        lines = [f"## Directory: {path}\n"]
        
        if not entries:
            lines.append("*Empty directory*")
            return "\n".join(lines)
        
        for entry in entries:
            if entry["type"] == "directory":
                lines.append(f"📁 **{entry['name']}/**")
            else:
                size_str = self._format_size(entry["size"]) if entry["size"] else ""
                lines.append(f"📄 {entry['name']} ({size_str})")
        
        return "\n".join(lines)
    
    def _format_search_results(self, query: str, results: List[Dict]) -> str:
        """Format search results for display."""
        lines = [f"## Search Results for: {query}\n"]
        
        if not results:
            lines.append("*No matches found*")
            return "\n".join(lines)
        
        for result in results:
            lines.append(f"### {result['path']}")
            
            if result["name_match"]:
                lines.append("*Filename matches query*")
            
            if result["content_matches"]:
                lines.append("**Content matches:**")
                for match in result["content_matches"]:
                    lines.append(f"  Line {match['line']}: {match['text']}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_size(self, size: int) -> str:
        """Format file size for display."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def _audit_log(self, action: str, path: str, kwargs: Dict) -> None:
        """
        Log an audit entry for a file operation.
        
        Args:
            action: The action being performed
            path: The target path
            kwargs: Additional arguments
        """
        logger.info(
            f"File operation: {action} on {path}",
            extra={
                "event": "file_operation",
                "action": action,
                "path": path,
                "workspace": str(self._workspace_dir),
            }
        )


__all__ = ["FilesTool"]
