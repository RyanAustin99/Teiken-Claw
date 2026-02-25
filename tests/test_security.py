"""
Tests for security utilities.

This module tests the PathGuard and Sanitizer classes for:
- Path validation and traversal protection
- URL sanitization
- Command sanitization
- Filename sanitization
"""

import pytest
import tempfile
import os
from pathlib import Path

from app.security.path_guard import (
    PathGuard,
    PathSecurityError,
    get_default_path_guard,
)
from app.security.sanitization import (
    Sanitizer,
    SanitizationError,
    get_default_sanitizer,
)


class TestPathGuard:
    """Tests for PathGuard class."""
    
    def test_init_with_valid_workspace(self, tmp_path):
        """Test initialization with a valid workspace."""
        guard = PathGuard(str(tmp_path))
        assert guard.workspace_root == tmp_path.resolve()
    
    def test_init_with_empty_workspace_raises(self):
        """Test that empty workspace raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PathGuard("")
    
    def test_normalize_path_relative(self, tmp_path):
        """Test normalizing a relative path."""
        guard = PathGuard(str(tmp_path))
        normalized = guard.normalize_path("subdir/file.txt")
        assert tmp_path.name in normalized
        assert "subdir" in normalized
    
    def test_normalize_path_with_traversal_raises(self, tmp_path):
        """Test that path traversal raises error."""
        guard = PathGuard(str(tmp_path))
        with pytest.raises(PathSecurityError, match="traversal"):
            guard.prevent_traversal("../../../etc/passwd")
    
    def test_is_within_workspace_true(self, tmp_path):
        """Test that path within workspace returns True."""
        guard = PathGuard(str(tmp_path))
        assert guard.is_within_workspace("subdir/file.txt")
    
    def test_is_within_workspace_false(self, tmp_path):
        """Test that path outside workspace returns False."""
        guard = PathGuard(str(tmp_path))
        # Use an absolute path outside the workspace
        outside_path = str(Path("/etc/passwd").resolve())
        assert not guard.is_within_workspace(outside_path)
    
    def test_is_safe_path_valid(self, tmp_path):
        """Test is_safe_path with valid path."""
        guard = PathGuard(str(tmp_path))
        assert guard.is_safe_path(str(tmp_path), "subdir/file.txt")
    
    def test_validate_and_resolve_valid(self, tmp_path):
        """Test validate_and_resolve with valid path."""
        guard = PathGuard(str(tmp_path))
        is_valid, resolved, error = guard.validate_and_resolve("subdir/file.txt")
        assert is_valid
        assert error is None
    
    def test_validate_and_resolve_traversal(self, tmp_path):
        """Test validate_and_resolve with traversal attempt."""
        guard = PathGuard(str(tmp_path))
        is_valid, resolved, error = guard.validate_and_resolve("../../../etc/passwd")
        assert not is_valid
        assert "traversal" in error.lower()
    
    def test_get_safe_path_valid(self, tmp_path):
        """Test get_safe_path with valid path."""
        guard = PathGuard(str(tmp_path))
        safe = guard.get_safe_path("subdir/file.txt")
        assert tmp_path.name in safe
    
    def test_get_safe_path_invalid_raises(self, tmp_path):
        """Test get_safe_path with invalid path raises."""
        guard = PathGuard(str(tmp_path))
        with pytest.raises(PathSecurityError):
            guard.get_safe_path("../../../etc/passwd")
    
    def test_null_byte_in_path_raises(self, tmp_path):
        """Test that null bytes in path raise error."""
        guard = PathGuard(str(tmp_path))
        with pytest.raises(PathSecurityError, match="null"):
            guard.normalize_path("file\x00.txt")
    
    def test_get_default_path_guard(self):
        """Test getting default path guard."""
        guard = get_default_path_guard()
        assert isinstance(guard, PathGuard)


class TestSanitizer:
    """Tests for Sanitizer class."""
    
    def test_sanitize_url_valid(self):
        """Test sanitizing a valid URL."""
        sanitizer = Sanitizer()
        url = sanitizer.sanitize_url("https://example.com/path")
        assert url == "https://example.com/path"
    
    def test_sanitize_url_adds_scheme(self):
        """Test that URL without scheme gets https."""
        sanitizer = Sanitizer()
        url = sanitizer.sanitize_url("example.com/path")
        assert url.startswith("https://")
    
    def test_sanitize_url_dangerous_scheme_raises(self):
        """Test that dangerous schemes raise error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="not allowed"):
            sanitizer.sanitize_url("javascript:alert(1)")
    
    def test_sanitize_url_credentials_raises(self):
        """Test that URLs with credentials raise error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="credentials"):
            sanitizer.sanitize_url("https://user:pass@example.com")
    
    def test_sanitize_url_with_allowed_domains(self):
        """Test URL validation with allowed domains."""
        sanitizer = Sanitizer(allowed_domains=["example.com", "test.com"])
        # Should pass
        url = sanitizer.sanitize_url("https://example.com/path")
        assert url == "https://example.com/path"
        # Should fail
        with pytest.raises(SanitizationError, match="not in allowed"):
            sanitizer.sanitize_url("https://other.com/path")
    
    def test_sanitize_url_empty_raises(self):
        """Test that empty URL raises error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="empty"):
            sanitizer.sanitize_url("")
    
    def test_sanitize_url_too_long_raises(self):
        """Test that overly long URL raises error."""
        sanitizer = Sanitizer()
        long_url = "https://example.com/" + "a" * 3000
        with pytest.raises(SanitizationError, match="exceeds"):
            sanitizer.sanitize_url(long_url)
    
    def test_sanitize_path_valid(self):
        """Test sanitizing a valid path."""
        sanitizer = Sanitizer()
        path = sanitizer.sanitize_path("subdir/file.txt")
        assert "subdir" in path
        assert "file.txt" in path
    
    def test_sanitize_path_traversal_raises(self):
        """Test that path traversal raises error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="traversal"):
            sanitizer.sanitize_path("../../../etc/passwd")
    
    def test_sanitize_path_null_byte_raises(self):
        """Test that null bytes raise error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="null"):
            sanitizer.sanitize_path("file\x00.txt")
    
    def test_sanitize_path_empty_raises(self):
        """Test that empty path raises error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="empty"):
            sanitizer.sanitize_path("")
    
    def test_sanitize_command_valid(self):
        """Test sanitizing a valid command."""
        sanitizer = Sanitizer()
        cmd = sanitizer.sanitize_command("Get-Process")
        assert cmd == "Get-Process"
    
    def test_sanitize_command_metacharacters_raises(self):
        """Test that shell metacharacters raise error in strict mode."""
        sanitizer = Sanitizer(strict_mode=True)
        with pytest.raises(SanitizationError, match="metacharacters"):
            sanitizer.sanitize_command("ls | grep test")
    
    def test_sanitize_command_with_allowlist(self):
        """Test command validation with allowlist."""
        sanitizer = Sanitizer(strict_mode=False)
        cmd = sanitizer.sanitize_command(
            "Get-Process",
            allowed_commands={"Get-Process", "Get-Service"}
        )
        assert cmd == "Get-Process"
    
    def test_sanitize_filename_valid(self):
        """Test sanitizing a valid filename."""
        sanitizer = Sanitizer()
        name = sanitizer.sanitize_filename("document.pdf")
        assert name == "document.pdf"
    
    def test_sanitize_filename_removes_unsafe_chars(self):
        """Test that unsafe characters are removed."""
        sanitizer = Sanitizer(strict_mode=False)
        name = sanitizer.sanitize_filename("file<>.txt")
        assert "<" not in name
        assert ">" not in name
    
    def test_sanitize_filename_reserved_raises(self):
        """Test that reserved names raise error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="reserved"):
            sanitizer.sanitize_filename("CON")
    
    def test_sanitize_filename_hidden_raises(self):
        """Test that hidden files raise error in strict mode."""
        sanitizer = Sanitizer(strict_mode=True)
        with pytest.raises(SanitizationError, match="Hidden"):
            sanitizer.sanitize_filename(".hidden")
    
    def test_sanitize_filename_empty_raises(self):
        """Test that empty filename raises error."""
        sanitizer = Sanitizer()
        with pytest.raises(SanitizationError, match="empty"):
            sanitizer.sanitize_filename("")
    
    def test_is_safe_url(self):
        """Test is_safe_url helper."""
        sanitizer = Sanitizer()
        assert sanitizer.is_safe_url("https://example.com")
        assert not sanitizer.is_safe_url("javascript:alert(1)")
    
    def test_is_safe_filename(self):
        """Test is_safe_filename helper."""
        sanitizer = Sanitizer()
        assert sanitizer.is_safe_filename("document.pdf")
        assert not sanitizer.is_safe_filename("CON")
    
    def test_get_default_sanitizer(self):
        """Test getting default sanitizer."""
        sanitizer = get_default_sanitizer()
        assert isinstance(sanitizer, Sanitizer)
        assert sanitizer._strict_mode


class TestSecurityIntegration:
    """Integration tests for security utilities."""
    
    def test_path_guard_with_sanitizer(self, tmp_path):
        """Test using PathGuard with Sanitizer together."""
        guard = PathGuard(str(tmp_path))
        sanitizer = Sanitizer()
        
        # Sanitize then validate
        raw_path = "subdir/file.txt"
        sanitized = sanitizer.sanitize_path(raw_path)
        safe = guard.get_safe_path(sanitized)
        
        assert tmp_path.name in safe
    
    def test_full_validation_flow(self, tmp_path):
        """Test full validation flow for file operations."""
        guard = PathGuard(str(tmp_path))
        sanitizer = Sanitizer()
        
        # Test valid path
        valid_path = "documents/report.pdf"
        is_valid, resolved, error = guard.validate_and_resolve(
            sanitizer.sanitize_path(valid_path)
        )
        assert is_valid
        
        # Test invalid path
        invalid_path = "../../../etc/passwd"
        with pytest.raises(SanitizationError):
            sanitizer.sanitize_path(invalid_path)
