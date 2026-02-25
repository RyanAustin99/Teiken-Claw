"""
Telegram Bot implementation for Teiken Claw.

This module provides:
- TelegramBot class using python-telegram-bot (async)
- Message handling and job creation
- Typing indicator support
- Error handling for Telegram API errors
"""

import asyncio
from typing import Optional, Callable, Any

from app.config.logging import get_logger
from app.config.settings import settings
from app.queue.jobs import Job, JobSource, JobType, JobPriority, create_job
from app.queue.dispatcher import get_dispatcher

logger = get_logger(__name__)

# Try to import telegram bot library
try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Update = None
    Application = None
    CommandHandler = None
    MessageHandler = None
    ContextTypes = None
    filters = None
    logger.warning(
        "python-telegram-bot not installed, Telegram interface disabled",
        extra={"event": "telegram_import_failed"}
    )


class TelegramBot:
    """
    Telegram Bot implementation using python-telegram-bot.
    
    Features:
    - Async polling mode
    - Message to Job conversion
    - Typing indicator while processing
    - Error handling
    
    Attributes:
        token: Telegram bot token
        application: python-telegram-bot Application instance
        is_running: Whether the bot is currently running
    """
    
    def __init__(
        self,
        token: Optional[str] = None,
        command_router: Optional[Any] = None,
    ):
        """
        Initialize the Telegram bot.
        
        Args:
            token: Telegram bot token (defaults to settings.TELEGRAM_BOT_TOKEN)
            command_router: Optional CommandRouter instance for handling commands
        """
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.command_router = command_router
        self._application: Optional[Any] = None
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None
        
        if not HAS_TELEGRAM:
            logger.warning(
                "TelegramBot created but python-telegram-bot not available",
                extra={"event": "telegram_unavailable"}
            )
            return
        
        if not self.token:
            logger.warning(
                "TelegramBot created but no token configured",
                extra={"event": "telegram_no_token"}
            )
            return
        
        # Build the application
        self._application = Application.builder().token(self.token).build()
        
        # Register handlers
        self._register_handlers()
        
        logger.info(
            "TelegramBot initialized",
            extra={"event": "telegram_bot_initialized"}
        )
    
    def _register_handlers(self) -> None:
        """Register command and message handlers."""
        if not self._application:
            return
        
        # Command handlers - these will be handled by command_router if available
        self._application.add_handler(
            CommandHandler("start", self._handle_start)
        )
        self._application.add_handler(
            CommandHandler("help", self._handle_help)
        )
        self._application.add_handler(
            CommandHandler("ping", self._handle_ping)
        )
        self._application.add_handler(
            CommandHandler("status", self._handle_status)
        )
        self._application.add_handler(
            CommandHandler("mode", self._handle_mode)
        )
        self._application.add_handler(
            CommandHandler("thread", self._handle_thread)
        )
        self._application.add_handler(
            CommandHandler("memory", self._handle_memory)
        )
        self._application.add_handler(
            CommandHandler("jobs", self._handle_jobs)
        )
        self._application.add_handler(
            CommandHandler("pause", self._handle_pause)
        )
        self._application.add_handler(
            CommandHandler("resume", self._handle_resume)
        )
        self._application.add_handler(
            CommandHandler("admin", self._handle_admin)
        )
        
        # Message handler for non-command messages
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        
        # Error handler
        self._application.add_error_handler(self._handle_error)
        
        logger.debug(
            "Telegram handlers registered",
            extra={"event": "telegram_handlers_registered"}
        )
    
    @property
    def is_running(self) -> bool:
        """Check if the bot is currently running."""
        return self._running
    
    async def start(self) -> None:
        """
        Start the Telegram bot in polling mode.
        
        Initializes the bot and starts polling for updates.
        """
        if not HAS_TELEGRAM:
            logger.warning(
                "Cannot start TelegramBot: python-telegram-bot not installed",
                extra={"event": "telegram_start_failed"}
            )
            return
        
        if not self._application:
            logger.warning(
                "Cannot start TelegramBot: application not initialized",
                extra={"event": "telegram_start_failed"}
            )
            return
        
        if self._running:
            logger.warning(
                "TelegramBot already running",
                extra={"event": "telegram_already_running"}
            )
            return
        
        try:
            # Initialize the application
            await self._application.initialize()
            
            # Start polling
            await self._application.start()
            
            # Start polling in a separate task
            self._polling_task = asyncio.create_task(
                self._application.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )
            )
            
            self._running = True
            
            logger.info(
                "TelegramBot started in polling mode",
                extra={"event": "telegram_bot_started"}
            )
            
        except Exception as e:
            logger.error(
                f"Failed to start TelegramBot: {e}",
                extra={"event": "telegram_start_error"},
                exc_info=True
            )
            raise
    
    async def stop(self) -> None:
        """
        Stop the Telegram bot gracefully.
        
        Stops polling and shuts down the application.
        """
        if not self._running:
            return
        
        self._running = False
        
        try:
            if self._application and self._application.updater:
                # Stop polling
                if self._application.updater.running:
                    await self._application.updater.stop()
            
            if self._application:
                # Stop the application
                await self._application.stop()
                await self._application.shutdown()
            
            # Wait for polling task to finish
            if self._polling_task and not self._polling_task.done():
                try:
                    await asyncio.wait_for(self._polling_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._polling_task.cancel()
                    try:
                        await self._polling_task
                    except asyncio.CancelledError:
                        pass
            
            logger.info(
                "TelegramBot stopped",
                extra={"event": "telegram_bot_stopped"}
            )
            
        except Exception as e:
            logger.error(
                f"Error stopping TelegramBot: {e}",
                extra={"event": "telegram_stop_error"},
                exc_info=True
            )
    
    async def _show_typing(self, chat_id: int) -> None:
        """Show typing indicator for a chat."""
        if self._application and self._application.bot:
            try:
                await self._application.bot.send_chat_action(
                    chat_id=chat_id,
                    action="typing"
                )
            except Exception as e:
                logger.debug(
                    f"Failed to show typing indicator: {e}",
                    extra={"event": "typing_indicator_failed", "chat_id": chat_id}
                )
    
    async def _create_job_from_message(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        message_id: Optional[int] = None,
    ) -> Optional[Job]:
        """
        Create a Job from a Telegram message.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            text: Message text
            message_id: Optional message ID for reply context
        
        Returns:
            Job: Created job or None if failed
        """
        try:
            dispatcher = get_dispatcher()
            if not dispatcher:
                logger.error(
                    "Dispatcher not available for job creation",
                    extra={"event": "dispatcher_unavailable"}
                )
                return None
            
            # Create job payload
            payload = {
                "text": text,
                "user_id": user_id,
                "message_id": message_id,
                "source": "telegram",
            }
            
            # Create the job
            job = create_job(
                source=JobSource.TELEGRAM,
                type=JobType.CHAT_MESSAGE,
                payload=payload,
                priority=JobPriority.INTERACTIVE,
                chat_id=str(chat_id),
            )
            
            # Enqueue to dispatcher
            await dispatcher.enqueue(job)
            
            logger.info(
                f"Created job {job.job_id} from Telegram message",
                extra={
                    "event": "telegram_job_created",
                    "job_id": job.job_id,
                    "chat_id": chat_id,
                    "user_id": user_id,
                }
            )
            
            return job
            
        except Exception as e:
            logger.error(
                f"Failed to create job from Telegram message: {e}",
                extra={"event": "telegram_job_creation_failed"},
                exc_info=True
            )
            return None
    
    # =========================================================================
    # Command Handlers
    # =========================================================================
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        
        logger.info(
            f"/start command from user {user_id} in chat {chat_id}",
            extra={"event": "telegram_start_command", "chat_id": chat_id, "user_id": user_id}
        )
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_start(chat_id, user_id)
        else:
            response = (
                "🤖 *Welcome to Teiken Claw!*\n\n"
                "I'm your AI assistant. Send me a message and I'll help you.\n\n"
                "Use /help to see available commands."
            )
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_help(chat_id, user_id)
        else:
            response = self._get_default_help()
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /ping command."""
        if not update.effective_message:
            return
        
        await update.effective_message.reply_text("🏓 Pong!")
    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_status(chat_id, user_id)
        else:
            response = "Status: Running ✅"
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /mode command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        args = context.args if context.args else []
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_mode(chat_id, user_id, args)
        else:
            response = "Mode commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_thread(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /thread command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        args = context.args if context.args else []
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_thread(chat_id, user_id, args)
        else:
            response = "Thread commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /memory command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        args = context.args if context.args else []
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_memory(chat_id, user_id, args)
        else:
            response = "Memory commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /jobs command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_jobs(chat_id, user_id)
        else:
            response = "Scheduler commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /pause command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        args = context.args if context.args else []
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_pause(chat_id, user_id, args)
        else:
            response = "Pause commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_resume(chat_id, user_id)
        else:
            response = "Resume commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    async def _handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command."""
        if not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        args = context.args if context.args else []
        
        # Use command router if available
        if self.command_router:
            response = await self.command_router.handle_admin(chat_id, user_id, args)
        else:
            response = "Admin commands not available."
        
        await update.effective_message.reply_text(
            response,
            parse_mode="Markdown"
        )
    
    # =========================================================================
    # Message Handler
    # =========================================================================
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle non-command text messages.
        
        Creates a Job and enqueues it to the dispatcher.
        Shows typing indicator while processing.
        """
        if not update.effective_message or not update.effective_message.text:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        text = update.effective_message.text
        message_id = update.effective_message.message_id
        
        logger.info(
            f"Message from user {user_id} in chat {chat_id}: {text[:50]}...",
            extra={
                "event": "telegram_message_received",
                "chat_id": chat_id,
                "user_id": user_id,
                "text_length": len(text),
            }
        )
        
        # Show typing indicator
        await self._show_typing(chat_id)
        
        # Create and enqueue job
        job = await self._create_job_from_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            message_id=message_id,
        )
        
        if not job:
            await update.effective_message.reply_text(
                "❌ Failed to process your message. Please try again later."
            )
    
    # =========================================================================
    # Error Handler
    # =========================================================================
    
    async def _handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle Telegram API errors.
        
        Logs the error and optionally notifies the user.
        """
        error = context.error
        
        logger.error(
            f"Telegram error: {error}",
            extra={
                "event": "telegram_error",
                "error_type": type(error).__name__ if error else None,
            },
            exc_info=True
        )
        
        # Try to notify the user if we have an update
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ An error occurred. Please try again later."
                )
            except Exception:
                pass  # Ignore if we can't send the error message
    
    def _get_default_help(self) -> str:
        """Get default help message."""
        return """
🤖 *Teiken Claw - AI Assistant*

*Core Commands:*
/start - Welcome message
/help - Show this help
/ping - Test bot responsiveness
/status - Show system status

*Mode Commands:*
/mode - Show current mode
/mode <name> - Switch mode (default, architect, operator, coder, researcher)

*Thread Commands:*
/thread - Show current thread info
/thread new - Start a new thread
/thread summary - Show thread summary

*Memory Commands:*
/memory review - List recent memories
/memory search <query> - Search memories
/memory pause - Pause auto-memory
/memory resume - Resume auto-memory

*Scheduler Commands:*
/jobs - List scheduled jobs
/pause jobs - Pause all scheduled jobs
/pause all - Pause everything
/resume - Resume from pause

*Admin Commands:*
/admin stats - Show admin statistics
/admin trace <job_id> - Show job trace
"""


# =============================================================================
# Global Instance Management
# =============================================================================

_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> Optional[TelegramBot]:
    """Get the global TelegramBot instance."""
    return _telegram_bot


def set_telegram_bot(bot: Optional[TelegramBot]) -> None:
    """Set the global TelegramBot instance."""
    global _telegram_bot
    _telegram_bot = bot


__all__ = [
    "TelegramBot",
    "HAS_TELEGRAM",
    "get_telegram_bot",
    "set_telegram_bot",
]
