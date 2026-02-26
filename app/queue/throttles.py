from __future__ import annotations

"""
Rate limiting and outbound queue for Telegram messages.

This module provides:
- RateLimiter class using aiolimiter
- Global and per-chat rate limiting
- OutboundQueue for Telegram message sending
- Retry logic with 429 handling
- Dead-letter integration for failed messages
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    from aiolimiter import Limiter
    HAS_AIOLIMITER = True
except ImportError:
    # Keep annotation/runtime references valid in environments without aiolimiter.
    Limiter = Any  # type: ignore[assignment,misc]
    HAS_AIOLIMITER = False

from app.config.logging import get_logger
from app.config.settings import settings

logger = get_logger(__name__)


class MessageStatus(str, Enum):
    """Status of an outbound message."""
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    DEAD_LETTER = "dead_letter"


@dataclass
class OutboundMessage:
    """A message to be sent via Telegram."""
    message_id: str
    chat_id: str
    text: str
    parse_mode: Optional[str] = None
    reply_to_message_id: Optional[int] = None
    disable_notification: bool = False
    status: MessageStatus = MessageStatus.PENDING
    attempts: int = 0
    max_attempts: int = 5
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_attempt_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_after: Optional[int] = None  # Seconds to wait before retry
    
    def increment_attempt(self) -> "OutboundMessage":
        """Return a new message with attempts incremented."""
        return OutboundMessage(
            message_id=self.message_id,
            chat_id=self.chat_id,
            text=self.text,
            parse_mode=self.parse_mode,
            reply_to_message_id=self.reply_to_message_id,
            disable_notification=self.disable_notification,
            status=self.status,
            attempts=self.attempts + 1,
            max_attempts=self.max_attempts,
            created_at=self.created_at,
            last_attempt_at=datetime.utcnow(),
            error_message=self.error_message,
            retry_after=None,
        )
    
    def can_retry(self) -> bool:
        """Check if this message can be retried."""
        return self.attempts < self.max_attempts


class RateLimiter:
    """
    Rate limiter using aiolimiter (token bucket algorithm).
    
    Provides both global and per-chat rate limiting for Telegram API.
    
    Attributes:
        global_rate: Global messages per second limit
        per_chat_rate: Per-chat messages per second limit
    """
    
    def __init__(
        self,
        global_rate: float = 30.0,
        per_chat_rate: float = 1.0,
    ):
        """
        Initialize the rate limiter.
        
        Args:
            global_rate: Maximum global messages per second
            per_chat_rate: Maximum messages per second per chat
        """
        self.global_rate = global_rate
        self.per_chat_rate = per_chat_rate
        
        # Create limiters if aiolimiter is available
        if HAS_AIOLIMITER:
            # Global limiter: allows burst up to 2x the rate
            self._global_limiter = Limiter(
                max_rate=global_rate,
                time_period=1.0,
                burst_factor=2.0,
            )
            
            # Per-chat limiters (created on demand)
            self._chat_limiters: Dict[str, Limiter] = {}
            self._chat_lock = asyncio.Lock()
        else:
            # Fallback: simple delay-based rate limiting
            self._global_limiter = None
            self._last_global_send: Optional[datetime] = None
            self._last_chat_send: Dict[str, datetime] = {}
            self._chat_lock = asyncio.Lock()
            logger.warning(
                "aiolimiter not installed, using simple delay-based rate limiting",
                extra={"event": "rate_limiter_fallback"}
            )
        
        logger.info(
            f"RateLimiter initialized: global={global_rate}/s, per_chat={per_chat_rate}/s",
            extra={"event": "rate_limiter_initialized"}
        )
    
    async def _get_or_create_chat_limiter(self, chat_id: str) -> Optional[Limiter]:
        """Get or create a rate limiter for a specific chat."""
        if not HAS_AIOLIMITER:
            return None
        
        async with self._chat_lock:
            if chat_id not in self._chat_limiters:
                self._chat_limiters[chat_id] = Limiter(
                    max_rate=self.per_chat_rate,
                    time_period=1.0,
                    burst_factor=1.5,
                )
            return self._chat_limiters[chat_id]
    
    async def acquire_global(self) -> None:
        """
        Acquire the global rate limit token.
        
        Waits if necessary to comply with the global rate limit.
        """
        if HAS_AIOLIMITER and self._global_limiter:
            await self._global_limiter.acquire()
        else:
            # Fallback: simple delay
            if self._last_global_send:
                min_interval = 1.0 / self.global_rate
                elapsed = (datetime.utcnow() - self._last_global_send).total_seconds()
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
            self._last_global_send = datetime.utcnow()
    
    async def acquire_chat(self, chat_id: str) -> None:
        """
        Acquire the per-chat rate limit token.
        
        Args:
            chat_id: The chat ID to rate limit for
        
        Waits if necessary to comply with the per-chat rate limit.
        """
        if HAS_AIOLIMITER:
            limiter = await self._get_or_create_chat_limiter(chat_id)
            if limiter:
                await limiter.acquire()
        else:
            # Fallback: simple delay
            async with self._chat_lock:
                if chat_id in self._last_chat_send:
                    min_interval = 1.0 / self.per_chat_rate
                    elapsed = (datetime.utcnow() - self._last_chat_send[chat_id]).total_seconds()
                    if elapsed < min_interval:
                        await asyncio.sleep(min_interval - elapsed)
                self._last_chat_send[chat_id] = datetime.utcnow()
    
    async def acquire(self, chat_id: str) -> None:
        """
        Acquire both global and per-chat rate limits.
        
        Args:
            chat_id: The chat ID to rate limit for
        """
        await self.acquire_global()
        await self.acquire_chat(chat_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        stats = {
            "global_rate": self.global_rate,
            "per_chat_rate": self.per_chat_rate,
            "has_aiolimiter": HAS_AIOLIMITER,
        }
        
        if HAS_AIOLIMITER and self._global_limiter:
            stats["active_chats"] = len(self._chat_limiters)
        
        return stats


class OutboundQueue:
    """
    Queue for outbound Telegram messages with rate limiting.
    
    Features:
    - Priority queue for messages
    - Global and per-chat rate limiting
    - Retry logic for 429 (rate limit) errors
    - Retry logic for transient network errors
    - Dead-letter queue for permanently failed messages
    
    Attributes:
        rate_limiter: RateLimiter instance
        queue: asyncio.Queue for pending messages
    """
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        global_rate: float = 30.0,
        per_chat_rate: float = 1.0,
        max_queue_size: int = 1000,
        max_attempts: int = 5,
        dead_letter_queue: Optional[Any] = None,
        telegram_sender: Optional[callable] = None,
    ):
        """
        Initialize the outbound queue.
        
        Args:
            rate_limiter: Optional RateLimiter instance
            global_rate: Global messages per second limit
            per_chat_rate: Per-chat messages per second limit
            max_queue_size: Maximum queue capacity
            max_attempts: Maximum retry attempts per message
            dead_letter_queue: Optional DeadLetterQueue for failed messages
            telegram_sender: Optional async function to send messages
        """
        self.rate_limiter = rate_limiter or RateLimiter(global_rate, per_chat_rate)
        self.max_queue_size = max_queue_size
        self.max_attempts = max_attempts
        self._dead_letter_queue = dead_letter_queue
        self._telegram_sender = telegram_sender
        
        # Message queue
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        
        # Tracking
        self._pending_messages: Dict[str, OutboundMessage] = {}
        self._sender_task: Optional[asyncio.Task] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self._total_sent = 0
        self._total_failed = 0
        self._total_retries = 0
        
        logger.info(
            f"OutboundQueue initialized: max_size={max_queue_size}, max_attempts={max_attempts}",
            extra={"event": "outbound_queue_initialized"}
        )
    
    @property
    def queue_depth(self) -> int:
        """Current number of messages in the queue."""
        return self._queue.qsize()
    
    @property
    def is_running(self) -> bool:
        """Check if the sender is running."""
        return self._running
    
    async def enqueue_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
    ) -> str:
        """
        Add a message to the outbound queue.
        
        Args:
            chat_id: Target Telegram chat ID
            text: Message text to send
            parse_mode: Optional parse mode (HTML, Markdown, etc.)
            reply_to_message_id: Optional message ID to reply to
            disable_notification: Whether to send silently
        
        Returns:
            str: Message ID for tracking
        
        Raises:
            QueueFullError: If queue is at maximum capacity
        """
        import uuid
        
        message = OutboundMessage(
            message_id=str(uuid.uuid4()),
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
            max_attempts=self.max_attempts,
        )
        
        if self._queue.full():
            logger.error(
                f"Outbound queue full, rejecting message for chat {chat_id}",
                extra={
                    "event": "outbound_queue_full",
                    "chat_id": chat_id,
                    "queue_depth": self.queue_depth,
                }
            )
            raise Exception(f"Outbound queue is full ({self.max_queue_size})")
        
        await self._queue.put(message)
        self._pending_messages[message.message_id] = message
        
        logger.debug(
            f"Message enqueued: {message.message_id} for chat {chat_id}",
            extra={
                "event": "message_enqueued",
                "message_id": message.message_id,
                "chat_id": chat_id,
                "queue_depth": self.queue_depth,
            }
        )
        
        return message.message_id
    
    async def _send_message(self, message: OutboundMessage) -> bool:
        """
        Send a message via Telegram API.
        
        Args:
            message: The message to send
        
        Returns:
            bool: True if sent successfully
        """
        # Apply rate limiting
        await self.rate_limiter.acquire(message.chat_id)
        
        # Update status
        message.status = MessageStatus.SENDING
        message.last_attempt_at = datetime.utcnow()
        
        try:
            if self._telegram_sender:
                # Use provided sender function
                await self._telegram_sender(
                    chat_id=message.chat_id,
                    text=message.text,
                    parse_mode=message.parse_mode,
                    reply_to_message_id=message.reply_to_message_id,
                    disable_notification=message.disable_notification,
                )
            else:
                # Placeholder: log the message
                logger.info(
                    f"[PLACEHOLDER] Would send to chat {message.chat_id}: {message.text[:50]}...",
                    extra={
                        "event": "message_send_placeholder",
                        "message_id": message.message_id,
                        "chat_id": message.chat_id,
                    }
                )
            
            message.status = MessageStatus.SENT
            self._total_sent += 1
            
            logger.info(
                f"Message sent: {message.message_id}",
                extra={
                    "event": "message_sent",
                    "message_id": message.message_id,
                    "chat_id": message.chat_id,
                }
            )
            
            return True
            
        except Exception as e:
            error_str = str(e)
            
            # Check for rate limit (429)
            if "429" in error_str or "rate" in error_str.lower():
                message.status = MessageStatus.RATE_LIMITED
                # Try to extract retry-after from error
                import re
                match = re.search(r"retry after (\d+)", error_str, re.IGNORECASE)
                if match:
                    message.retry_after = int(match.group(1))
                else:
                    message.retry_after = 30  # Default 30 seconds
                
                logger.warning(
                    f"Rate limited sending to chat {message.chat_id}, retry after {message.retry_after}s",
                    extra={
                        "event": "message_rate_limited",
                        "message_id": message.message_id,
                        "chat_id": message.chat_id,
                        "retry_after": message.retry_after,
                    }
                )
            else:
                message.status = MessageStatus.FAILED
                message.error_message = error_str
                
                logger.error(
                    f"Failed to send message {message.message_id}: {e}",
                    extra={
                        "event": "message_send_failed",
                        "message_id": message.message_id,
                        "chat_id": message.chat_id,
                        "error": error_str,
                    }
                )
            
            return False
    
    async def _process_message(self, message: OutboundMessage) -> None:
        """
        Process a single message with retry logic.
        
        Args:
            message: The message to process
        """
        success = await self._send_message(message)
        
        if success:
            # Remove from pending
            self._pending_messages.pop(message.message_id, None)
            return
        
        # Handle retry
        updated_message = message.increment_attempt()
        
        if updated_message.can_retry():
            self._total_retries += 1
            
            # Wait for retry_after if specified, otherwise exponential backoff
            if message.retry_after:
                wait_time = message.retry_after
            else:
                wait_time = min(2 ** message.attempts, 60)  # Max 60 seconds
            
            logger.info(
                f"Retrying message {message.message_id} in {wait_time}s (attempt {updated_message.attempts}/{updated_message.max_attempts})",
                extra={
                    "event": "message_retry",
                    "message_id": message.message_id,
                    "attempt": updated_message.attempts,
                    "wait_time": wait_time,
                }
            )
            
            await asyncio.sleep(wait_time)
            
            # Re-queue for retry
            await self._queue.put(updated_message)
            self._pending_messages[message.message_id] = updated_message
        else:
            # Max attempts reached
            updated_message.status = MessageStatus.DEAD_LETTER
            self._total_failed += 1
            
            logger.error(
                f"Message permanently failed: {message.message_id}",
                extra={
                    "event": "message_dead_letter",
                    "message_id": message.message_id,
                    "chat_id": message.chat_id,
                    "attempts": updated_message.attempts,
                    "error": message.error_message,
                }
            )
            
            # Remove from pending
            self._pending_messages.pop(message.message_id, None)
            
            # Send to dead-letter queue if available
            if self._dead_letter_queue:
                # Create a minimal job-like object for dead-letter
                from app.queue.jobs import Job, JobSource, JobType
                dummy_job = Job(
                    job_id=message.message_id,
                    source=JobSource.TELEGRAM,
                    type=JobType.NOTIFICATION,
                    chat_id=message.chat_id,
                    payload={
                        "text": message.text,
                        "parse_mode": message.parse_mode,
                    },
                )
                await self._dead_letter_queue.add(
                    dummy_job,
                    Exception(message.error_message or "Max retries exceeded"),
                )
    
    async def _sender_loop(self) -> None:
        """Main loop for sending messages."""
        logger.info(
            "OutboundQueue sender started",
            extra={"event": "outbound_sender_started"}
        )
        
        while self._running or not self._queue.empty():
            try:
                # Get next message with timeout
                try:
                    message = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                await self._process_message(message)
                
            except asyncio.CancelledError:
                logger.info(
                    "OutboundQueue sender cancelled",
                    extra={"event": "outbound_sender_cancelled"}
                )
                break
            except Exception as e:
                logger.error(
                    f"Error in sender loop: {e}",
                    extra={"event": "outbound_sender_error"},
                    exc_info=True,
                )
                await asyncio.sleep(0.1)
        
        logger.info(
            "OutboundQueue sender stopped",
            extra={
                "event": "outbound_sender_stopped",
                "total_sent": self._total_sent,
                "total_failed": self._total_failed,
                "total_retries": self._total_retries,
            }
        )
    
    async def start_sender(self) -> None:
        """Start the message sender loop."""
        if self._running:
            logger.warning("OutboundQueue sender already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        self._sender_task = asyncio.create_task(self._sender_loop())
        
        logger.info(
            "OutboundQueue sender starting",
            extra={"event": "outbound_sender_starting"}
        )
    
    async def stop_sender(self, timeout: float = 30.0) -> None:
        """
        Stop the message sender loop.
        
        Args:
            timeout: Maximum time to wait for pending messages
        """
        if not self._running:
            return
        
        logger.info(
            "Stopping OutboundQueue sender",
            extra={
                "event": "outbound_sender_stopping",
                "pending_messages": len(self._pending_messages),
            }
        )
        
        self._running = False
        self._shutdown_event.set()
        
        if self._sender_task:
            try:
                await asyncio.wait_for(self._sender_task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "OutboundQueue sender stop timeout, cancelling",
                    extra={"event": "outbound_sender_stop_timeout"}
                )
                self._sender_task.cancel()
                try:
                    await self._sender_task
                except asyncio.CancelledError:
                    pass
        
        self._sender_task = None
        
        logger.info(
            "OutboundQueue sender stopped",
            extra={"event": "outbound_sender_stopped"}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get outbound queue statistics."""
        return {
            "running": self._running,
            "queue_depth": self.queue_depth,
            "max_queue_size": self.max_queue_size,
            "pending_messages": len(self._pending_messages),
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "total_retries": self._total_retries,
            "rate_limiter": self.rate_limiter.get_stats(),
        }


# Global instances (initialized by main app)
_rate_limiter: Optional[RateLimiter] = None
_outbound_queue: Optional[OutboundQueue] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Set the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


def get_outbound_queue() -> Optional[OutboundQueue]:
    """Get the global outbound queue instance."""
    return _outbound_queue


def set_outbound_queue(queue: OutboundQueue) -> None:
    """Set the global outbound queue instance."""
    global _outbound_queue
    _outbound_queue = queue


__all__ = [
    "RateLimiter",
    "OutboundQueue",
    "OutboundMessage",
    "MessageStatus",
    "get_rate_limiter",
    "set_rate_limiter",
    "get_outbound_queue",
    "set_outbound_queue",
]
