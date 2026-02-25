"""
Telegram message sender for Teiken Claw.

This module provides:
- TelegramSender class for sending messages
- Retry logic for rate limits (429) and network errors
- Chunked message support for long messages
- Integration with OutboundQueue
"""

import asyncio
import re
from datetime import datetime
from typing import Optional, List, Callable, Any

from app.config.logging import get_logger
from app.config.settings import settings
from app.queue.throttles import OutboundQueue, get_outbound_queue

logger = get_logger(__name__)

# Try to import telegram bot library
try:
    from telegram import Bot
    from telegram.error import TelegramError, RetryAfter, NetworkError, TimedOut
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Bot = None
    TelegramError = Exception
    RetryAfter = Exception
    NetworkError = Exception
    TimedOut = Exception
    logger.warning(
        "python-telegram-bot not installed, TelegramSender will use placeholder",
        extra={"event": "telegram_import_failed"}
    )


class TelegramSender:
    """
    Telegram message sender with retry logic and rate limiting.
    
    Features:
    - Send messages via Telegram Bot API
    - Retry on 429 (rate limit) with retry-after respect
    - Retry on network errors with exponential backoff
    - Chunk long messages automatically
    - Integration with OutboundQueue
    
    Attributes:
        bot: Telegram Bot instance
        is_running: Whether the sender loop is running
    """
    
    # Telegram message length limit
    MAX_MESSAGE_LENGTH = 4096
    
    # Retry configuration
    MAX_RETRIES = 5
    BASE_RETRY_DELAY = 1.0
    MAX_RETRY_DELAY = 60.0
    
    def __init__(
        self,
        token: Optional[str] = None,
        outbound_queue: Optional[OutboundQueue] = None,
    ):
        """
        Initialize the Telegram sender.
        
        Args:
            token: Telegram bot token (defaults to settings.TELEGRAM_BOT_TOKEN)
            outbound_queue: Optional OutboundQueue instance
        """
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self._outbound_queue = outbound_queue
        self._bot: Optional[Any] = None
        self._running = False
        self._sender_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self._total_sent = 0
        self._total_failed = 0
        self._total_retries = 0
        self._total_chunks = 0
        
        if not HAS_TELEGRAM:
            logger.warning(
                "TelegramSender created but python-telegram-bot not available",
                extra={"event": "telegram_sender_unavailable"}
            )
            return
        
        if not self.token:
            logger.warning(
                "TelegramSender created but no token configured",
                extra={"event": "telegram_sender_no_token"}
            )
            return
        
        # Create bot instance
        self._bot = Bot(token=self.token)
        
        logger.info(
            "TelegramSender initialized",
            extra={"event": "telegram_sender_initialized"}
        )
    
    @property
    def is_running(self) -> bool:
        """Check if the sender loop is running."""
        return self._running
    
    @property
    def stats(self) -> dict:
        """Get sender statistics."""
        return {
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "total_retries": self._total_retries,
            "total_chunks": self._total_chunks,
            "is_running": self._running,
        }
    
    async def start_sender_loop(self) -> None:
        """
        Start the sender loop that pulls from outbound queue.
        
        This method runs continuously until stop_sender() is called.
        """
        if self._running:
            logger.warning(
                "TelegramSender loop already running",
                extra={"event": "sender_already_running"}
            )
            return
        
        if not self._outbound_queue:
            # Try to get the global outbound queue
            self._outbound_queue = get_outbound_queue()
        
        if not self._outbound_queue:
            logger.warning(
                "No outbound queue available for sender loop",
                extra={"event": "sender_no_queue"}
            )
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        logger.info(
            "Starting TelegramSender loop",
            extra={"event": "sender_loop_starting"}
        )
        
        # Set the sender callback on the outbound queue
        self._outbound_queue._telegram_sender = self.send_message
        
        logger.info(
            "TelegramSender loop started (sender attached to outbound queue)",
            extra={"event": "sender_loop_started"}
        )
    
    async def stop_sender(self, timeout: float = 30.0) -> None:
        """
        Stop the sender loop gracefully.
        
        Args:
            timeout: Maximum time to wait for pending messages
        """
        if not self._running:
            return
        
        self._running = False
        self._shutdown_event.set()
        
        # Wait for sender task to finish
        if self._sender_task and not self._sender_task.done():
            try:
                await asyncio.wait_for(self._sender_task, timeout=timeout)
            except asyncio.TimeoutError:
                self._sender_task.cancel()
                try:
                    await self._sender_task
                except asyncio.CancelledError:
                    pass
        
        logger.info(
            "TelegramSender loop stopped",
            extra={"event": "sender_loop_stopped"}
        )
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
    ) -> bool:
        """
        Send a message via Telegram API with retry logic.
        
        Args:
            chat_id: Target Telegram chat ID
            text: Message text to send
            parse_mode: Optional parse mode (HTML, Markdown, MarkdownV2)
            reply_to_message_id: Optional message ID to reply to
            disable_notification: Whether to send silently
        
        Returns:
            bool: True if sent successfully
        
        Raises:
            Exception: If message fails after all retries
        """
        if not HAS_TELEGRAM or not self._bot:
            logger.warning(
                f"[PLACEHOLDER] Would send to chat {chat_id}: {text[:50]}...",
                extra={
                    "event": "sender_placeholder",
                    "chat_id": chat_id,
                    "text_length": len(text),
                }
            )
            self._total_sent += 1
            return True
        
        # Check if message needs to be chunked
        if len(text) > self.MAX_MESSAGE_LENGTH:
            return await self.send_chunked_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id,
                disable_notification=disable_notification,
            )
        
        return await self._send_with_retry(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )
    
    async def send_chunked_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
    ) -> bool:
        """
        Send a long message in chunks.
        
        Splits the message at safe boundaries (newlines, spaces) to avoid
        breaking formatting.
        
        Args:
            chat_id: Target Telegram chat ID
            text: Message text to send
            parse_mode: Optional parse mode
            reply_to_message_id: Optional message ID to reply to
            disable_notification: Whether to send silently
        
        Returns:
            bool: True if all chunks sent successfully
        """
        chunks = self._split_message(text)
        all_success = True
        
        for i, chunk in enumerate(chunks):
            # Only reply to the first chunk
            reply_id = reply_to_message_id if i == 0 else None
            
            success = await self._send_with_retry(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                reply_to_message_id=reply_id,
                disable_notification=disable_notification,
            )
            
            if success:
                self._total_chunks += 1
            else:
                all_success = False
            
            # Small delay between chunks to avoid rate limiting
            if i < len(chunks) - 1:
                await asyncio.sleep(0.1)
        
        return all_success
    
    def _split_message(self, text: str) -> List[str]:
        """
        Split a long message into chunks at safe boundaries.
        
        Args:
            text: Message text to split
        
        Returns:
            List[str]: List of message chunks
        """
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return [text]
        
        chunks = []
        remaining = text
        
        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break
            
            # Find a safe split point
            split_point = self._find_split_point(remaining, self.MAX_MESSAGE_LENGTH)
            
            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()
        
        logger.debug(
            f"Split message into {len(chunks)} chunks",
            extra={
                "event": "message_split",
                "chunk_count": len(chunks),
                "original_length": len(text),
            }
        )
        
        return chunks
    
    def _find_split_point(self, text: str, max_length: int) -> int:
        """
        Find a safe point to split text.
        
        Tries to split at (in order of preference):
        1. Double newline (paragraph break)
        2. Single newline (line break)
        3. Space (word break)
        4. Hard split at max_length
        
        Args:
            text: Text to find split point in
            max_length: Maximum length for this chunk
        
        Returns:
            int: Index to split at
        """
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
    
    async def _send_with_retry(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
    ) -> bool:
        """
        Send a message with retry logic.
        
        Handles:
        - 429 (rate limit) with retry-after
        - Network errors with exponential backoff
        - Timeout errors
        
        Args:
            chat_id: Target Telegram chat ID
            text: Message text to send
            parse_mode: Optional parse mode
            reply_to_message_id: Optional message ID to reply to
            disable_notification: Whether to send silently
        
        Returns:
            bool: True if sent successfully
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    disable_notification=disable_notification,
                )
                
                self._total_sent += 1
                
                logger.debug(
                    f"Message sent to chat {chat_id}",
                    extra={
                        "event": "message_sent",
                        "chat_id": chat_id,
                        "attempt": attempt + 1,
                    }
                )
                
                return True
                
            except RetryAfter as e:
                # Rate limited - wait the specified time
                retry_after = e.retry_after
                self._total_retries += 1
                
                logger.warning(
                    f"Rate limited, retrying after {retry_after}s",
                    extra={
                        "event": "rate_limited",
                        "chat_id": chat_id,
                        "retry_after": retry_after,
                        "attempt": attempt + 1,
                    }
                )
                
                await asyncio.sleep(retry_after)
                continue
                
            except (NetworkError, TimedOut) as e:
                # Network error - exponential backoff
                self._total_retries += 1
                last_error = e
                
                delay = min(
                    self.BASE_RETRY_DELAY * (2 ** attempt),
                    self.MAX_RETRY_DELAY
                )
                
                logger.warning(
                    f"Network error, retrying in {delay}s: {e}",
                    extra={
                        "event": "network_error",
                        "chat_id": chat_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "delay": delay,
                    }
                )
                
                await asyncio.sleep(delay)
                continue
                
            except TelegramError as e:
                # Other Telegram errors - check if retryable
                error_str = str(e)
                
                # Check for rate limit in error message
                if "429" in error_str or "Too Many Requests" in error_str:
                    # Try to extract retry-after
                    match = re.search(r"retry after (\d+)", error_str, re.IGNORECASE)
                    retry_after = int(match.group(1)) if match else 30
                    
                    self._total_retries += 1
                    
                    logger.warning(
                        f"Rate limited (from error), retrying after {retry_after}s",
                        extra={
                            "event": "rate_limited_from_error",
                            "chat_id": chat_id,
                            "retry_after": retry_after,
                            "attempt": attempt + 1,
                        }
                    )
                    
                    await asyncio.sleep(retry_after)
                    continue
                
                # Non-retryable error
                self._total_failed += 1
                
                logger.error(
                    f"Telegram error (non-retryable): {e}",
                    extra={
                        "event": "telegram_error",
                        "chat_id": chat_id,
                        "error": str(e),
                    }
                )
                
                return False
        
        # All retries exhausted
        self._total_failed += 1
        
        logger.error(
            f"Failed to send message after {self.MAX_RETRIES} attempts",
            extra={
                "event": "send_failed",
                "chat_id": chat_id,
                "last_error": str(last_error) if last_error else None,
            }
        )
        
        return False
    
    async def send_typing_action(self, chat_id: str) -> bool:
        """
        Send typing action to a chat.
        
        Args:
            chat_id: Target Telegram chat ID
        
        Returns:
            bool: True if action sent successfully
        """
        if not HAS_TELEGRAM or not self._bot:
            return True  # Placeholder
        
        try:
            await self._bot.send_chat_action(
                chat_id=chat_id,
                action="typing",
            )
            return True
        except Exception as e:
            logger.debug(
                f"Failed to send typing action: {e}",
                extra={"event": "typing_action_failed", "chat_id": chat_id}
            )
            return False


# =============================================================================
# Global Instance Management
# =============================================================================

_telegram_sender: Optional[TelegramSender] = None


def get_telegram_sender() -> Optional[TelegramSender]:
    """Get the global TelegramSender instance."""
    return _telegram_sender


def set_telegram_sender(sender: Optional[TelegramSender]) -> None:
    """Set the global TelegramSender instance."""
    global _telegram_sender
    _telegram_sender = sender


__all__ = [
    "TelegramSender",
    "HAS_TELEGRAM",
    "get_telegram_sender",
    "set_telegram_sender",
]
