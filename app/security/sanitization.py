"""
Input sanitization utilities for the Teiken Claw agent system.

This module provides sanitization functions for various input types
to prevent injection attacks and ensure data integrity.

Key Features:
    - URL sanitization and validation
    - Path sanitization
    - Command sanitization
    - Filename sanitization

Security Considerations:
    - Prevents URL injection attacks
    - Blocks dangerous URL schemes (javascript:, data:, etc.)
    - Removes shell metacharacters from commands
    - Validates filenames for unsafe characters
"""

import re
import logging
import urllib.parse
from typing import Optional, List, Set

logger = logging.getLogger(__name__)


class SanitizationError(Exception):
    """Raised when input fails sanitization."""
    
    def __init__(self, message: str, input_value: Optional[str] = None):
        super().__init__(message)
        self.input_value = input_value


class Sanitizer:
    """
    Input sanitizer for various data types.
    
    Provides methods to sanitize and validate URLs, paths, commands,
    and filenames to prevent injection attacks.
    
    Example:
        >>> sanitizer = Sanitizer()
        >>> safe_url = sanitizer.sanitize_url("https://example.com/path")
        >>> safe_filename = sanitizer.sanitize_filename("document.pdf")
    """
    
    # Allowed URL schemes
    SAFE_URL_SCHEMES: Set[str] = {"http", "https"}
    
    # Dangerous URL schemes that should be blocked
    DANGEROUS_SCHEMES: Set[str] = {
        "javascript", "data", "vbscript", "file", "ftp",
        "sftp", "ssh", "telnet", "gopher", "ldap",
    }
    
    # Characters that are unsafe in filenames
    UNSAFE_FILENAME_CHARS: Set[str] = {
        '<', '>', ':', '"', '|', '?', '*',
        '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
        '\x08', '\x09', '\x0a', '\x0b', '\x0c', '\x0d', '\x0e', '\x0f',
        '\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17',
        '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e', '\x1f',
    }
    
    # Windows reserved filenames
    WINDOWS_RESERVED_NAMES: Set[str] = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    
    # Shell metacharacters that could be dangerous
    SHELL_METACHARACTERS: Set[str] = {
        '|', '&', ';', '<', '>', '(', ')', '$', '`', '\\', '"', "'",
        '\n', '\r', '*', '?', '[', ']', '{', '}', '!', '#',
    }
    
    # Maximum lengths
    MAX_URL_LENGTH: int = 2048
    MAX_PATH_LENGTH: int = 4096
    MAX_FILENAME_LENGTH: int = 255
    MAX_COMMAND_LENGTH: int = 8192
    
    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        strict_mode: bool = True,
    ):
        """
        Initialize the sanitizer.
        
        Args:
            allowed_domains: Optional list of allowed domains for URLs
            strict_mode: If True, reject suspicious input; if False, sanitize it
        """
        self._allowed_domains = set(allowed_domains) if allowed_domains else None
        self._strict_mode = strict_mode
    
    def sanitize_url(self, url: str) -> str:
        """
        Sanitize and validate a URL.
        
        This method:
        - Strips whitespace
        - Validates the URL scheme
        - Checks for dangerous schemes
        - Optionally validates against allowed domains
        - Limits URL length
        
        Args:
            url: The URL to sanitize
            
        Returns:
            The sanitized URL
            
        Raises:
            SanitizationError: If the URL is invalid or dangerous
        """
        if not url:
            raise SanitizationError("URL cannot be empty", url)
        
        # Strip whitespace
        url = url.strip()
        
        # Check length
        if len(url) > self.MAX_URL_LENGTH:
            raise SanitizationError(
                f"URL exceeds maximum length of {self.MAX_URL_LENGTH}",
                url
            )
        
        # Parse the URL
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            raise SanitizationError(f"Invalid URL format: {e}", url)
        
        # Check scheme
        scheme = parsed.scheme.lower()
        
        if not scheme:
            # Default to https if no scheme provided
            url = "https://" + url
            parsed = urllib.parse.urlparse(url)
            scheme = "https"
        
        if scheme in self.DANGEROUS_SCHEMES:
            logger.warning(
                f"Dangerous URL scheme blocked: {scheme}",
                extra={"event": "dangerous_scheme_blocked", "scheme": scheme, "url": url}
            )
            raise SanitizationError(
                f"URL scheme '{scheme}' is not allowed",
                url
            )
        
        if scheme not in self.SAFE_URL_SCHEMES:
            if self._strict_mode:
                raise SanitizationError(
                    f"URL scheme '{scheme}' is not in allowed list",
                    url
                )
        
        # Check for credentials in URL (security risk)
        if parsed.username or parsed.password:
            logger.warning(
                "URL with credentials blocked",
                extra={"event": "credentials_in_url", "url": url[:50] + "..."}
            )
            raise SanitizationError(
                "URLs with credentials are not allowed",
                url
            )
        
        # Check against allowed domains
        if self._allowed_domains is not None:
            hostname = parsed.hostname
            if hostname:
                hostname_lower = hostname.lower()
                domain_allowed = any(
                    hostname_lower == domain.lower() or
                    hostname_lower.endswith('.' + domain.lower())
                    for domain in self._allowed_domains
                )
                if not domain_allowed:
                    if self._strict_mode:
                        raise SanitizationError(
                            f"Domain '{hostname}' is not in allowed list",
                            url
                        )
                    logger.warning(
                        f"Domain outside allowlist accepted in non-strict mode: {hostname}",
                        extra={"event": "domain_allowlist_bypass", "hostname": hostname}
                    )
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'javascript:',
            r'data:',
            r'vbscript:',
            r'<script',
            r'on\w+\s*=',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                logger.warning(
                    f"Suspicious pattern in URL: {pattern}",
                    extra={"event": "suspicious_url_pattern", "pattern": pattern}
                )
                raise SanitizationError(
                    "URL contains suspicious content",
                    url
                )
        
        return url
    
    def sanitize_path(self, path: str) -> str:
        """
        Sanitize a file path.
        
        This method:
        - Strips whitespace
        - Removes null bytes
        - Normalizes path separators
        - Checks for traversal attempts
        - Limits path length
        
        Args:
            path: The path to sanitize
            
        Returns:
            The sanitized path
            
        Raises:
            SanitizationError: If the path is invalid or dangerous
        """
        if not path:
            raise SanitizationError("Path cannot be empty", path)
        
        # Strip whitespace
        path = path.strip()
        
        # Check length
        if len(path) > self.MAX_PATH_LENGTH:
            raise SanitizationError(
                f"Path exceeds maximum length of {self.MAX_PATH_LENGTH}",
                path
            )
        
        # Remove null bytes
        if '\x00' in path:
            raise SanitizationError("Path contains null bytes", path)
        
        # Check for traversal attempts
        traversal_patterns = [
            '../', '..\\', '..',
            '%2e%2e/', '%2e%2e%2f', '%2e%2e%5c',
        ]
        
        path_lower = path.lower()
        for pattern in traversal_patterns:
            if pattern.lower() in path_lower:
                logger.warning(
                    f"Path traversal attempt detected: {path}",
                    extra={"event": "path_traversal_attempt", "path": path}
                )
                raise SanitizationError(
                    "Path contains traversal sequence",
                    path
                )
        
        # Normalize path separators (convert backslashes to forward slashes)
        # But keep the original for Windows compatibility
        normalized = path.replace('\\', '/')
        
        # Remove redundant slashes
        while '//' in normalized:
            normalized = normalized.replace('//', '/')
        
        return normalized
    
    def sanitize_command(self, command: str, allowed_commands: Optional[Set[str]] = None) -> str:
        """
        Sanitize a command string.
        
        This method:
        - Strips whitespace
        - Checks for shell metacharacters
        - Optionally validates against allowed commands
        - Limits command length
        
        Note: This is for display/logging purposes. Commands should be
        executed through a proper allowlist mechanism, not string sanitization.
        
        Args:
            command: The command to sanitize
            allowed_commands: Optional set of allowed command prefixes
            
        Returns:
            The sanitized command
            
        Raises:
            SanitizationError: If the command is invalid or dangerous
        """
        if not command:
            raise SanitizationError("Command cannot be empty", command)
        
        # Strip whitespace
        command = command.strip()
        
        # Check length
        if len(command) > self.MAX_COMMAND_LENGTH:
            raise SanitizationError(
                f"Command exceeds maximum length of {self.MAX_COMMAND_LENGTH}",
                command
            )
        
        # Check for shell metacharacters in strict mode
        if self._strict_mode:
            found_metachars = set(command) & self.SHELL_METACHARACTERS
            if found_metachars:
                logger.warning(
                    f"Shell metacharacters in command: {found_metachars}",
                    extra={"event": "shell_metacharacters", "metachars": list(found_metachars)}
                )
                raise SanitizationError(
                    f"Command contains shell metacharacters: {found_metachars}",
                    command
                )
        
        # Check against allowed commands
        if allowed_commands is not None:
            # Extract the base command (first word)
            base_command = command.split()[0] if command.split() else ""
            if base_command.lower() not in {c.lower() for c in allowed_commands}:
                raise SanitizationError(
                    f"Command '{base_command}' is not in allowed list",
                    command
                )
        
        return command
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename.
        
        This method:
        - Strips whitespace
        - Removes unsafe characters
        - Checks for reserved names
        - Limits filename length
        - Prevents hidden files (starting with .)
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            The sanitized filename
            
        Raises:
            SanitizationError: If the filename is invalid or dangerous
        """
        if not filename:
            raise SanitizationError("Filename cannot be empty", filename)
        
        # Strip whitespace
        filename = filename.strip()
        
        # Check length
        if len(filename) > self.MAX_FILENAME_LENGTH:
            # Truncate but preserve extension
            name, ext = self._split_extension(filename)
            max_name_len = self.MAX_FILENAME_LENGTH - len(ext) - 1
            if max_name_len > 0:
                filename = name[:max_name_len] + ext
            else:
                filename = filename[:self.MAX_FILENAME_LENGTH]
        
        # Remove null bytes and control characters
        filename = ''.join(c for c in filename if c not in self.UNSAFE_FILENAME_CHARS)
        
        # Check for empty after sanitization
        if not filename:
            raise SanitizationError("Filename is empty after sanitization", filename)
        
        # Check for reserved names (Windows)
        name_without_ext = filename.split('.')[0].upper()
        if name_without_ext in self.WINDOWS_RESERVED_NAMES:
            raise SanitizationError(
                f"Filename uses reserved name: {name_without_ext}",
                filename
            )
        
        # Check for hidden files (starting with .)
        if filename.startswith('.'):
            if self._strict_mode:
                raise SanitizationError(
                    "Hidden files (starting with .) are not allowed",
                    filename
                )
            else:
                filename = '_' + filename[1:]
        
        # Check for relative path indicators
        if filename in ('.', '..'):
            raise SanitizationError(
                "Filename cannot be a relative path indicator",
                filename
            )
        
        return filename
    
    def _split_extension(self, filename: str) -> tuple:
        """
        Split a filename into name and extension.
        
        Args:
            filename: The filename to split
            
        Returns:
            Tuple of (name, extension) where extension includes the dot
        """
        if '.' in filename:
            parts = filename.rsplit('.', 1)
            return (parts[0], '.' + parts[1])
        return (filename, '')
    
    def is_safe_url(self, url: str) -> bool:
        """
        Check if a URL is safe without raising an exception.
        
        Args:
            url: The URL to check
            
        Returns:
            True if the URL is safe, False otherwise
        """
        try:
            self.sanitize_url(url)
            return True
        except SanitizationError:
            return False
    
    def is_safe_filename(self, filename: str) -> bool:
        """
        Check if a filename is safe without raising an exception.
        
        Args:
            filename: The filename to check
            
        Returns:
            True if the filename is safe, False otherwise
        """
        try:
            self.sanitize_filename(filename)
            return True
        except SanitizationError:
            return False


def get_default_sanitizer() -> Sanitizer:
    """
    Get a Sanitizer instance with default settings.
    
    Returns:
        Sanitizer instance with strict mode enabled
    """
    return Sanitizer(strict_mode=True)


__all__ = [
    "Sanitizer",
    "SanitizationError",
    "get_default_sanitizer",
]
