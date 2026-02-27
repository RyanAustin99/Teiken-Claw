"""
Tests for Telegram interface components.

This module tests:
- TelegramAdapter message conversion
- CommandRouter command handling
- TelegramSender retry logic
- Rate limiting
- Chunked messages
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.interfaces.adapters import (
    TelegramAdapter,
    escape_markdown_v2,
    escape_html,
    format_for_telegram,
)
from app.interfaces.telegram_commands import CommandRouter
from app.interfaces.telegram_sender import TelegramSender
from app.queue.jobs import Job, JobSource, JobType, JobPriority


# =============================================================================
# TelegramAdapter Tests
# =============================================================================

class TestTelegramAdapter:
    """Tests for TelegramAdapter class."""
    
    def test_escape_markdown_v2_basic(self):
        """Test basic MarkdownV2 escaping."""
        text = "Hello *world*!"
        escaped = escape_markdown_v2(text)
        assert "\\*" in escaped
        assert "\\!" in escaped
    
    def test_escape_markdown_v2_all_special_chars(self):
        """Test all special characters are escaped."""
        special_chars = "_*[]()~`>#+-=|{}.!"
        escaped = escape_markdown_v2(special_chars)
        
        # All special chars should be escaped
        for char in special_chars:
            assert f"\\{char}" in escaped
    
    def test_escape_markdown_v2_preserves_normal_text(self):
        """Test that normal text is preserved."""
        text = "Hello World 123"
        escaped = escape_markdown_v2(text)
        assert "Hello" in escaped
        assert "World" in escaped
        assert "123" in escaped
    
    def test_escape_html_basic(self):
        """Test basic HTML escaping."""
        text = "<script>alert('xss')</script>"
        escaped = escape_html(text)
        assert "<" in escaped
        assert ">" in escaped
        assert "<script>" not in escaped
    
    def test_escape_html_ampersand(self):
        """Test ampersand escaping."""
        text = "Tom & Jerry"
        escaped = escape_html(text)
        assert "&" in escaped
    
    def test_message_to_job(self):
        """Test converting Telegram message to Job."""
        adapter = TelegramAdapter()
        job = adapter.message_to_job(
            chat_id=12345,
            user_id=67890,
            text="Hello, bot!",
            message_id=1,
        )
        
        assert job.source == JobSource.TELEGRAM
        assert job.type == JobType.CHAT_MESSAGE
        assert job.priority == JobPriority.INTERACTIVE
        assert job.chat_id == "12345"
        assert job.payload["text"] == "Hello, bot!"
        assert job.payload["user_id"] == 67890
    
    def test_message_to_job_with_reply(self):
        """Test converting message with reply context."""
        adapter = TelegramAdapter()
        job = adapter.message_to_job(
            chat_id=12345,
            user_id=67890,
            text="Reply text",
            message_id=2,
            reply_to_id=1,
        )
        
        assert job.payload["reply_to_id"] == 1
    
    def test_format_bold_markdown_v2(self):
        """Test bold formatting for MarkdownV2."""
        text = "Important"
        formatted = TelegramAdapter.format_bold(text, "MarkdownV2")
        assert formatted.startswith("*")
        assert formatted.endswith("*")
    
    def test_format_bold_html(self):
        """Test bold formatting for HTML."""
        text = "Important"
        formatted = TelegramAdapter.format_bold(text, "HTML")
        assert "<b>" in formatted
        assert "</b>" in formatted
    
    def test_format_code_block(self):
        """Test code block formatting."""
        code = "print('hello')"
        formatted = TelegramAdapter.format_code_block(code, "python")
        assert "```python" in formatted
        assert "print('hello')" in formatted
    
    def test_validate_message_length_within_limit(self):
        """Test message length validation within limit."""
        text = "Short message"
        assert TelegramAdapter.validate_message_length(text, 100)
    
    def test_validate_message_length_exceeds_limit(self):
        """Test message length validation exceeds limit."""
        text = "x" * 5000
        assert not TelegramAdapter.validate_message_length(text, 4096)
    
    def test_truncate_message(self):
        """Test message truncation."""
        text = "x" * 5000
        truncated = TelegramAdapter.truncate_message(text, 100)
        assert len(truncated) <= 100
        assert "truncated" in truncated
    
    def test_split_message_short(self):
        """Test splitting short message."""
        text = "Short message"
        chunks = TelegramAdapter.split_message(text, 100)
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_split_message_long(self):
        """Test splitting long message."""
        text = "Line 1\n\nLine 2\n\nLine 3"
        chunks = TelegramAdapter.split_message(text, 10)
        assert len(chunks) > 1
    
    def test_split_message_preserves_paragraphs(self):
        """Test that splitting prefers paragraph breaks."""
        text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        chunks = TelegramAdapter.split_message(text, 20)
        # Should split at paragraph boundaries
        for chunk in chunks:
            assert len(chunk) <= 25  # Allow some flexibility


# =============================================================================
# CommandRouter Tests
# =============================================================================

class TestCommandRouter:
    """Tests for CommandRouter class."""
    
    @pytest.fixture
    def router(self):
        """Create a CommandRouter instance."""
        return CommandRouter(admin_chat_ids=[12345])
    
    @pytest.mark.asyncio
    async def test_handle_start(self, router):
        """Test /start command."""
        response = await router.handle_start(12345, 111)
        assert "Welcome" in response
        assert "Teiken Claw" in response
    
    @pytest.mark.asyncio
    async def test_handle_help(self, router):
        """Test /help command."""
        response = await router.handle_help(12345, 111)
        assert "Core Commands" in response
        assert "/start" in response
        assert "/help" in response
    
    @pytest.mark.asyncio
    async def test_handle_help_shows_admin_for_admin(self, router):
        """Test /help shows admin commands for admin users."""
        response = await router.handle_help(12345, 111)
        assert "Admin Commands" in response
    
    @pytest.mark.asyncio
    async def test_handle_help_hides_admin_for_non_admin(self, router):
        """Test /help hides admin commands for non-admin users."""
        response = await router.handle_help(99999, 111)
        assert "Admin Commands" not in response
    
    @pytest.mark.asyncio
    async def test_handle_ping(self, router):
        """Test /ping command."""
        response = await router.handle_ping(12345, 111)
        assert "Pong" in response
    
    @pytest.mark.asyncio
    async def test_handle_mode_show_current(self, router):
        """Test /mode command shows current mode."""
        response = await router.handle_mode(12345, 111, [])
        assert "Current Mode" in response
        assert "default" in response
    
    @pytest.mark.asyncio
    async def test_handle_mode_switch(self, router):
        """Test /mode command switches mode."""
        response = await router.handle_mode(12345, 111, ["architect"])
        assert "architect" in response.lower()
        assert router.get_current_mode(12345) == "architect"
    
    @pytest.mark.asyncio
    async def test_handle_mode_invalid(self, router):
        """Test /mode command with invalid mode."""
        response = await router.handle_mode(12345, 111, ["invalid"])
        assert "Invalid" in response
    
    @pytest.mark.asyncio
    async def test_handle_thread_new(self, router):
        """Test /thread new command."""
        response = await router.handle_thread(12345, 111, ["new"])
        assert "New thread" in response
    
    @pytest.mark.asyncio
    async def test_handle_thread_info(self, router):
        """Test /thread command shows thread info."""
        # First create a thread
        await router.handle_thread(12345, 111, ["new"])
        # Then get info
        response = await router.handle_thread(12345, 111, [])
        assert "Thread Info" in response
    
    @pytest.mark.asyncio
    async def test_handle_memory_stub(self, router):
        """Test /memory review command."""
        response = await router.handle_memory(12345, 111, ["review"])
        assert "recent memories" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_jobs_stub(self, router):
        """Test /jobs command without active scheduler."""
        response = await router.handle_jobs(12345, 111)
        assert "scheduled jobs" in response.lower()
        assert "scheduler is not running" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_pause_jobs(self, router):
        """Test /pause jobs command."""
        response = await router.handle_pause(12345, 111, ["jobs"])
        assert "jobs paused" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_pause_all(self, router):
        """Test /pause all command."""
        response = await router.handle_pause(12345, 111, ["all"])
        assert "ALL PAUSED" in response
        assert router._all_paused
    
    @pytest.mark.asyncio
    async def test_handle_resume(self, router):
        """Test /resume command."""
        # First pause
        await router.handle_pause(12345, 111, ["all"])
        # Then resume
        response = await router.handle_resume(12345, 111)
        assert "resumed" in response.lower()
        assert not router._all_paused
    
    @pytest.mark.asyncio
    async def test_handle_admin_requires_admin(self, router):
        """Test /admin command requires admin."""
        response = await router.handle_admin(99999, 111, ["stats"])
        assert "admin privileges" in response.lower()
    
    @pytest.mark.asyncio
    async def test_handle_admin_stats(self, router):
        """Test /admin stats command."""
        response = await router.handle_admin(12345, 111, ["stats"])
        assert "Admin Statistics" in response
    
    def test_is_admin(self, router):
        """Test admin check."""
        assert router._is_admin(12345)
        assert not router._is_admin(99999)
    
    def test_is_paused(self, router):
        """Test pause check."""
        assert not router.is_paused(12345)
        router._paused_chats.add(12345)
        assert router.is_paused(12345)

    @pytest.mark.asyncio
    async def test_hatch_commands_without_control_plane_context(self):
        router = CommandRouter(admin_chat_ids=[12345], control_plane_context=None)
        hatch = await router.handle_hatch(12345, 111, [])
        identity = await router.handle_identity(12345, 111)
        rename = await router.handle_rename(12345, 111, ["Forge"])
        onboard = await router.handle_onboard(12345, 111)
        assert "unavailable" in hatch.lower()
        assert "unavailable" in identity.lower()
        assert "unavailable" in rename.lower()
        assert "unavailable" in onboard.lower()


# =============================================================================
# TelegramSender Tests
# =============================================================================

class TestTelegramSender:
    """Tests for TelegramSender class."""
    
    @pytest.fixture
    def sender(self):
        """Create a TelegramSender instance without actual bot."""
        with patch('app.interfaces.telegram_sender.HAS_TELEGRAM', False):
            return TelegramSender(token="test_token")
    
    def test_sender_initialization(self, sender):
        """Test sender initialization."""
        assert sender.token == "test_token"
        assert not sender.is_running
    
    def test_sender_stats(self, sender):
        """Test sender statistics."""
        stats = sender.stats
        assert "total_sent" in stats
        assert "total_failed" in stats
        assert "is_running" in stats
    
    def test_split_message_short(self, sender):
        """Test splitting short message."""
        text = "Short message"
        chunks = sender._split_message(text)
        assert len(chunks) == 1
    
    def test_split_message_long(self, sender):
        """Test splitting long message."""
        text = "x" * 5000
        chunks = sender._split_message(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= sender.MAX_MESSAGE_LENGTH
    
    def test_find_split_point_paragraph(self, sender):
        """Test finding split point at paragraph."""
        text = "Paragraph 1\n\nParagraph 2 with more text"
        split = sender._find_split_point(text, 20)
        # Should split at paragraph boundary
        assert text[split-2:split] == "\n\n" or text[split-1] == "\n"
    
    def test_find_split_point_newline(self, sender):
        """Test finding split point at newline."""
        text = "Line 1\nLine 2\nLine 3"
        split = sender._find_split_point(text, 10)
        # Should split at newline
        assert text[split-1] == "\n" or split == 10
    
    def test_find_split_point_hard(self, sender):
        """Test hard split when no good boundary."""
        text = "abcdefghijklmnopqrstuvwxyz"
        split = sender._find_split_point(text, 10)
        assert split == 10
    
    @pytest.mark.asyncio
    async def test_send_message_placeholder(self, sender):
        """Test sending message in placeholder mode."""
        result = await sender.send_message(
            chat_id="12345",
            text="Test message"
        )
        assert result  # Should succeed in placeholder mode
    
    @pytest.mark.asyncio
    async def test_send_chunked_message(self, sender):
        """Test sending chunked message."""
        long_text = "x" * 5000
        result = await sender.send_chunked_message(
            chat_id="12345",
            text=long_text
        )
        assert result  # Should succeed
        assert sender._total_chunks > 0

    @pytest.mark.asyncio
    async def test_send_message_strips_tc_profile_before_send(self):
        with patch("app.interfaces.telegram_sender.HAS_TELEGRAM", True), patch("app.interfaces.telegram_sender.Bot"):
            sender = TelegramSender(token="test_token")
            sender._send_with_retry = AsyncMock(return_value=True)
            ok = await sender.send_message(
                chat_id="12345",
                text='<tc_profile>{"agent_display_name":"Forge"}</tc_profile>\n\nHello there',
            )
            assert ok
            sender._send_with_retry.assert_awaited_once()
            sent_text = sender._send_with_retry.await_args.kwargs["text"]
            assert sent_text == "Hello there"


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting functionality."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a RateLimiter instance."""
        from app.queue.throttles import RateLimiter
        return RateLimiter(global_rate=10.0, per_chat_rate=1.0)
    
    def test_rate_limiter_initialization(self, rate_limiter):
        """Test rate limiter initialization."""
        assert rate_limiter.global_rate == 10.0
        assert rate_limiter.per_chat_rate == 1.0
    
    def test_rate_limiter_stats(self, rate_limiter):
        """Test rate limiter statistics."""
        stats = rate_limiter.get_stats()
        assert stats["global_rate"] == 10.0
        assert stats["per_chat_rate"] == 1.0
    
    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self, rate_limiter):
        """Test rate limiter acquire."""
        # Should not raise
        await rate_limiter.acquire("12345")


