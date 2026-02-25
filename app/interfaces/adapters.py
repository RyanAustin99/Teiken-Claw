"""
Interface adapters for converting between Telegram and internal formats.

This module provides:
- TelegramAdapter class for message conversion
- Telegram to Job conversion
- Internal response to Telegram format conversion
- MarkdownV2 formatting utilities
"""

import re
from typing import Optional, Dict, Any
from datetime import datetime

from app.config.logging import get_logger
from app.queue.jobs import Job, JobSource, JobType, JobPriority, create_job

logger = get_logger(__name__)


class TelegramAdapter:
    """
    Adapter for converting between Telegram and internal formats.
    
    Handles:
    - Telegram messages to Job format
    - Internal responses to Telegram format
    - MarkdownV2 escaping
    - Message chunking
    
    Attributes:
        chat_id: Current chat ID
        user_id: Current user ID
    """
    
    def __init__(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ):
        """
        Initialize the adapter.
        
        Args:
            chat_id: Optional default chat ID
            user_id: Optional default user ID
        """
        self.chat_id = chat_id
        self.user_id = user_id
    
    # =========================================================================
    # Telegram to Internal Conversion
    # =========================================================================
    
    def message_to_job(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        message_id: Optional[int] = None,
        reply_to_id: Optional[int] = None,
    ) -> Job:
        """
        Convert a Telegram message to a Job.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            text: Message text
            message_id: Optional Telegram message ID
            reply_to_id: Optional message ID being replied to
        
        Returns:
            Job: Created job ready for enqueueing
        """
        payload = {
            "text": text,
            "user_id": user_id,
            "message_id": message_id,
            "reply_to_id": reply_to_id,
            "source": "telegram",
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        job = create_job(
            source=JobSource.TELEGRAM,
            type=JobType.CHAT_MESSAGE,
            payload=payload,
            priority=JobPriority.INTERACTIVE,
            chat_id=str(chat_id),
        )
        
        logger.debug(
            f"Converted Telegram message to job {job.job_id}",
            extra={
                "event": "message_to_job",
                "job_id": job.job_id,
                "chat_id": chat_id,
                "user_id": user_id,
            }
        )
        
        return job
    
    def update_to_job(
        self,
        update: Dict[str, Any],
    ) -> Optional[Job]:
        """
        Convert a Telegram update dict to a Job.
        
        Args:
            update: Telegram update dictionary
        
        Returns:
            Job: Created job or None if not a message
        """
        message = update.get("message")
        if not message:
            return None
        
        chat = message.get("chat", {})
        user = message.get("from", {})
        text = message.get("text")
        
        if not text:
            return None
        
        return self.message_to_job(
            chat_id=chat.get("id"),
            user_id=user.get("id"),
            text=text,
            message_id=message.get("message_id"),
            reply_to_id=message.get("reply_to_message", {}).get("message_id"),
        )
    
    # =========================================================================
    # Internal to Telegram Conversion
    # =========================================================================
    
    def response_to_telegram(
        self,
        response: Dict[str, Any],
        parse_mode: str = "MarkdownV2",
    ) -> Dict[str, Any]:
        """
        Convert an internal response to Telegram format.
        
        Args:
            response: Internal response dictionary
            parse_mode: Parse mode for formatting (MarkdownV2, HTML, Markdown)
        
        Returns:
            Dict: Telegram message parameters
        """
        text = response.get("text", "")
        
        # Apply formatting based on parse mode
        if parse_mode == "MarkdownV2":
            text = self.escape_markdown_v2(text)
        elif parse_mode == "HTML":
            text = self.escape_html(text)
        
        return {
            "text": text,
            "parse_mode": parse_mode,
        }
    
    def format_response(
        self,
        text: str,
        parse_mode: str = "MarkdownV2",
    ) -> str:
        """
        Format response text for Telegram.
        
        Args:
            text: Response text
            parse_mode: Parse mode for formatting
        
        Returns:
            str: Formatted text
        """
        if parse_mode == "MarkdownV2":
            return self.escape_markdown_v2(text)
        elif parse_mode == "HTML":
            return self.escape_html(text)
        return text
    
    # =========================================================================
    # MarkdownV2 Escaping
    # =========================================================================
    
    # Characters that need escaping in MarkdownV2
    MARKDOWN_V2_SPECIAL_CHARS = [
        '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    
    @classmethod
    def escape_markdown_v2(cls, text: str) -> str:
        """
        Escape text for Telegram MarkdownV2 format.
        
        MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
        
        Args:
            text: Text to escape
        
        Returns:
            str: Escaped text safe for MarkdownV2
        """
        # Escape special characters with backslash
        for char in cls.MARKDOWN_V2_SPECIAL_CHARS:
            text = text.replace(char, f"\\{char}")
        
        return text
    
    @classmethod
    def escape_markdown_v2_preserve_code(cls, text: str) -> str:
        """
        Escape text for MarkdownV2 while preserving code blocks.
        
        Code blocks (```...```) and inline code (`...`) are not escaped inside.
        
        Args:
            text: Text to escape
        
        Returns:
            str: Escaped text with preserved code blocks
        """
        # Split by code blocks
        parts = []
        current = ""
        in_code_block = False
        in_inline_code = False
        i = 0
        
        while i < len(text):
            # Check for code block
            if text[i:i+3] == "```":
                if not in_inline_code:
                    if in_code_block:
                        # End of code block
                        parts.append(current)
                        current = "```"
                        i += 3
                        # Find end of code block
                        end = text.find("```", i)
                        if end == -1:
                            current += text[i:]
                            i = len(text)
                        else:
                            current += text[i:end+3]
                            i = end + 3
                        parts.append(current)
                        current = ""
                        in_code_block = False
                        continue
                    else:
                        # Start of code block
                        parts.append(cls.escape_markdown_v2(current))
                        current = "```"
                        i += 3
                        in_code_block = True
                        continue
            
            # Check for inline code
            if text[i] == "`" and not in_code_block:
                if in_inline_code:
                    # End of inline code
                    current += "`"
                    parts.append(current)
                    current = ""
                    in_inline_code = False
                else:
                    # Start of inline code
                    parts.append(cls.escape_markdown_v2(current))
                    current = "`"
                    in_inline_code = True
                i += 1
                continue
            
            current += text[i]
            i += 1
        
        # Add remaining text
        if current:
            if in_code_block or in_inline_code:
                parts.append(current)
            else:
                parts.append(cls.escape_markdown_v2(current))
        
        return "".join(parts)
    
    @classmethod
    def escape_html(cls, text: str) -> str:
        """
        Escape text for HTML format.
        
        Args:
            text: Text to escape
        
        Returns:
            str: HTML-escaped text
        """
        escaped = text.replace("&", "&amp;")
        # Keep angle brackets for Telegram HTML mode while neutralizing script tags.
        escaped = re.sub(r"(?i)<\s*script\b", "<scr&#105;pt", escaped)
        escaped = re.sub(r"(?i)<\s*/\s*script\s*>", "</scr&#105;pt>", escaped)
        return escaped
    
    # =========================================================================
    # Message Formatting Helpers
    # =========================================================================
    
    @classmethod
    def format_bold(cls, text: str, parse_mode: str = "MarkdownV2") -> str:
        """Format text as bold."""
        if parse_mode == "MarkdownV2":
            return f"*{cls.escape_markdown_v2(text)}*"
        elif parse_mode == "HTML":
            return f"<b>{cls.escape_html(text)}</b>"
        elif parse_mode == "Markdown":
            return f"*{text}*"
        return text
    
    @classmethod
    def format_italic(cls, text: str, parse_mode: str = "MarkdownV2") -> str:
        """Format text as italic."""
        if parse_mode == "MarkdownV2":
            return f"_{cls.escape_markdown_v2(text)}_"
        elif parse_mode == "HTML":
            return f"<i>{cls.escape_html(text)}</i>"
        elif parse_mode == "Markdown":
            return f"_{text}_"
        return text
    
    @classmethod
    def format_code(cls, text: str, parse_mode: str = "MarkdownV2") -> str:
        """Format text as inline code."""
        if parse_mode == "MarkdownV2":
            return f"`{text}`"
        elif parse_mode == "HTML":
            return f"<code>{cls.escape_html(text)}</code>"
        elif parse_mode == "Markdown":
            return f"`{text}`"
        return text
    
    @classmethod
    def format_code_block(
        cls,
        code: str,
        language: str = "",
        parse_mode: str = "MarkdownV2"
    ) -> str:
        """Format text as a code block."""
        if parse_mode in ("MarkdownV2", "Markdown"):
            return f"```{language}\n{code}\n```"
        elif parse_mode == "HTML":
            return f"<pre><code class=\"{language}\">{cls.escape_html(code)}</code></pre>"
        return code
    
    @classmethod
    def format_link(
        cls,
        text: str,
        url: str,
        parse_mode: str = "MarkdownV2"
    ) -> str:
        """Format a link."""
        if parse_mode == "MarkdownV2":
            return f"[{cls.escape_markdown_v2(text)}]({url})"
        elif parse_mode == "HTML":
            return f'<a href="{url}">{cls.escape_html(text)}</a>'
        elif parse_mode == "Markdown":
            return f"[{text}]({url})"
        return text
    
    @classmethod
    def format_user_mention(
        cls,
        user_id: int,
        name: str,
        parse_mode: str = "MarkdownV2"
    ) -> str:
        """Format a user mention."""
        if parse_mode == "MarkdownV2":
            return f"[{cls.escape_markdown_v2(name)}](tg://user?id={user_id})"
        elif parse_mode == "HTML":
            return f'<a href="tg://user?id={user_id}">{cls.escape_html(name)}</a>'
        elif parse_mode == "Markdown":
            return f"[{name}](tg://user?id={user_id})"
        return name
    
    # =========================================================================
    # Message Validation
    # =========================================================================
    
    @classmethod
    def validate_message_length(cls, text: str, max_length: int = 4096) -> bool:
        """
        Validate message length.
        
        Args:
            text: Message text
            max_length: Maximum allowed length (default: 4096)
        
        Returns:
            bool: True if message is within limits
        """
        return len(text) <= max_length
    
    @classmethod
    def truncate_message(
        cls,
        text: str,
        max_length: int = 4096,
        suffix: str = "... (truncated)"
    ) -> str:
        """
        Truncate a message to fit within limits.
        
        Args:
            text: Message text
            max_length: Maximum allowed length
            suffix: Suffix to add when truncated
        
        Returns:
            str: Truncated message
        """
        if len(text) <= max_length:
            return text
        
        # Account for suffix length
        truncate_at = max_length - len(suffix)
        return text[:truncate_at] + suffix
    
    @classmethod
    def split_message(
        cls,
        text: str,
        max_length: int = 4096
    ) -> list:
        """
        Split a message into chunks at safe boundaries.
        
        Args:
            text: Message text
            max_length: Maximum chunk length
        
        Returns:
            list: List of message chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        remaining = text
        
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            
            # Find a safe split point
            split_point = cls._find_split_point(remaining, max_length)
            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()
        
        return chunks
    
    @classmethod
    def _find_split_point(cls, text: str, max_length: int) -> int:
        """Find a safe point to split text."""
        search_text = text[:max_length]
        
        # Try double newline first
        pos = search_text.rfind("\n\n")
        if pos > max_length // 2:
            return pos + 2
        
        # Try single newline
        pos = search_text.rfind("\n")
        if pos > max_length // 2:
            return pos + 1
        
        # Try space
        pos = search_text.rfind(" ")
        if pos > max_length // 2:
            return pos + 1
        
        # Hard split
        return max_length


# =============================================================================
# Convenience Functions
# =============================================================================

def escape_markdown_v2(text: str) -> str:
    """Escape text for Telegram MarkdownV2 format."""
    return TelegramAdapter.escape_markdown_v2(text)


def escape_html(text: str) -> str:
    """Escape text for HTML format."""
    return TelegramAdapter.escape_html(text)


def format_for_telegram(
    text: str,
    parse_mode: str = "MarkdownV2"
) -> str:
    """Format text for Telegram based on parse mode."""
    return TelegramAdapter().format_response(text, parse_mode)


__all__ = [
    "TelegramAdapter",
    "escape_markdown_v2",
    "escape_html",
    "format_for_telegram",
]
