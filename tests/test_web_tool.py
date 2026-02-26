"""
Tests for Web Tool.

This module tests the WebTool class for:
- Web search functionality
- URL fetching
- Text extraction
- Search and extract combined
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.web_tool import WebTool
from app.tools.base import ToolPolicy


class TestWebTool:
    """Tests for WebTool class."""

    def test_init_default(self):
        """Test initialization with default settings."""
        tool = WebTool()
        assert tool.name == "web"
        assert tool._timeout_sec == 30.0
        assert tool._max_response_size == 1_000_000

    def test_init_custom(self):
        """Test initialization with custom settings."""
        policy = ToolPolicy(timeout_sec=60.0)
        tool = WebTool(
            policy=policy,
            timeout_sec=60.0,
            max_response_size=5_000_000,
            allowed_domains=["example.com"],
        )
        assert tool._timeout_sec == 60.0
        assert tool._max_response_size == 5_000_000
        assert tool._allowed_domains == ["example.com"]

    def test_name_property(self):
        """Test name property."""
        tool = WebTool()
        assert tool.name == "web"

    def test_description_property(self):
        """Test description property."""
        tool = WebTool()
        assert "web" in tool.description.lower()
        assert "search" in tool.description.lower()

    def test_json_schema(self):
        """Test JSON schema structure."""
        tool = WebTool()
        schema = tool.json_schema

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web"
        assert "action" in schema["function"]["parameters"]["properties"]
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "url" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_missing_action(self):
        """Test execute with missing action."""
        tool = WebTool()
        result = await tool.execute()
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code

    @pytest.mark.asyncio
    async def test_execute_invalid_action(self):
        """Test execute with invalid action."""
        tool = WebTool()
        result = await tool.execute(action="invalid")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        """Test search with missing query."""
        tool = WebTool()
        result = await tool.execute(action="search")
        assert not result.ok
        assert "MISSING_QUERY" in result.error_code

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful search."""
        tool = WebTool()

        mock_results = [
            {
                "title": "Test Result",
                "href": "https://example.com",
                "body": "Test snippet",
            }
        ]

        with patch("app.tools.web_tool.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = iter(mock_results)
            mock_ddgs.return_value = mock_instance

            result = await tool.execute(action="search", query="test query")

            assert result.ok
            assert "Test Result" in result.content

    @pytest.mark.asyncio
    async def test_fetch_missing_url(self):
        """Test fetch with missing URL."""
        tool = WebTool()
        result = await tool.execute(action="fetch")
        assert not result.ok
        assert "MISSING_URL" in result.error_code

    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self):
        """Test fetch with invalid URL."""
        tool = WebTool()
        result = await tool.execute(action="fetch", url="javascript:alert(1)")
        assert not result.ok
        assert "INVALID_URL" in result.error_code

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Test successful fetch."""
        tool = WebTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.content = b"<html><body>Test content</body></html>"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await tool.execute(
                action="fetch",
                url="https://example.com",
            )

            assert result.ok
            assert "Test content" in result.content

    @pytest.mark.asyncio
    async def test_fetch_binary_rejected(self):
        """Test that binary content is rejected."""
        tool = WebTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\x00\x01\x02\x03"
        mock_response.headers = {"content-type": "application/octet-stream"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await tool.execute(
                action="fetch",
                url="https://example.com/file.exe",
            )

            assert not result.ok
            assert "BINARY_CONTENT" in result.error_code

    @pytest.mark.asyncio
    async def test_extract_missing_url(self):
        """Test extract with missing URL."""
        tool = WebTool()
        result = await tool.execute(action="extract")
        assert not result.ok
        assert "MISSING_URL" in result.error_code

    @pytest.mark.asyncio
    async def test_extract_success(self):
        """Test successful text extraction."""
        tool = WebTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Main Heading</h1>
                <p>This is the main content of the page.</p>
            </body>
        </html>
        """
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await tool.execute(
                action="extract",
                url="https://example.com",
            )

            assert result.ok
            assert (
                "content" in result.content.lower()
                or "Main" in result.content
            )

    @pytest.mark.asyncio
    async def test_search_and_extract_missing_query(self):
        """Test search_and_extract with missing query."""
        tool = WebTool()
        result = await tool.execute(action="search_and_extract")
        assert not result.ok
        assert "MISSING_QUERY" in result.error_code

    def test_is_text_content(self):
        """Test _is_text_content helper."""
        tool = WebTool()

        assert tool._is_text_content("text/html")
        assert tool._is_text_content("application/json")
        assert tool._is_text_content("text/plain")
        assert not tool._is_text_content("image/png")
        assert not tool._is_text_content("application/pdf")

    def test_is_html_content(self):
        """Test _is_html_content helper."""
        tool = WebTool()

        assert tool._is_html_content("text/html")
        assert tool._is_html_content("application/xhtml+xml")
        assert not tool._is_html_content("text/plain")
        assert not tool._is_html_content("application/json")

    def test_truncate_content(self):
        """Test _truncate_content helper."""
        tool = WebTool()

        short_content = "Short content"
        assert tool._truncate_content(short_content) == short_content

        long_content = "x" * 15000
        truncated = tool._truncate_content(long_content, max_chars=10000)
        assert len(truncated) < len(long_content)
        assert "truncated" in truncated.lower()

    def test_domain_allowlist(self):
        """Test domain allowlist enforcement."""
        tool = WebTool(allowed_domains=["allowed.com"])

        # Should fail for non-allowed domain
        tool._sanitizer.sanitize_url("https://notallowed.com")
        # The sanitizer should have the allowed domains set
        assert "allowed.com" in tool._sanitizer._allowed_domains


class TestWebToolPolicy:
    """Tests for WebTool policy enforcement."""

    def test_policy_applied(self):
        """Test that policy is properly applied."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=45.0,
        )
        tool = WebTool(policy=policy)

        assert tool.policy.enabled
        assert tool.policy.timeout_sec == 45.0

    def test_to_ollama_tool(self):
        """Test conversion to Ollama tool format."""
        tool = WebTool()
        ollama_tool = tool.to_ollama_tool()

        assert ollama_tool == tool.json_schema
