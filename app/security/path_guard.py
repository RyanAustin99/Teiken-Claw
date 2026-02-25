"""
Path security utilities for the Teiken Claw agent system.

This module provides path validation and traversal protection to ensure
file operations are confined to designated workspace directories.

Key Features:
    - Path normalization and validation
    - Traversal attack prevention
    - Workspace boundary enforcement
    - Cross-platform path handling

Security Considerations:
    - Prevents directory traversal attacks using ../ sequences
    - Handles symlinks that could escape the workspace
    - Normalizes paths to prevent bypass via encoding tricks
    - Works across Windows and Unix-like systems
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PathSecurityError(Exception):
    """Raised when a path fails security validation."""
    
    def __init__(self, message: str, path: Optional[str] = None):
        super().__init__(message)
        self.path = path


class PathGuard:
    """
    Path security guard for validating and sanitizing file paths.
    
    Ensures all file operations are confined to a designated workspace
    directory and prevents directory traversal attacks.
    
    Attributes:
        workspace_root: The root directory that all paths must be within
        allow_symlinks: Whether to allow symlinks (default: False for security)
    
    Example:
        >>> guard = PathGuard("/app/data/workspace")
        >>> safe_path = guard.normalize_path("subdir/file.txt")
        >>> if guard.is_safe_path(safe_path):
        ...     # Proceed with file operation
        ...     pass
    """
    
    def __init__(
        self,
        workspace_root: str,
        allow_symlinks: bool = False,
    ):
        """
        Initialize the path guard with a workspace root.
        
        Args:
            workspace_root: The root directory that all paths must be within
            allow_symlinks: Whether to allow symlinks (default: False)
            
        Raises:
            ValueError: If workspace_root is empty or not an absolute path
        """
        if not workspace_root:
            raise ValueError("workspace_root cannot be empty")
        
        # Resolve to absolute path
        self._workspace_root = Path(workspace_root).resolve()
        self._allow_symlinks = allow_symlinks
        
        # Ensure workspace exists
        if not self._workspace_root.exists():
            logger.warning(
                f"Workspace root does not exist: {self._workspace_root}",
                extra={"event": "workspace_not_found", "path": str(self._workspace_root)}
            )
        
        logger.debug(
            f"PathGuard initialized with workspace: {self._workspace_root}",
            extra={"event": "path_guard_init", "workspace": str(self._workspace_root)}
        )
    
    @property
    def workspace_root(self) -> Path:
        """Get the workspace root as a Path object."""
        return self._workspace_root
    
    @property
    def workspace_root_str(self) -> str:
        """Get the workspace root as a string."""
        return str(self._workspace_root)
    
    def normalize_path(self, path: str) -> str:
        """
        Normalize a path by resolving relative components and removing redundancies.
        
        This method:
        - Converts backslashes to forward slashes (cross-platform)
        - Resolves . and .. components
        - Removes redundant slashes
        - Returns an absolute path within the workspace
        
        Args:
            path: The path to normalize
            
        Returns:
            Normalized absolute path as a string
            
        Raises:
            PathSecurityError: If the path is empty or contains null bytes
        """
        if not path:
            raise PathSecurityError("Path cannot be empty", path=path)
        
        # Check for null bytes (potential bypass attempt)
        if '\x00' in path:
            raise PathSecurityError("Path contains null bytes", path=path)
        
        # Convert to Path object and resolve
        try:
            # Start with workspace root for relative paths
            if os.path.isabs(path):
                # For absolute paths, we still need to check if they're in workspace
                normalized = Path(path).resolve()
            else:
                # For relative paths, resolve from workspace root
                normalized = (self._workspace_root / path).resolve()
            
            return str(normalized)
            
        except Exception as e:
            logger.warning(
                f"Path normalization failed: {path}",
                extra={"event": "path_normalize_error", "path": path, "error": str(e)}
            )
            raise PathSecurityError(f"Path normalization failed: {e}", path=path)
    
    def prevent_traversal(self, path: str) -> str:
        """
        Validate that a path does not contain traversal sequences.
        
        This method checks for and rejects paths that attempt to escape
        the workspace using:
        - ../ sequences
        - Encoded traversal attempts (e.g., %2e%2e%2f)
        - Backslash traversal on Windows (..\\)
        
        Args:
            path: The path to validate
            
        Returns:
            The validated path
            
        Raises:
            PathSecurityError: If the path contains traversal sequences
        """
        if not path:
            raise PathSecurityError("Path cannot be empty", path=path)
        
        # Check for obvious traversal attempts
        traversal_patterns = [
            "../",           # Unix traversal
            "..\\",          # Windows traversal
            "..",            # Standalone parent reference
            "%2e%2e/",       # URL encoded ../
            "%2e%2e%2f",     # URL encoded ../
            "%2e%2e%5c",     # URL encoded ..\\
            "..%2f",         # Partial URL encoding
            "..%5c",         # Partial URL encoding
            "%252e%252e",    # Double URL encoding
        ]
        
        path_lower = path.lower()
        for pattern in traversal_patterns:
            if pattern.lower() in path_lower:
                logger.warning(
                    f"Path traversal attempt detected: {path}",
                    extra={"event": "traversal_attempt", "path": path, "pattern": pattern}
                )
                raise PathSecurityError(
                    f"Path contains traversal sequence: {pattern}",
                    path=path
                )
        
        return path
    
    def is_within_workspace(self, path: str) -> bool:
        """
        Check if a path is within the workspace directory.
        
        This method resolves the path and checks if it starts with
        the workspace root path.
        
        Args:
            path: The path to check (can be relative or absolute)
            
        Returns:
            True if the path is within the workspace, False otherwise
        """
        try:
            # Normalize the path first
            normalized = self.normalize_path(path)
            resolved_path = Path(normalized).resolve()
            
            # Check if it's within workspace
            try:
                resolved_path.relative_to(self._workspace_root)
                return True
            except ValueError:
                return False
                
        except PathSecurityError:
            return False
        except Exception as e:
            logger.debug(
                f"Error checking workspace boundary: {e}",
                extra={"event": "workspace_check_error", "path": path}
            )
            return False
    
    def is_safe_path(self, base_path: str, target_path: str) -> bool:
        """
        Check if a target path is safe relative to a base path.
        
        This method validates that the target path, when resolved,
        is within the workspace and does not escape the base path.
        
        Args:
            base_path: The base directory to check against
            target_path: The target path to validate
            
        Returns:
            True if the path is safe, False otherwise
        """
        try:
            # Normalize both paths
            normalized_base = self.normalize_path(base_path)
            normalized_target = self.normalize_path(target_path)
            
            # Check workspace boundary
            if not self.is_within_workspace(normalized_target):
                return False
            
            # Check symlink safety
            if not self._allow_symlinks:
                target = Path(normalized_target)
                if target.is_symlink():
                    logger.warning(
                        f"Symlink detected in path: {normalized_target}",
                        extra={"event": "symlink_detected", "path": normalized_target}
                    )
                    return False
            
            return True
            
        except PathSecurityError:
            return False
        except Exception:
            return False
    
    def validate_and_resolve(self, path: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate a path and return resolved result.
        
        This is a convenience method that combines all validation steps
        and returns a tuple with the result.
        
        Args:
            path: The path to validate
            
        Returns:
            Tuple of (is_valid, resolved_path, error_message)
            - is_valid: True if path is safe to use
            - resolved_path: The resolved absolute path (or original if invalid)
            - error_message: Error description if invalid, None otherwise
        """
        try:
            # Check for traversal attempts
            self.prevent_traversal(path)
            
            # Normalize the path
            normalized = self.normalize_path(path)
            
            # Check workspace boundary
            if not self.is_within_workspace(normalized):
                return (
                    False,
                    normalized,
                    f"Path is outside workspace: {normalized}"
                )
            
            # Check symlink safety
            if not self._allow_symlinks:
                target = Path(normalized)
                if target.exists() and target.is_symlink():
                    return (
                        False,
                        normalized,
                        f"Symlinks are not allowed: {normalized}"
                    )
            
            return (True, normalized, None)
            
        except PathSecurityError as e:
            return (False, path, str(e))
        except Exception as e:
            return (False, path, f"Validation error: {e}")
    
    def get_safe_path(self, path: str) -> str:
        """
        Get a safe path within the workspace.
        
        This method validates the path and returns the resolved path
        if it's safe, otherwise raises an exception.
        
        Args:
            path: The path to validate
            
        Returns:
            The resolved safe path
            
        Raises:
            PathSecurityError: If the path is not safe
        """
        is_valid, resolved_path, error = self.validate_and_resolve(path)
        
        if not is_valid:
            raise PathSecurityError(error or "Invalid path", path=path)
        
        return resolved_path
    
    def __repr__(self) -> str:
        return f"<PathGuard workspace={self._workspace_root!r}>"


# Default workspace path
DEFAULT_WORKSPACE = Path("./data/workspace").resolve()


def get_default_path_guard() -> PathGuard:
    """
    Get a PathGuard instance with the default workspace.
    
    Returns:
        PathGuard instance with default workspace
    """
    return PathGuard(str(DEFAULT_WORKSPACE))


__all__ = [
    "PathGuard",
    "PathSecurityError",
    "get_default_path_guard",
    "DEFAULT_WORKSPACE",
]
