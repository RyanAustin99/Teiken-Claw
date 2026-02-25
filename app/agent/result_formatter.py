"""
Response formatting for the Teiken Claw agent.

This module provides functions for formatting agent responses
for different output channels (Telegram, CLI, etc.).

Key Features:
    - Telegram Markdown formatting
    - CLI plain text formatting
    - Long response chunking
"""

import re
from typing import List, Optional, Tuple


# Maximum message lengths
TELEGRAM_MAX_LENGTH = 4096
CLI_MAX_LENGTH = 10000
DEFAULT_CHUNK_SIZE = 4000


def format_response(
    response: str,
    channel: str = "cli",
    max_length: Optional[int] = None,
) -> str:
    """
    Format a response for a specific channel.
    
    Args:
        response: Raw response text
        channel: Output channel ('telegram', 'cli')
        max_length: Optional maximum length
        
    Returns:
        Formatted response string
    """
    if channel == "telegram":
        return format_for_telegram(response, max_length)
    else:
        return format_for_cli(response, max_length)


def format_for_telegram(
    text: str,
    max_length: Optional[int] = None,
) -> str:
    """
    Format text for Telegram Markdown.
    
    Telegram uses a specific Markdown variant that needs careful handling.
    
    Args:
        text: Raw text to format
        max_length: Maximum length (default: TELEGRAM_MAX_LENGTH)
        
    Returns:
        Telegram-formatted text
    """
    max_len = max_length or TELEGRAM_MAX_LENGTH
    
    # Escape special characters for Telegram MarkdownV2
    # Characters that need escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escaped = _escape_telegram_markdown(text)
    
    # Truncate if needed
    if len(escaped) > max_len:
        escaped = escaped[:max_len - 3] + "..."
    
    return escaped


def _escape_telegram_markdown(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    # Characters that need escaping in MarkdownV2
    special_chars = r'_*[]()~`>#+-=|{}.!'
    
    # Escape backslash first
    text = text.replace('\\', '\\\\')
    
    # Escape other special characters
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def format_for_cli(
    text: str,
    max_length: Optional[int] = None,
) -> str:
    """
    Format text for CLI output.
    
    Args:
        text: Raw text to format
        max_length: Maximum length (default: CLI_MAX_LENGTH)
        
    Returns:
        CLI-formatted text
    """
    max_len = max_length or CLI_MAX_LENGTH
    
    # Clean up whitespace
    text = text.strip()
    
    # Truncate if needed
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    
    return text


def chunk_response(
    response: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    respect_boundaries: bool = True,
) -> List[str]:
    """
    Split a long response into chunks.
    
    Args:
        response: Response text to chunk
        chunk_size: Maximum size per chunk
        respect_boundaries: Try to split at sentence/paragraph boundaries
        
    Returns:
        List of response chunks
    """
    if len(response) <= chunk_size:
        return [response]
    
    chunks = []
    remaining = response
    
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        
        # Find a good split point
        if respect_boundaries:
            split_point = _find_split_point(remaining, chunk_size)
        else:
            split_point = chunk_size
        
        chunk = remaining[:split_point].strip()
        if chunk:
            chunks.append(chunk)
        
        remaining = remaining[split_point:].strip()
    
    return chunks


def _find_split_point(text: str, max_pos: int) -> int:
    """
    Find a good position to split text.
    
    Tries to split at (in order of preference):
    1. Paragraph boundary
    2. Sentence boundary
    3. Word boundary
    4. Hard split
    
    Args:
        text: Text to find split point in
        max_pos: Maximum position for split
        
    Returns:
        Position to split at
    """
    search_text = text[:max_pos]
    
    # Try paragraph break (double newline)
    para_match = search_text.rfind('\n\n')
    if para_match > max_pos // 2:
        return para_match + 2
    
    # Try single newline
    newline_match = search_text.rfind('\n')
    if newline_match > max_pos // 2:
        return newline_match + 1
    
    # Try sentence end (. ! ?)
    sentence_pattern = r'[.!?]\s+'
    matches = list(re.finditer(sentence_pattern, search_text))
    if matches:
        last_match = matches[-1]
        if last_match.end() > max_pos // 2:
            return last_match.end()
    
    # Try word boundary
    space_match = search_text.rfind(' ')
    if space_match > max_pos // 2:
        return space_match + 1
    
    # Hard split
    return max_pos


def format_tool_result_for_display(
    tool_name: str,
    result: str,
    success: bool = True,
) -> str:
    """
    Format a tool result for display in conversation.
    
    Args:
        tool_name: Name of the tool
        result: Tool result content
        success: Whether the tool succeeded
        
    Returns:
        Formatted tool result string
    """
    status = "✓" if success else "✗"
    header = f"[{status} {tool_name}]"
    
    # Truncate long results
    if len(result) > 500:
        result = result[:497] + "..."
    
    return f"{header}\n{result}"


def format_error_response(
    error_message: str,
    error_code: Optional[str] = None,
) -> str:
    """
    Format an error response for display.
    
    Args:
        error_message: Human-readable error message
        error_code: Optional error code
        
    Returns:
        Formatted error string
    """
    if error_code:
        return f"Error ({error_code}): {error_message}"
    return f"Error: {error_message}"


def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Extract code blocks from text.
    
    Args:
        text: Text containing code blocks
        
    Returns:
        List of (language, code) tuples
    """
    pattern = r'```(\w*)\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    return [(lang or "text", code.strip()) for lang, code in matches]


__all__ = [
    "TELEGRAM_MAX_LENGTH",
    "CLI_MAX_LENGTH",
    "DEFAULT_CHUNK_SIZE",
    "format_response",
    "format_for_telegram",
    "format_for_cli",
    "chunk_response",
    "format_tool_result_for_display",
    "format_error_response",
    "extract_code_blocks",
]
