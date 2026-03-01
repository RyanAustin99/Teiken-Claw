"""Guarded filesystem service used by both legacy and canonical file tools."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from app.config.settings import settings
from app.observability.file_audit import get_file_audit_logger
from app.security.workspace_paths import (
    ERR_PATH_ABSOLUTE,
    ERR_PATH_OUTSIDE_SANDBOX,
    ERR_PATH_SYMLINK_ESCAPE,
    ERR_PATH_TRAVERSAL,
    PathPolicyError,
    ResolvedPath,
    WorkspaceContext,
    initialize_workspace_context,
    normalize_user_path,
    resolve_in_sandbox,
)

logger = logging.getLogger(__name__)


ERR_EXT_NOT_ALLOWED = "ERR_EXT_NOT_ALLOWED"
ERR_FILE_TOO_LARGE = "ERR_FILE_TOO_LARGE"
ERR_BINARY_NOT_SUPPORTED = "ERR_BINARY_NOT_SUPPORTED"
ERR_OVERWRITE_NOT_ALLOWED = "ERR_OVERWRITE_NOT_ALLOWED"

BINARY_EXTENSION_DENYLIST = {
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


LEGACY_ERROR_CODE_MAP = {
    ERR_PATH_ABSOLUTE: "PATH_SECURITY_ERROR",
    ERR_PATH_TRAVERSAL: "PATH_SECURITY_ERROR",
    ERR_PATH_OUTSIDE_SANDBOX: "PATH_SECURITY_ERROR",
    ERR_PATH_SYMLINK_ESCAPE: "PATH_SECURITY_ERROR",
    ERR_EXT_NOT_ALLOWED: "BINARY_FILE",
    ERR_FILE_TOO_LARGE: "FILE_TOO_LARGE",
    ERR_BINARY_NOT_SUPPORTED: "ENCODING_ERROR",
    ERR_OVERWRITE_NOT_ALLOWED: "PERMISSION_DENIED",
}

_RUNTIME_FILE_POLICY_OVERRIDE: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "runtime_file_policy_override",
    default=None,
)


@dataclass(frozen=True)
class FilePolicy:
    """Capabilities and limits for file service operations."""

    allowed_ops: set[str] = field(default_factory=lambda: {"read", "write", "list", "mkdir", "delete", "stat"})
    allowed_extensions: set[str] = field(default_factory=lambda: {".md", ".txt", ".json", ".yaml", ".yml", ".log"})
    max_read_bytes: int = 1_048_576
    max_write_bytes: int = 262_144
    allow_overwrite: bool = True
    auto_mkdir: bool = True
    soft_write_warn_ratio: float = 0.75


class FileOperationError(Exception):
    """Structured file service error."""

    def __init__(self, code: str, message: str, *, hint: Optional[str] = None, legacy_code: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.legacy_code = legacy_code or LEGACY_ERROR_CODE_MAP.get(code, "EXECUTION_ERROR")

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "legacy_code": self.legacy_code,
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload


def build_file_policy(*, legacy_max_file_size: Optional[int] = None) -> FilePolicy:
    """Build file policy from settings with backward-compatible precedence."""
    if legacy_max_file_size is not None:
        read_cap = max(1, int(legacy_max_file_size))
        write_cap = max(1, int(legacy_max_file_size))
    else:
        legacy_cap = max(1, int(getattr(settings, "FILES_MAX_SIZE", 10_000_000)))
        read_cap = max(1, int(getattr(settings, "FILES_MAX_READ_BYTES", legacy_cap)))
        write_cap = max(1, int(getattr(settings, "FILES_MAX_WRITE_BYTES", legacy_cap)))

    allowed_exts = getattr(settings, "FILES_ALLOWED_WRITE_EXTENSIONS", None) or [".md", ".txt", ".json", ".yaml", ".yml", ".log"]
    normalized_exts = {
        (item if str(item).startswith(".") else f".{item}").lower()
        for item in allowed_exts
        if str(item).strip()
    }
    if not normalized_exts:
        normalized_exts = {".md"}

    return FilePolicy(
        allowed_extensions=normalized_exts,
        max_read_bytes=read_cap,
        max_write_bytes=write_cap,
        allow_overwrite=bool(getattr(settings, "FILES_ALLOW_OVERWRITE", True)),
        auto_mkdir=bool(getattr(settings, "FILES_AUTO_MKDIR", True)),
        soft_write_warn_ratio=float(getattr(settings, "FILES_SOFT_WRITE_WARN_RATIO", 0.75)),
    )


class FileOperationsService:
    """Safe workspace-only file operations with structured audit events."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        policy: Optional[FilePolicy] = None,
    ) -> None:
        self.workspace: WorkspaceContext = initialize_workspace_context(workspace_root)
        self.policy = policy or build_file_policy()
        self._audit = get_file_audit_logger()

    def _effective_policy(self) -> FilePolicy:
        override = _RUNTIME_FILE_POLICY_OVERRIDE.get()
        if not override:
            return self.policy

        base_ext = {str(item).lower() for item in self.policy.allowed_extensions}
        override_ext = {str(item).lower() for item in override.get("allowed_extensions", []) if item}
        if override_ext:
            effective_ext = base_ext & override_ext if base_ext else override_ext
        else:
            effective_ext = base_ext

        return FilePolicy(
            allowed_ops=set(self.policy.allowed_ops),
            allowed_extensions=effective_ext or base_ext,
            max_read_bytes=min(int(self.policy.max_read_bytes), int(override.get("max_read_bytes", self.policy.max_read_bytes))),
            max_write_bytes=min(int(self.policy.max_write_bytes), int(override.get("max_write_bytes", self.policy.max_write_bytes))),
            allow_overwrite=bool(override.get("allow_overwrite", self.policy.allow_overwrite)),
            auto_mkdir=bool(override.get("auto_mkdir", self.policy.auto_mkdir)),
            soft_write_warn_ratio=float(self.policy.soft_write_warn_ratio),
        )

    def resolve_path(self, path: str) -> ResolvedPath:
        """Resolve a user path using sandbox guarantees."""
        try:
            return resolve_in_sandbox(self.workspace, path, deny_symlinks=True)
        except PathPolicyError as exc:
            raise self._from_path_error(exc) from exc

    def write_text_file(self, path: str, content: str, *, encoding: str = "utf-8") -> dict[str, Any]:
        op = "write"
        policy = self._effective_policy()
        started = time.perf_counter()
        bytes_in = 0
        bytes_out = 0
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None
        warning_code: Optional[str] = None
        resolved: Optional[ResolvedPath] = None

        try:
            self._ensure_op_allowed(op)
            text = content if isinstance(content, str) else str(content)
            if not text:
                raise FileOperationError("EMPTY_CONTENT", "Content cannot be empty", legacy_code="EMPTY_CONTENT")

            bytes_in = len(text.encode("utf-8"))
            if bytes_in > policy.max_write_bytes:
                raise FileOperationError(
                    ERR_FILE_TOO_LARGE,
                    f"Content size ({bytes_in} bytes) exceeds write limit ({policy.max_write_bytes} bytes)",
                    hint=f"Reduce content size below {policy.max_write_bytes} bytes",
                    legacy_code="CONTENT_TOO_LARGE",
                )

            resolved = self.resolve_path(path)
            path_rel = resolved.rel_path
            self._enforce_write_extension(resolved.rel_path)

            target = resolved.abs_path
            if target.exists() and not target.is_file():
                raise FileOperationError("NOT_FILE", f"Path is not a file: {path}", legacy_code="NOT_FILE")
            if target.exists() and not policy.allow_overwrite:
                raise FileOperationError(
                    ERR_OVERWRITE_NOT_ALLOWED,
                    f"Overwrite is not allowed for path: {resolved.rel_path}",
                    hint="Choose a new filename or enable overwrite policy",
                )

            if policy.auto_mkdir:
                target.parent.mkdir(parents=True, exist_ok=True)
            elif not target.parent.exists():
                raise FileOperationError(
                    "NOT_FOUND",
                    f"Parent directory does not exist: {resolved.parent_rel_path}",
                    hint="Create the directory first",
                    legacy_code="NOT_FOUND",
                )

            temp_path: Optional[Path] = None
            try:
                fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.tmp.", dir=str(target.parent))
                temp_path = Path(temp_name)
                with os.fdopen(fd, "w", encoding=encoding) as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink(missing_ok=True)

            bytes_out = target.stat().st_size
            status = "success"
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            ratio = policy.soft_write_warn_ratio
            if 0 < ratio <= 1 and bytes_in >= int(policy.max_write_bytes * ratio):
                warning_code = "approaching_write_cap"
                logger.warning(
                    "Write payload approaching configured cap",
                    extra={"event": "approaching_write_cap", "path": resolved.rel_path, "bytes": bytes_in},
                )

            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "bytes": bytes_out,
                "message": f"Wrote {bytes_out} bytes to {resolved.rel_path}",
                "sha256": digest,
                "created_at": datetime.now(UTC).isoformat(),
                "warning_code": warning_code,
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        except OSError as exc:
            error = FileOperationError("WRITE_ERROR", f"Failed to write file: {exc}", legacy_code="WRITE_ERROR")
            error_code = error.code
            raise error from exc
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def read_text_file(self, path: str) -> dict[str, Any]:
        op = "read"
        policy = self._effective_policy()
        started = time.perf_counter()
        bytes_out = 0
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None

        try:
            self._ensure_op_allowed(op)
            resolved = self.resolve_path(path)
            path_rel = resolved.rel_path
            target = resolved.abs_path

            if not target.exists():
                raise FileOperationError("NOT_FOUND", f"File not found: {path}", legacy_code="NOT_FOUND")
            if not target.is_file():
                raise FileOperationError("NOT_FILE", f"Path is not a file: {path}", legacy_code="NOT_FILE")
            if target.suffix.lower() in BINARY_EXTENSION_DENYLIST:
                raise FileOperationError(
                    ERR_BINARY_NOT_SUPPORTED,
                    "Binary files are not supported",
                    hint="Read a UTF-8 text file instead",
                    legacy_code="BINARY_FILE",
                )

            size = target.stat().st_size
            if size > policy.max_read_bytes:
                raise FileOperationError(
                    ERR_FILE_TOO_LARGE,
                    f"File size ({size} bytes) exceeds read limit ({policy.max_read_bytes} bytes)",
                    hint=f"Read a smaller file under {policy.max_read_bytes} bytes",
                    legacy_code="FILE_TOO_LARGE",
                )

            data = target.read_bytes()
            bytes_out = len(data)
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise FileOperationError(
                    ERR_BINARY_NOT_SUPPORTED,
                    "Only UTF-8 text files are supported",
                    hint="Use a UTF-8 text file format",
                    legacy_code="ENCODING_ERROR",
                ) from exc

            status = "success"
            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "bytes": bytes_out,
                "message": f"Read {bytes_out} bytes from {resolved.rel_path}",
                "content": content,
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        except OSError as exc:
            error = FileOperationError("READ_ERROR", f"Failed to read file: {exc}", legacy_code="READ_ERROR")
            error_code = error.code
            raise error from exc
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                bytes_out=bytes_out,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def list_dir(self, path: str = ".") -> dict[str, Any]:
        op = "list"
        started = time.perf_counter()
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None

        try:
            self._ensure_op_allowed(op)
            resolved = self.resolve_path(path or ".")
            path_rel = resolved.rel_path
            target_dir = resolved.abs_path

            if not target_dir.exists():
                raise FileOperationError("NOT_FOUND", f"Directory not found: {path}", legacy_code="NOT_FOUND")
            if not target_dir.is_dir():
                raise FileOperationError("NOT_DIRECTORY", f"Path is not a directory: {path}", legacy_code="NOT_DIRECTORY")

            items: list[dict[str, Any]] = []
            for entry in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                rel = str(entry.relative_to(self.workspace.root_real)).replace("\\", "/")
                stat = entry.stat()
                items.append(
                    {
                        "name": entry.name,
                        "path": rel,
                        "kind": "dir" if entry.is_dir() else "file",
                        "size": stat.st_size if entry.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    }
                )

            status = "success"
            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "bytes": 0,
                "message": f"Listed {len(items)} items in {resolved.rel_path}",
                "items": items,
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def mkdir(self, path: str) -> dict[str, Any]:
        op = "mkdir"
        started = time.perf_counter()
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None

        try:
            self._ensure_op_allowed(op)
            resolved = self.resolve_path(path)
            path_rel = resolved.rel_path
            resolved.abs_path.mkdir(parents=True, exist_ok=True)
            status = "success"
            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "bytes": 0,
                "message": f"Created directory {resolved.rel_path}",
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def delete(self, path: str) -> dict[str, Any]:
        op = "delete"
        started = time.perf_counter()
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None

        try:
            self._ensure_op_allowed(op)
            resolved = self.resolve_path(path)
            path_rel = resolved.rel_path
            target = resolved.abs_path

            if not target.exists():
                raise FileOperationError("NOT_FOUND", f"File not found: {path}", legacy_code="NOT_FOUND")
            if not target.is_file():
                raise FileOperationError("NOT_FILE", f"Path is not a file: {path}", legacy_code="NOT_FILE")
            target.unlink()

            status = "success"
            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "bytes": 0,
                "message": f"Deleted {resolved.rel_path}",
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def stat(self, path: str) -> dict[str, Any]:
        op = "stat"
        started = time.perf_counter()
        path_rel = self._path_for_audit(path)
        status = "failure"
        error_code: Optional[str] = None

        try:
            self._ensure_op_allowed(op)
            resolved = self.resolve_path(path)
            path_rel = resolved.rel_path
            target = resolved.abs_path

            if not target.exists():
                status = "success"
                return {
                    "ok": True,
                    "op": op,
                    "path": resolved.rel_path,
                    "exists": False,
                    "kind": "missing",
                    "bytes": 0,
                    "message": f"{resolved.rel_path} does not exist",
                }

            stat = target.stat()
            status = "success"
            return {
                "ok": True,
                "op": op,
                "path": resolved.rel_path,
                "exists": True,
                "kind": "dir" if target.is_dir() else "file",
                "bytes": stat.st_size if target.is_file() else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "message": f"{resolved.rel_path} exists",
            }
        except FileOperationError as exc:
            error_code = exc.code
            raise
        finally:
            self._audit.log_event(
                op=op,
                path_rel=path_rel,
                status=status,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def _ensure_op_allowed(self, op: str) -> None:
        if op not in self._effective_policy().allowed_ops:
            raise FileOperationError("PERMISSION_DENIED", f"Operation not allowed by file policy: {op}", legacy_code="PERMISSION_DENIED")

    def _enforce_write_extension(self, rel_path: str) -> None:
        policy = self._effective_policy()
        ext = Path(rel_path).suffix.lower()
        if ext not in policy.allowed_extensions:
            allowed = ", ".join(sorted(policy.allowed_extensions))
            raise FileOperationError(
                ERR_EXT_NOT_ALLOWED,
                f"Extension '{ext or '<none>'}' is not allowed for writes",
                hint=f"Use one of: {allowed}",
            )

    @staticmethod
    def _path_for_audit(raw_path: str) -> Optional[str]:
        try:
            normalized = normalize_user_path(raw_path)
            return normalized
        except Exception:
            return None

    @staticmethod
    def _from_path_error(exc: PathPolicyError) -> FileOperationError:
        return FileOperationError(
            exc.code,
            exc.message,
            hint=exc.hint,
            legacy_code=LEGACY_ERROR_CODE_MAP.get(exc.code, "PATH_SECURITY_ERROR"),
        )


@contextmanager
def runtime_file_policy_override(override: Optional[dict[str, Any]]):
    token = _RUNTIME_FILE_POLICY_OVERRIDE.set(override)
    try:
        yield
    finally:
        _RUNTIME_FILE_POLICY_OVERRIDE.reset(token)


def render_error_receipt(op: str, path: str, error: FileOperationError) -> dict[str, Any]:
    """Return canonical structured error payload for tool metadata/envelopes."""
    return {
        "ok": False,
        "op": op,
        "path": path,
        "error": error.to_payload(),
    }


def render_success_receipt(result: dict[str, Any]) -> dict[str, Any]:
    """Build canonical structured success payload."""
    return {
        "ok": True,
        "op": result.get("op"),
        "path": result.get("path"),
        "bytes": int(result.get("bytes", 0)),
        "message": result.get("message", ""),
    }


__all__ = [
    "ERR_EXT_NOT_ALLOWED",
    "ERR_FILE_TOO_LARGE",
    "ERR_BINARY_NOT_SUPPORTED",
    "FilePolicy",
    "FileOperationError",
    "FileOperationsService",
    "LEGACY_ERROR_CODE_MAP",
    "build_file_policy",
    "render_error_receipt",
    "render_success_receipt",
    "runtime_file_policy_override",
]