# =============================================================================
# OutboundQueue Tests
# =============================================================================

class TestOutboundQueue:
    """Tests for OutboundQueue with Telegram integration."""
    
    @pytest.fixture
    def outbound_queue(self):
        """Create an OutboundQueue instance."""
        from app.queue.throttles import OutboundQueue, RateLimiter
        rate_limiter = RateLimiter(global_rate=10.0, per_chat_rate=1.0)
        return OutboundQueue(
            rate_limiter=rate_limiter,
            max_queue_size=100,
        )
    
    def test_queue_initialization(self, outbound_queue):
        """Test queue initialization."""
        assert outbound_queue.max_queue_size == 100
        assert outbound_queue.queue_depth == 0
    
    @pytest.mark.asyncio
    async def test_enqueue_message(self, outbound_queue):
        """Test enqueuing a message."""
        message_id = await outbound_queue.enqueue_message(
            chat_id="12345",
            text="Test message"
        )
        assert message_id is not None
        assert outbound_queue.queue_depth == 1
    
    @pytest.mark.asyncio
    async def test_enqueue_multiple_messages(self, outbound_queue):
        """Test enqueuing multiple messages."""
        for i in range(5):
            await outbound_queue.enqueue_message(
                chat_id="12345",
                text=f"Message {i}"
            )
        assert outbound_queue.queue_depth == 5
    
    @pytest.mark.asyncio
    async def test_queue_full(self, outbound_queue):
        """Test queue full condition."""
        # Fill the queue
        for i in range(100):
            await outbound_queue.enqueue_message(
                chat_id="12345",
                text=f"Message {i}"
            )
        
        # Next message should fail
        with pytest.raises(Exception):
            await outbound_queue.enqueue_message(
                chat_id="12345",
                text="Overflow message"
            )


