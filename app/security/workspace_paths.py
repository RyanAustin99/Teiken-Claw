"""Workspace path normalization and sandbox-safe resolution utilities."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging


ERR_PATH_ABSOLUTE = "ERR_PATH_ABSOLUTE"
ERR_PATH_TRAVERSAL = "ERR_PATH_TRAVERSAL"
ERR_PATH_OUTSIDE_SANDBOX = "ERR_PATH_OUTSIDE_SANDBOX"
ERR_PATH_SYMLINK_ESCAPE = "ERR_PATH_SYMLINK_ESCAPE"

_WINDOWS_DRIVE_PATTERN = re.compile(r"^[a-zA-Z]:")
logger = logging.getLogger(__name__)
_LOGGED_ROOTS: set[str] = set()


class PathPolicyError(Exception):
    """Raised when a user-supplied path violates sandbox policy."""

    def __init__(self, code: str, message: str, *, hint: Optional[str] = None, raw_path: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.raw_path = raw_path


@dataclass(frozen=True)
class WorkspaceContext:
    """Canonical workspace root paths used by all file operations."""

    root_abs: Path
    root_real: Path


@dataclass(frozen=True)
class ResolvedPath:
    """Sandbox-validated path details for downstream tooling and auditing."""

    abs_path: Path
    rel_path: str
    parent_abs_path: Path
    parent_rel_path: str


def initialize_workspace_context(workspace_root: str | Path) -> WorkspaceContext:
    """Resolve and validate the single workspace root for runtime use."""
    if not workspace_root:
        raise ValueError("workspace_root cannot be empty")

    root_abs = Path(workspace_root).expanduser()
    if not root_abs.is_absolute():
        root_abs = root_abs.resolve()
    root_abs.mkdir(parents=True, exist_ok=True)
    root_real = root_abs.resolve()

    if not root_real.exists():
        raise ValueError(f"Workspace root does not exist: {root_real}")
    if not root_real.is_dir():
        raise ValueError(f"Workspace root is not a directory: {root_real}")
    if not os.access(root_real, os.R_OK | os.W_OK):
        raise ValueError(f"Workspace root is not readable/writable: {root_real}")

    root_key = str(root_real)
    if root_key not in _LOGGED_ROOTS:
        _LOGGED_ROOTS.add(root_key)
        logger.info("Workspace root initialized: %s", root_key)

    return WorkspaceContext(root_abs=root_abs, root_real=root_real)


def normalize_user_path(input_path: str) -> str:
    """Normalize and validate a user path into a stable relative path."""
    if input_path is None:
        raise PathPolicyError(
            ERR_PATH_TRAVERSAL,
            "Path cannot be empty",
            hint="Use a relative path like notes/file.md",
            raw_path=None,
        )

    raw = str(input_path).strip()
    if not raw:
        raise PathPolicyError(
            ERR_PATH_TRAVERSAL,
            "Path cannot be empty",
            hint="Use a relative path like notes/file.md",
            raw_path=input_path,
        )

    if "\x00" in raw:
        raise PathPolicyError(
            ERR_PATH_TRAVERSAL,
            "Path contains null bytes",
            hint="Remove hidden characters from the path",
            raw_path=input_path,
        )

    if any((ord(ch) < 32 or ord(ch) == 127) for ch in raw):
        raise PathPolicyError(
            ERR_PATH_TRAVERSAL,
            "Path contains control characters",
            hint="Use only standard filename characters",
            raw_path=input_path,
        )

    normalized = raw.replace("\\", "/")
    lower = normalized.lower()
    encoded_traversal_patterns = ("%2e%2e", "..%2f", "..%5c", "%2e%2e%2f", "%2e%2e%5c", "%252e%252e")
    if any(pattern in lower for pattern in encoded_traversal_patterns):
        raise PathPolicyError(
            ERR_PATH_TRAVERSAL,
            "Encoded path traversal is not allowed",
            hint="Use a plain workspace-relative path",
            raw_path=input_path,
        )

    if normalized.startswith("//"):
        raise PathPolicyError(
            ERR_PATH_ABSOLUTE,
            "UNC paths are not allowed",
            hint="Use a workspace-relative path",
            raw_path=input_path,
        )

    if _WINDOWS_DRIVE_PATTERN.match(normalized):
        raise PathPolicyError(
            ERR_PATH_ABSOLUTE,
            "Drive-qualified absolute paths are not allowed",
            hint="Use a workspace-relative path",
            raw_path=input_path,
        )

    if normalized.startswith("/"):
        raise PathPolicyError(
            ERR_PATH_ABSOLUTE,
            "Absolute paths are not allowed",
            hint="Use a workspace-relative path",
            raw_path=input_path,
        )

    while normalized.startswith("./"):
        normalized = normalized[2:]

    parts = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise PathPolicyError(
                    ERR_PATH_TRAVERSAL,
                    "Path traversal is not allowed",
                    hint="Remove '..' and stay within the workspace",
                    raw_path=input_path,
                )
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        return "."
    return "/".join(parts)


def _check_no_symlink_components(workspace_root: Path, normalized_rel_path: str) -> None:
    """Deny symlinks in any existing path component (strict v1)."""
    if normalized_rel_path == ".":
        return

    current = workspace_root
    for part in Path(normalized_rel_path).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise PathPolicyError(
                ERR_PATH_SYMLINK_ESCAPE,
                "Symlink paths are not allowed in file operations",
                hint="Use a regular directory/file path inside the workspace",
                raw_path=normalized_rel_path,
            )


def _ensure_within_workspace(candidate: Path, workspace_root: Path, *, raw_path: str) -> None:
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise PathPolicyError(
            ERR_PATH_OUTSIDE_SANDBOX,
            "Path resolves outside workspace sandbox",
            hint="Use a workspace-relative path like notes/file.md",
            raw_path=raw_path,
        ) from exc


def resolve_in_sandbox(
    workspace: WorkspaceContext,
    rel_path: str,
    *,
    deny_symlinks: bool = True,
) -> ResolvedPath:
    """Resolve a user path to a sandbox-safe absolute path."""
    normalized = normalize_user_path(rel_path)
    candidate = workspace.root_real if normalized == "." else (workspace.root_real / normalized)

    if deny_symlinks:
        _check_no_symlink_components(workspace.root_real, normalized)

    parent = candidate.parent if normalized != "." else workspace.root_real
    parent_resolved = parent.resolve(strict=False)
    _ensure_within_workspace(parent_resolved, workspace.root_real, raw_path=rel_path)

    candidate_resolved = candidate.resolve(strict=False)
    _ensure_within_workspace(candidate_resolved, workspace.root_real, raw_path=rel_path)

    rel_norm = "." if candidate_resolved == workspace.root_real else str(candidate_resolved.relative_to(workspace.root_real)).replace("\\", "/")
    parent_rel = "." if parent_resolved == workspace.root_real else str(parent_resolved.relative_to(workspace.root_real)).replace("\\", "/")

    return ResolvedPath(
        abs_path=candidate_resolved,
        rel_path=rel_norm,
        parent_abs_path=parent_resolved,
        parent_rel_path=parent_rel,
    )
