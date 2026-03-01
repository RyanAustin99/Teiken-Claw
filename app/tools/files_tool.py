"""
File operation tools (legacy + canonical) backed by hardened file service.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.tools.base import Tool, ToolPolicy, ToolResult
from app.tools.files_service import (
    FileOperationError,
    FileOperationsService,
    build_file_policy,
    render_error_receipt,
    render_success_receipt,
)

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = "./data/workspace"
DEFAULT_MAX_FILE_SIZE = 10_000_000

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".sql",
    ".csv",
    ".tsv",
    ".ini",
    ".cfg",
    ".conf",
    ".log",
    ".toml",
    ".env",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".rst",
    ".adoc",
    ".tex",
    ".bib",
    ".markdown",
    ".mkd",
    ".mkdn",
}

BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".bz2",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".db",
    ".sqlite",
    ".sqlite3",
}

_RUNTIME_WORKSPACE_ROOT: ContextVar[Optional[Path]] = ContextVar("runtime_workspace_root", default=None)


@contextmanager
def runtime_workspace_root(path: Optional[Path]):
    """Temporarily set runtime workspace root for canonical file subtools."""
    token = _RUNTIME_WORKSPACE_ROOT.set(path.resolve() if path else None)
    try:
        yield
    finally:
        _RUNTIME_WORKSPACE_ROOT.reset(token)


def _resolve_runtime_workspace(default_workspace: str = DEFAULT_WORKSPACE) -> Path:
    root = _RUNTIME_WORKSPACE_ROOT.get()
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
        return root
    fallback = Path(default_workspace).resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _service_error_result(op: str, path: str, error: FileOperationError) -> ToolResult:
    receipt = render_error_receipt(op, path, error)
    return ToolResult.error(
        error_code=error.code,
        error_message=error.message,
        metadata={
            "receipt": receipt,
            "error": receipt["error"],
        },
    )


def _build_service(workspace_root: Path | str, *, legacy_max_file_size: Optional[int] = None) -> FileOperationsService:
    policy = build_file_policy(legacy_max_file_size=legacy_max_file_size)
    return FileOperationsService(workspace_root=workspace_root, policy=policy)


class FilesTool(Tool):
    """Legacy action-based files tool kept for backward compatibility."""

    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
        workspace_dir: str = DEFAULT_WORKSPACE,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ):
        super().__init__(policy)
        self._workspace_dir = Path(workspace_dir).resolve()
        self._workspace_root = self._workspace_dir
        self._max_file_size = max_file_size
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        self._service = _build_service(self._workspace_dir, legacy_max_file_size=max_file_size)
        logger.debug("FilesTool initialized with workspace=%s", self._workspace_dir)

    @property
    def name(self) -> str:
        return "files"

    @property
    def description(self) -> str:
        return (
            "File operations tool for managing files in the workspace. "
            "Can list directories, read files, write files, and search for files. "
            "All operations are confined to the workspace directory for security. "
            "Only text files are supported in v1."
        )

    @property
    def json_schema(self) -> Dict[str, Any]:
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
                            "description": "The file action to perform",
                        },
                        "path": {"type": "string", "description": "File or directory path (relative to workspace)"},
                        "content": {"type": "string", "description": "Content to write (for write_file action)"},
                        "query": {"type": "string", "description": "Search query (for search_files action)"},
                        "recursive": {"type": "boolean", "description": "Search recursively", "default": False},
                    },
                    "required": ["action", "path"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        path = str(kwargs.get("path", ""))
        self._audit_log(action, path, kwargs)

        try:
            if action == "list_dir":
                return await self._list_dir(path)
            if action == "read_file":
                return await self._read_file(path)
            if action == "write_file":
                return await self._write_file(path, kwargs.get("content", ""))
            if action == "search_files":
                return await self._search_files(path, kwargs.get("query", ""), kwargs.get("recursive", False))
            if action == "delete_file":
                return await self._delete_file(path)
            return ToolResult.error(
                error_code="INVALID_ACTION",
                error_message="Unknown action: "
                f"{action}. Valid actions: list_dir, read_file, write_file, search_files, delete_file",
            )
        except FileOperationError as exc:
            return _service_error_result(action or "unknown", path, exc)
        except Exception as exc:
            logger.error("Files tool execution error: %s", exc, exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"File operation failed: {exc}",
            )

    async def _list_dir(self, path: str) -> ToolResult:
        try:
            result = self._service.list_dir(path or ".")
        except FileOperationError as exc:
            return _service_error_result("list", path, exc)

        entries = [
            {
                "name": item["name"],
                "type": "directory" if item["kind"] == "dir" else "file",
                "size": item.get("size"),
                "modified": item.get("modified"),
            }
            for item in result["items"]
        ]
        formatted = self._format_directory_listing(path or ".", entries)
        receipt = render_success_receipt(result)
        receipt["entry_count"] = len(entries)
        return ToolResult.success(content=formatted, metadata={"receipt": receipt, "path": path, "entry_count": len(entries), "action": "list_dir"})

    async def _read_file(self, path: str) -> ToolResult:
        try:
            result = self._service.read_text_file(path)
        except FileOperationError as exc:
            return _service_error_result("read", path, exc)
        receipt = render_success_receipt(result)
        return ToolResult.success(content=result["content"], metadata={"receipt": receipt, "path": path, "size": result["bytes"], "action": "read_file"})

    async def _write_file(self, path: str, content: str) -> ToolResult:
        try:
            result = self._service.write_text_file(path, content)
        except FileOperationError as exc:
            return _service_error_result("write", path, exc)
        receipt = render_success_receipt(result)
        receipt.update({"sha256": result.get("sha256"), "created_at": result.get("created_at")})
        return ToolResult.success(
            content=f"Successfully wrote {result['bytes']} bytes to {result['path']}",
            metadata={"receipt": receipt, "path": path, "size": result["bytes"], "action": "write_file"},
        )

    async def _search_files(self, path: str, query: str, recursive: bool = False) -> ToolResult:
        if not query:
            return ToolResult.error(error_code="MISSING_QUERY", error_message="Search query is required")

        try:
            safe_path = self._service.resolve_path(path or ".").abs_path
        except FileOperationError as exc:
            return _service_error_result("list", path, exc)

        if not safe_path.exists():
            return ToolResult.error(error_code="NOT_FOUND", error_message=f"Directory not found: {path}")
        if not safe_path.is_dir():
            return ToolResult.error(error_code="NOT_DIRECTORY", error_message=f"Path is not a directory: {path}")

        results: List[Dict[str, Any]] = []
        query_lower = query.lower()
        files = list(safe_path.rglob("*")) if recursive else list(safe_path.glob("*"))

        for file_path in files:
            if not file_path.is_file():
                continue
            if not self._is_text_file(file_path):
                continue
            if file_path.stat().st_size > self._max_file_size:
                continue

            match_info = {
                "path": str(file_path.relative_to(self._workspace_dir)).replace("\\", "/"),
                "name_match": query_lower in file_path.name.lower(),
                "content_matches": [],
            }

            try:
                read_result = self._service.read_text_file(str(file_path.relative_to(self._workspace_dir)).replace("\\", "/"))
                content = read_result["content"]
            except FileOperationError:
                continue

            if query_lower in content.lower():
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        match_info["content_matches"].append({"line": i + 1, "text": line.strip()[:100]})
                        if len(match_info["content_matches"]) >= 5:
                            break

            if match_info["name_match"] or match_info["content_matches"]:
                results.append(match_info)

        formatted = self._format_search_results(query, results)
        receipt = {
            "ok": True,
            "op": "search",
            "path": path,
            "bytes": 0,
            "message": f"Found {len(results)} results",
            "result_count": len(results),
        }
        return ToolResult.success(
            content=formatted,
            metadata={
                "receipt": receipt,
                "path": path,
                "query": query,
                "result_count": len(results),
                "recursive": recursive,
                "action": "search_files",
            },
        )

    async def _delete_file(self, path: str) -> ToolResult:
        try:
            result = self._service.delete(path)
        except FileOperationError as exc:
            return _service_error_result("delete", path, exc)
        receipt = render_success_receipt(result)
        return ToolResult.success(
            content=f"Successfully deleted: {result['path']}",
            metadata={"receipt": receipt, "path": path, "action": "delete_file"},
        )

    def _get_safe_path(self, path: str) -> Path:
        return self._service.resolve_path(path).abs_path

    def _is_text_file(self, path: Path) -> bool:
        ext = path.suffix.lower()
        if ext in BINARY_EXTENSIONS:
            return False
        if ext in TEXT_EXTENSIONS:
            return True
        if not ext:
            return True
        logger.debug("Unknown file extension: %s, treating as text", ext)
        return True

    def _format_directory_listing(self, path: str, entries: List[Dict[str, Any]]) -> str:
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

    def _format_search_results(self, query: str, results: List[Dict[str, Any]]) -> str:
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

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def _audit_log(self, action: str, path: str, kwargs: Dict[str, Any]) -> None:
        _ = kwargs
        logger.info(
            "File operation: %s on %s",
            action,
            path,
            extra={"event": "file_operation", "action": action, "path": path, "workspace": str(self._workspace_dir)},
        )


class _CanonicalFilesTool(Tool):
    """Base class for canonical files.* tools."""

    required_fields: tuple[str, ...] = ()

    def __init__(self, policy: Optional[ToolPolicy] = None, max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        super().__init__(policy=policy)
        self.max_file_size = max_file_size

    @property
    def description(self) -> str:
        return f"Canonical workspace file tool: {self.name}"

    async def _validate_inputs(self, kwargs: Dict[str, Any]) -> None:
        for field_name in self.required_fields:
            value = kwargs.get(field_name)
            if value is None:
                raise ValueError(f"Missing required argument: {field_name}")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Argument cannot be empty: {field_name}")

    def _runtime_service(self) -> FileOperationsService:
        workspace_root = _resolve_runtime_workspace()
        return _build_service(workspace_root, legacy_max_file_size=self.max_file_size)


class FilesWriteSubtool(_CanonicalFilesTool):
    required_fields = ("path", "content")

    @property
    def name(self) -> str:
        return "files.write"

    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Write text content to a workspace-relative file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "encoding": {"type": "string", "default": "utf-8"},
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        await self._validate_inputs(kwargs)
        relative_path = str(kwargs.get("path", "")).strip()
        content = kwargs.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        try:
            result = self._runtime_service().write_text_file(
                relative_path,
                content,
                encoding=str(kwargs.get("encoding", "utf-8")),
            )
            receipt = render_success_receipt(result)
            receipt.update(
                {
                    "sha256": result.get("sha256"),
                    "created_at": result.get("created_at"),
                }
            )
            return ToolResult.success(content=result["message"], metadata={"receipt": receipt})
        except FileOperationError as exc:
            return _service_error_result("write", relative_path, exc)
        except Exception as exc:
            return ToolResult.error("WRITE_ERROR", f"Failed to write file: {exc}")


class FilesReadSubtool(_CanonicalFilesTool):
    required_fields = ("path",)

    @property
    def name(self) -> str:
        return "files.read"

    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Read a workspace-relative text file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        await self._validate_inputs(kwargs)
        relative_path = str(kwargs.get("path", "")).strip()
        try:
            result = self._runtime_service().read_text_file(relative_path)
            receipt = render_success_receipt(result)
            return ToolResult.success(content=result["content"], metadata={"receipt": receipt})
        except FileOperationError as exc:
            return _service_error_result("read", relative_path, exc)
        except Exception as exc:
            return ToolResult.error("READ_ERROR", f"Failed to read file: {exc}")


class FilesListSubtool(_CanonicalFilesTool):
    @property
    def name(self) -> str:
        return "files.list"

    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "List files in a workspace-relative directory.",
                "parameters": {
                    "type": "object",
                    "properties": {"dir": {"type": "string", "default": "."}},
                    "required": [],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        relative_dir = str(kwargs.get("dir", ".")).strip() or "."
        try:
            result = self._runtime_service().list_dir(relative_dir)
            items = [{"path": item["path"], "kind": item["kind"]} for item in result["items"]]
            receipt = render_success_receipt(result)
            receipt.update({"count": len(items), "items": items[:200], "truncated": len(items) > 200})
            content = json.dumps(receipt, ensure_ascii=False)
            return ToolResult.success(content=content, metadata={"receipt": receipt})
        except FileOperationError as exc:
            return _service_error_result("list", relative_dir, exc)
        except Exception as exc:
            return ToolResult.error("LIST_ERROR", f"Failed to list directory: {exc}")


class FilesExistsSubtool(_CanonicalFilesTool):
    required_fields = ("path",)

    @property
    def name(self) -> str:
        return "files.exists"

    @property
    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Check if a workspace-relative path exists.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        await self._validate_inputs(kwargs)
        relative_path = str(kwargs.get("path", "")).strip()
        try:
            result = self._runtime_service().stat(relative_path)
            receipt = render_success_receipt(result)
            receipt.update({"exists": result["exists"], "kind": result["kind"]})
            return ToolResult.success(content=json.dumps(receipt, ensure_ascii=False), metadata={"receipt": receipt})
        except FileOperationError as exc:
            return _service_error_result("stat", relative_path, exc)
        except Exception as exc:
            return ToolResult.error("EXISTS_ERROR", f"Failed to check path: {exc}")


__all__ = [
    "FilesTool",
    "FilesWriteSubtool",
    "FilesReadSubtool",
    "FilesListSubtool",
    "FilesExistsSubtool",
    "runtime_workspace_root",
    "TEXT_EXTENSIONS",
    "BINARY_EXTENSIONS",
]