# =============================================================================
# Integration Tests
# =============================================================================

class TestTelegramIntegration:
    """Integration tests for Telegram components."""
    
    def test_adapter_creates_valid_job(self):
        """Test that adapter creates a valid Job."""
        adapter = TelegramAdapter()
        job = adapter.message_to_job(
            chat_id=12345,
            user_id=67890,
            text="Test message",
        )
        
        # Verify job is valid
        assert job.job_id is not None
        assert job.source == JobSource.TELEGRAM
        assert job.type == JobType.CHAT_MESSAGE
        assert job.priority == JobPriority.INTERACTIVE
    
    @pytest.mark.asyncio
    async def test_command_router_mode_persistence(self):
        """Test that mode changes persist."""
        router = CommandRouter()
        
        # Change mode
        await router.handle_mode(12345, 111, ["coder"])
        
        # Verify mode persisted
        assert router.get_current_mode(12345) == "coder"
        
        # Change again
        await router.handle_mode(12345, 111, ["researcher"])
        assert router.get_current_mode(12345) == "researcher"
    
    def test_markdown_v2_escaping_integration(self):
        """Test MarkdownV2 escaping with realistic content."""
        text = """
        *Bold text* and _italic text_
        [Link](https://example.com)
        `code snippet`
        ```python
        print("Hello, World!")
        ```
        """
        
        escaped = escape_markdown_v2(text)
        
        # All special chars should be escaped
        assert "\\*" in escaped
        assert "\\_" in escaped
        assert "\\[" in escaped
        assert "\\]" in escaped
        assert "\\`" in escaped


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
