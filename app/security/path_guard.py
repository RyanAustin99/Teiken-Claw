"""Backward-compatible path guard wrapper over hardened workspace path policies."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from app.security.workspace_paths import (
    PathPolicyError,
    initialize_workspace_context,
    resolve_in_sandbox,
)

logger = logging.getLogger(__name__)


class PathSecurityError(Exception):
    """Raised when a path fails security validation."""

    def __init__(self, message: str, path: Optional[str] = None):
        super().__init__(message)
        self.path = path


class PathGuard:
    """Compatibility facade retaining prior PathGuard API shape."""

    def __init__(self, workspace_root: str, allow_symlinks: bool = False):
        if not workspace_root:
            raise ValueError("workspace_root cannot be empty")
        self._workspace = initialize_workspace_context(workspace_root)
        self._allow_symlinks = bool(allow_symlinks)

    @property
    def workspace_root(self) -> Path:
        return self._workspace.root_real

    @property
    def workspace_root_str(self) -> str:
        return str(self._workspace.root_real)

    def normalize_path(self, path: str) -> str:
        try:
            resolved = resolve_in_sandbox(
                self._workspace,
                path,
                deny_symlinks=not self._allow_symlinks,
            )
            return str(resolved.abs_path)
        except PathPolicyError as exc:
            raise PathSecurityError(exc.message, path=path) from exc

    def prevent_traversal(self, path: str) -> str:
        # Traversal is checked by resolve_in_sandbox; this method remains for compatibility.
        self.normalize_path(path)
        return path

    def is_within_workspace(self, path: str) -> bool:
        try:
            self.normalize_path(path)
            return True
        except PathSecurityError:
            return False

    def is_safe_path(self, base_path: str, target_path: str) -> bool:
        # base_path retained for signature compatibility; workspace root is authoritative.
        _ = base_path
        return self.is_within_workspace(target_path)

    def validate_and_resolve(self, path: str) -> Tuple[bool, str, Optional[str]]:
        try:
            normalized = self.normalize_path(path)
            return (True, normalized, None)
        except PathSecurityError as exc:
            return (False, path, str(exc))
        except Exception as exc:
            return (False, path, f"Validation error: {exc}")

    def get_safe_path(self, path: str) -> str:
        is_valid, resolved_path, error = self.validate_and_resolve(path)
        if not is_valid:
            raise PathSecurityError(error or "Invalid path", path=path)
        return resolved_path

    def __repr__(self) -> str:
        return f"<PathGuard workspace={self.workspace_root!r}>"


DEFAULT_WORKSPACE = Path("./data/workspace").resolve()


def get_default_path_guard() -> PathGuard:
    return PathGuard(str(DEFAULT_WORKSPACE))


__all__ = [
    "PathSecurityError",
    "PathGuard",
    "DEFAULT_WORKSPACE",
    "get_default_path_guard",
]

