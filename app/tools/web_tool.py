"""
Web operations tool for the Teiken Claw agent system.

This module provides web-related capabilities including:
- Web search using DuckDuckGo
- URL content fetching
- Text extraction from web pages
- Combined search and extract operations

Key Features:
    - Domain allowlist support
    - Timeout handling
    - Response size limits
    - User-agent header configuration
    - No binary downloads in v1

Security Considerations:
    - URL validation and sanitization
    - Domain restriction via allowlist
    - Response size limits to prevent memory exhaustion
    - Timeout protection against hanging requests
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

import httpx

from app.tools.base import Tool, ToolResult, ToolPolicy
from app.security.sanitization import Sanitizer, SanitizationError

logger = logging.getLogger(__name__)

# Default user agent
DEFAULT_USER_AGENT = "TeikenClaw/1.0 (AI Agent System)"

# Default headers
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,text/plain",
    "Accept-Language": "en-US,en;q=0.9",
}

# Optional DuckDuckGo search client (patched in tests).
try:
    from duckduckgo_search import DDGS
except ImportError:  # pragma: no cover - exercised via runtime fallbacks
    DDGS = None


class WebTool(Tool):
    """
    Web operations tool for searching and fetching web content.
    
    Provides capabilities for:
    - Web search (DuckDuckGo)
    - URL content fetching
    - Text extraction from web pages
    - Combined search and extract
    
    Attributes:
        timeout_sec: Request timeout in seconds
        max_response_size: Maximum response size in bytes
        allowed_domains: Optional list of allowed domains
        user_agent: User agent string for requests
    """
    
    def __init__(
        self,
        policy: Optional[ToolPolicy] = None,
        timeout_sec: float = 30.0,
        max_response_size: int = 1_000_000,
        allowed_domains: Optional[List[str]] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        """
        Initialize the web tool.
        
        Args:
            policy: Tool policy configuration
            timeout_sec: Request timeout in seconds
            max_response_size: Maximum response size in bytes
            allowed_domains: Optional list of allowed domains (empty = all allowed)
            user_agent: User agent string for requests
        """
        super().__init__(policy)
        self._timeout_sec = timeout_sec
        self._max_response_size = max_response_size
        self._allowed_domains = allowed_domains or []
        self._user_agent = user_agent
        # Non-strict mode keeps URL normalization while allowing caller-side handling.
        self._sanitizer = Sanitizer(allowed_domains=allowed_domains, strict_mode=False)
        
        logger.debug(
            f"WebTool initialized with timeout={timeout_sec}s, "
            f"max_size={max_response_size}, domains={allowed_domains}"
        )
    
    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "web"
    
    @property
    def description(self) -> str:
        """Tool description for the AI model."""
        return (
            "Web operations tool for searching and fetching web content. "
            "Can search the web, fetch URL content, and extract readable text from pages. "
            "Use this tool when you need to look up information online or retrieve content from URLs."
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
                            "enum": ["search", "fetch", "extract", "search_and_extract"],
                            "description": "The web action to perform"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (for search and search_and_extract actions)"
                        },
                        "url": {
                            "type": "string",
                            "description": "URL to fetch or extract (for fetch and extract actions)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search results (default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute a web operation.
        
        Args:
            action: The action to perform (search, fetch, extract, search_and_extract)
            query: Search query for search actions
            url: URL for fetch/extract actions
            max_results: Maximum search results (default: 5)
            
        Returns:
            ToolResult with the operation result
        """
        action = kwargs.get("action", "")
        
        try:
            if action == "search":
                query = kwargs.get("query", "")
                max_results = kwargs.get("max_results", 5)
                return await self._search(query, max_results)
            
            elif action == "fetch":
                url = kwargs.get("url", "")
                return await self._fetch(url)
            
            elif action == "extract":
                url = kwargs.get("url", "")
                return await self._extract(url)
            
            elif action == "search_and_extract":
                query = kwargs.get("query", "")
                max_results = kwargs.get("max_results", 3)
                return await self._search_and_extract(query, max_results)
            
            else:
                return ToolResult.error(
                    error_code="INVALID_ACTION",
                    error_message=f"Unknown action: {action}. Valid actions: search, fetch, extract, search_and_extract"
                )
        
        except asyncio.TimeoutError:
            logger.warning(f"Web tool timeout for action: {action}")
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Request timed out after {self._timeout_sec} seconds"
            )
        
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error in web tool: {e}")
            return ToolResult.error(
                error_code="HTTP_ERROR",
                error_message=f"HTTP error: {e.response.status_code}"
            )
        
        except Exception as e:
            logger.error(f"Web tool execution error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXECUTION_ERROR",
                error_message=f"Web operation failed: {e}"
            )
    
    async def _search(self, query: str, max_results: int = 5) -> ToolResult:
        """
        Perform a web search using DuckDuckGo.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            ToolResult with search results
        """
        if not query:
            return ToolResult.error(
                error_code="MISSING_QUERY",
                error_message="Search query is required"
            )
        
        logger.info(f"Performing web search: {query[:50]}...")
        
        try:
            if DDGS is None:
                raise ImportError("duckduckgo-search package is not installed")
            
            results = []
            
            # Run search in thread pool to avoid blocking
            def _do_search():
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(query, max_results=max_results))
                    return search_results
            
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(None, _do_search)
            
            for result in search_results:
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                })
            
            if not results:
                return ToolResult.success(
                    content="No search results found.",
                    metadata={"query": query, "result_count": 0}
                )
            
            # Format results
            formatted = self._format_search_results(results)
            
            return ToolResult.success(
                content=formatted,
                metadata={
                    "query": query,
                    "result_count": len(results),
                    "action": "search"
                }
            )
            
        except ImportError:
            logger.warning("duckduckgo-search not installed")
            return ToolResult.error(
                error_code="DEPENDENCY_MISSING",
                error_message="Search functionality requires duckduckgo-search package"
            )
        
        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="SEARCH_ERROR",
                error_message=f"Search failed: {e}"
            )
    
    async def _fetch(self, url: str) -> ToolResult:
        """
        Fetch content from a URL.
        
        Args:
            url: URL to fetch
            
        Returns:
            ToolResult with fetched content
        """
        if not url:
            return ToolResult.error(
                error_code="MISSING_URL",
                error_message="URL is required"
            )
        
        # Validate URL
        try:
            safe_url = self._sanitizer.sanitize_url(url)
        except SanitizationError as e:
            return ToolResult.error(
                error_code="INVALID_URL",
                error_message=str(e)
            )
        
        logger.info(f"Fetching URL: {safe_url}")
        
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_sec,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                response = await client.get(
                    safe_url,
                    headers={**DEFAULT_HEADERS, "User-Agent": self._user_agent},
                )
                
                # Check response size
                content_length = len(response.content)
                if content_length > self._max_response_size:
                    return ToolResult.error(
                        error_code="RESPONSE_TOO_LARGE",
                        error_message=f"Response size ({content_length} bytes) exceeds limit ({self._max_response_size} bytes)"
                    )
                
                # Check content type
                content_type = response.headers.get("content-type", "")
                if not self._is_text_content(content_type):
                    return ToolResult.error(
                        error_code="BINARY_CONTENT",
                        error_message=f"Binary content not supported in v1 (content-type: {content_type})"
                    )
                
                # Return content
                content = response.text
                
                return ToolResult.success(
                    content=self._truncate_content(content),
                    metadata={
                        "url": safe_url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "content_length": content_length,
                        "action": "fetch"
                    }
                )
                
        except httpx.TimeoutException:
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Request timed out after {self._timeout_sec} seconds"
            )
        
        except httpx.HTTPStatusError as e:
            return ToolResult.error(
                error_code="HTTP_ERROR",
                error_message=f"HTTP error: {e.response.status_code}"
            )
        
        except Exception as e:
            logger.error(f"Fetch error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="FETCH_ERROR",
                error_message=f"Failed to fetch URL: {e}"
            )
    
    async def _extract(self, url: str) -> ToolResult:
        """
        Extract readable text from a URL.
        
        Args:
            url: URL to extract text from
            
        Returns:
            ToolResult with extracted text
        """
        if not url:
            return ToolResult.error(
                error_code="MISSING_URL",
                error_message="URL is required"
            )
        
        # Validate URL
        try:
            safe_url = self._sanitizer.sanitize_url(url)
        except SanitizationError as e:
            return ToolResult.error(
                error_code="INVALID_URL",
                error_message=str(e)
            )
        
        logger.info(f"Extracting text from URL: {safe_url}")
        
        try:
            # First fetch the content
            async with httpx.AsyncClient(
                timeout=self._timeout_sec,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                response = await client.get(
                    safe_url,
                    headers={**DEFAULT_HEADERS, "User-Agent": self._user_agent},
                )
                
                content_type = response.headers.get("content-type", "")
                if not self._is_html_content(content_type):
                    return ToolResult.error(
                        error_code="NOT_HTML",
                        error_message=f"Content is not HTML (content-type: {content_type})"
                    )
                
                html_content = response.text
            
            # Extract text using readability
            try:
                from readability import Document
                from bs4 import BeautifulSoup
                
                doc = Document(html_content)
                summary = doc.summary()
                
                # Parse with BeautifulSoup to get clean text
                soup = BeautifulSoup(summary, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                
                # Clean up extra whitespace
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                clean_text = "\n".join(lines)
                
                return ToolResult.success(
                    content=self._truncate_content(clean_text),
                    metadata={
                        "url": safe_url,
                        "title": doc.title(),
                        "content_length": len(clean_text),
                        "action": "extract"
                    }
                )
                
            except ImportError:
                # Fallback: just strip HTML tags
                from bs4 import BeautifulSoup
                
                soup = BeautifulSoup(html_content, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                clean_text = "\n".join(lines)
                
                return ToolResult.success(
                    content=self._truncate_content(clean_text),
                    metadata={
                        "url": safe_url,
                        "title": soup.title.string if soup.title else "",
                        "content_length": len(clean_text),
                        "action": "extract",
                        "note": "Used basic extraction (readability-lxml not installed)"
                    }
                )
                
        except httpx.TimeoutException:
            return ToolResult.error(
                error_code="TIMEOUT",
                error_message=f"Request timed out after {self._timeout_sec} seconds"
            )
        
        except Exception as e:
            logger.error(f"Extract error: {e}", exc_info=True)
            return ToolResult.error(
                error_code="EXTRACT_ERROR",
                error_message=f"Failed to extract text: {e}"
            )
    
    async def _search_and_extract(self, query: str, max_results: int = 3) -> ToolResult:
        """
        Search and extract content from top results.
        
        Args:
            query: Search query
            max_results: Maximum number of results to extract
            
        Returns:
            ToolResult with combined extracted content
        """
        if not query:
            return ToolResult.error(
                error_code="MISSING_QUERY",
                error_message="Search query is required"
            )
        
        logger.info(f"Search and extract: {query[:50]}...")
        
        # First, perform search
        search_result = await self._search(query, max_results)
        
        if not search_result.ok:
            return search_result
        
        # Extract URLs from search results
        results = search_result.metadata.get("results", [])
        if not results:
            # Parse the formatted content to get URLs
            # This is a fallback if metadata doesn't have results
            return ToolResult.success(
                content=f"Search completed but no URLs to extract.\n\n{search_result.content}",
                metadata={"query": query, "action": "search_and_extract"}
            )
        
        # Extract content from each URL
        extracted = []
        for result in results[:max_results]:
            url = result.get("url", "")
            if not url:
                continue
            
            extract_result = await self._extract(url)
            
            extracted.append({
                "title": result.get("title", ""),
                "url": url,
                "snippet": result.get("snippet", ""),
                "content": extract_result.content if extract_result.ok else f"[Error: {extract_result.error_message}]",
                "success": extract_result.ok,
            })
        
        # Format combined results
        formatted = self._format_extracted_results(query, extracted)
        
        return ToolResult.success(
            content=formatted,
            metadata={
                "query": query,
                "result_count": len(extracted),
                "action": "search_and_extract"
            }
        )
    
    def _format_search_results(self, results: List[Dict]) -> str:
        """Format search results for display."""
        lines = ["## Search Results\n"]
        
        for i, result in enumerate(results, 1):
            lines.append(f"### {i}. {result['title']}")
            lines.append(f"**URL:** {result['url']}")
            lines.append(f"**Snippet:** {result['snippet']}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_extracted_results(self, query: str, results: List[Dict]) -> str:
        """Format extracted results for display."""
        lines = [f"## Search Results for: {query}\n"]
        
        for i, result in enumerate(results, 1):
            lines.append(f"### {i}. {result['title']}")
            lines.append(f"**URL:** {result['url']}")
            lines.append(f"**Snippet:** {result['snippet']}")
            lines.append("")
            lines.append("**Extracted Content:**")
            lines.append(result['content'][:2000])  # Limit per-result content
            lines.append("")
            lines.append("---\n")
        
        return "\n".join(lines)
    
    def _is_text_content(self, content_type: str) -> bool:
        """Check if content type is text-based."""
        text_types = [
            "text/html",
            "text/plain",
            "text/xml",
            "application/json",
            "application/xml",
            "application/xhtml+xml",
        ]
        return any(t in content_type.lower() for t in text_types)
    
    def _is_html_content(self, content_type: str) -> bool:
        """Check if content type is HTML."""
        html_types = ["text/html", "application/xhtml+xml"]
        return any(t in content_type.lower() for t in html_types)
    
    def _truncate_content(self, content: str, max_chars: int = 10000) -> str:
        """Truncate content to maximum characters."""
        if len(content) <= max_chars:
            return content
        
        return content[:max_chars] + "\n\n... [Content truncated]"


__all__ = ["WebTool"]
