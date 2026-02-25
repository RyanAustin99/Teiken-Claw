"""
Command router for Telegram bot commands.

This module provides:
- CommandRouter class for handling all bot commands
- Core commands (start, help, ping, status)
- Mode commands
- Thread commands
- Memory commands (stubs for Phase 6)
- Scheduler commands (stubs for Phase 9)
- Admin commands
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from app.config.logging import get_logger
from app.config.settings import settings
from app.queue.dispatcher import get_dispatcher
from app.queue.workers import get_worker_pool
from app.agent import get_ollama_client, get_circuit_breaker_metrics

logger = get_logger(__name__)


class CommandRouter:
    """
    Router for Telegram bot commands.
    
    Handles all command processing and returns formatted responses.
    
    Attributes:
        admin_chat_ids: List of admin chat IDs
        current_modes: Dict mapping chat_id to current mode
        current_threads: Dict mapping chat_id to thread info
    """
    
    # Available modes
    MODES = ["default", "architect", "operator", "coder", "researcher"]
    
    def __init__(self, admin_chat_ids: Optional[List[int]] = None):
        """
        Initialize the command router.
        
        Args:
            admin_chat_ids: Optional list of admin chat IDs
        """
        self.admin_chat_ids = admin_chat_ids or settings.ADMIN_CHAT_IDS
        self.current_modes: Dict[str, str] = {}
        self.current_threads: Dict[str, Dict[str, Any]] = {}
        self._paused_chats: set = set()
        self._paused_jobs: set = set()
        self._all_paused = False
        
        logger.info(
            f"CommandRouter initialized with {len(self.admin_chat_ids)} admin IDs",
            extra={"event": "command_router_initialized"}
        )
    
    def _is_admin(self, chat_id: int) -> bool:
        """Check if a chat ID is an admin."""
        return chat_id in self.admin_chat_ids
    
    def _format_admin_required(self) -> str:
        """Return admin required message."""
        return "⛔ This command requires admin privileges."
    
    # =========================================================================
    # Core Commands
    # =========================================================================
    
    async def handle_start(self, chat_id: int, user_id: int) -> str:
        """
        Handle /start command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Welcome message
        """
        logger.info(
            f"/start from chat {chat_id}, user {user_id}",
            extra={"event": "command_start", "chat_id": chat_id}
        )
        
        # Initialize mode for this chat
        if str(chat_id) not in self.current_modes:
            self.current_modes[str(chat_id)] = "default"
        
        return (
            "🤖 *Welcome to Teiken Claw\\!*\n\n"
            "I'm your AI assistant powered by Ollama\\. Send me a message and I'll help you\\.\n\n"
            "Use /help to see available commands\\.\n"
            "Use /status to check system health\\."
        )
    
    async def handle_help(self, chat_id: int, user_id: int) -> str:
        """
        Handle /help command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Help message with all commands
        """
        logger.info(
            f"/help from chat {chat_id}",
            extra={"event": "command_help", "chat_id": chat_id}
        )
        
        help_text = """
🤖 *Teiken Claw \\- AI Assistant*

*Core Commands:*
/start \\- Welcome message
/help \\- Show this help
/ping \\- Test bot responsiveness
/status \\- Show system status

*Mode Commands:*
/mode \\- Show current mode
/mode \\<name\\> \\- Switch mode
  Modes: default, architect, operator, coder, researcher

*Thread Commands:*
/thread \\- Show current thread info
/thread new \\- Start a new thread
/thread summary \\- Show thread summary

*Memory Commands:*
/memory review \\- List recent memories
/memory search \\<query\\> \\- Search memories
/memory pause \\- Pause auto\\-memory
/memory resume \\- Resume auto\\-memory

*Scheduler Commands:*
/jobs \\- List scheduled jobs
/pause jobs \\- Pause all scheduled jobs
/pause all \\- Pause everything
/resume \\- Resume from pause
"""
        
        # Add admin commands if user is admin
        if self._is_admin(chat_id):
            help_text += """
*Admin Commands:*
/admin stats \\- Show admin statistics
/admin trace \\<job\\_id\\> \\- Show job trace
"""
        
        return help_text
    
    async def handle_ping(self, chat_id: int, user_id: int) -> str:
        """
        Handle /ping command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Pong response
        """
        return "🏓 Pong\\!"
    
    async def handle_status(self, chat_id: int, user_id: int) -> str:
        """
        Handle /status command.
        
        Shows system status including:
        - Queue depth
        - Worker status
        - Ollama status
        - Circuit breaker status
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Status message
        """
        logger.info(
            f"/status from chat {chat_id}",
            extra={"event": "command_status", "chat_id": chat_id}
        )
        
        status_lines = ["📊 *System Status*\n"]
        
        # Queue status
        dispatcher = get_dispatcher()
        if dispatcher:
            queue_depth = dispatcher.queue_depth
            status_lines.append(f"📦 *Queue Depth:* {queue_depth}")
        else:
            status_lines.append("📦 *Queue:* Not available")
        
        # Worker status
        worker_pool = get_worker_pool()
        if worker_pool:
            worker_status = worker_pool.get_status()
            active_workers = worker_status.get("active_workers", 0)
            total_workers = worker_status.get("total_workers", 0)
            status_lines.append(f"👷 *Workers:* {active_workers}/{total_workers} active")
        else:
            status_lines.append("👷 *Workers:* Not available")
        
        # Ollama status
        try:
            ollama_client = get_ollama_client()
            if ollama_client:
                health = await ollama_client.check_health()
                ollama_status = health.get("status", "unknown")
                model_count = health.get("model_count", 0)
                status_emoji = "✅" if ollama_status == "healthy" else "⚠️"
                status_lines.append(f"🦙 *Ollama:* {status_emoji} {ollama_status} \\({model_count} models\\)")
            else:
                status_lines.append("🦙 *Ollama:* Not configured")
        except Exception as e:
            status_lines.append(f"🦙 *Ollama:* ❌ Error \\- {str(e)[:30]}")
        
        # Circuit breaker status
        try:
            cb_metrics = get_circuit_breaker_metrics()
            status_lines.append(
                f"🔌 *Circuit Breakers:* {cb_metrics.closed_count} closed, "
                f"{cb_metrics.open_count} open, {cb_metrics.half_open_count} half\\-open"
            )
        except Exception:
            status_lines.append("🔌 *Circuit Breakers:* Not available")
        
        # Current mode
        current_mode = self.current_modes.get(str(chat_id), "default")
        status_lines.append(f"🎯 *Current Mode:* {current_mode}")
        
        # Pause status
        if self._all_paused:
            status_lines.append("⏸️ *Status:* ALL PAUSED")
        elif chat_id in self._paused_chats:
            status_lines.append("⏸️ *Status:* Chat paused")
        
        return "\n".join(status_lines)
    
    # =========================================================================
    # Mode Commands
    # =========================================================================
    
    async def handle_mode(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /mode command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments (optional mode name)
        
        Returns:
            str: Mode status or confirmation
        """
        chat_id_str = str(chat_id)
        
        if not args:
            # Show current mode
            current_mode = self.current_modes.get(chat_id_str, "default")
            return (
                f"🎯 *Current Mode:* {current_mode}\n\n"
                f"Available modes: {', '.join(self.MODES)}\n"
                f"Use /mode \\<name\\> to switch\\."
            )
        
        # Switch mode
        new_mode = args[0].lower()
        
        if new_mode not in self.MODES:
            return (
                f"❌ Invalid mode: {new_mode}\n\n"
                f"Available modes: {', '.join(self.MODES)}"
            )
        
        old_mode = self.current_modes.get(chat_id_str, "default")
        self.current_modes[chat_id_str] = new_mode
        
        logger.info(
            f"Mode changed from {old_mode} to {new_mode} for chat {chat_id}",
            extra={
                "event": "mode_changed",
                "chat_id": chat_id,
                "old_mode": old_mode,
                "new_mode": new_mode,
            }
        )
        
        return f"🎯 Mode changed: {old_mode} → {new_mode}"
    
    # =========================================================================
    # Thread Commands
    # =========================================================================
    
    async def handle_thread(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /thread command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments (new, summary)
        
        Returns:
            str: Thread info or confirmation
        """
        chat_id_str = str(chat_id)
        
        if not args:
            # Show current thread info
            thread_info = self.current_threads.get(chat_id_str, {})
            if not thread_info:
                return (
                    "🧵 *Thread Info*\n\n"
                    "No active thread\\. Use /thread new to start one\\."
                )
            
            created_at = thread_info.get("created_at", "unknown")
            message_count = thread_info.get("message_count", 0)
            
            return (
                f"🧵 *Thread Info*\n\n"
                f"Created: {created_at}\n"
                f"Messages: {message_count}"
            )
        
        subcommand = args[0].lower()
        
        if subcommand == "new":
            # Start a new thread
            self.current_threads[chat_id_str] = {
                "created_at": datetime.utcnow().isoformat(),
                "message_count": 0,
            }
            
            logger.info(
                f"New thread started for chat {chat_id}",
                extra={"event": "thread_new", "chat_id": chat_id}
            )
            
            return "🧵 New thread started\\!"
        
        if subcommand == "summary":
            # Thread summary (placeholder)
            thread_info = self.current_threads.get(chat_id_str, {})
            if not thread_info:
                return "❌ No active thread to summarize\\."
            
            return (
                "🧵 *Thread Summary*\n\n"
                "Thread summarization is not yet implemented\\. "
                "This feature will be available in a future update\\."
            )
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    # =========================================================================
    # Memory Commands (Stubs for Phase 6)
    # =========================================================================
    
    async def handle_memory(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /memory command.
        
        These are stubs for Phase 6 implementation.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments
        
        Returns:
            str: Memory info or stub message
        """
        if not args:
            return (
                "🧠 *Memory Commands*\n\n"
                "/memory review \\- List recent memories\n"
                "/memory search \\<query\\> \\- Search memories\n"
                "/memory pause \\- Pause auto\\-memory\n"
                "/memory resume \\- Resume auto\\-memory"
            )
        
        subcommand = args[0].lower()
        
        if subcommand == "review":
            return (
                "🧠 *Recent Memories*\n\n"
                "⚠️ Memory system not yet implemented\\. "
                "This feature will be available in Phase 6\\."
            )
        
        if subcommand == "search":
            query = " ".join(args[1:]) if len(args) > 1 else ""
            if not query:
                return "❌ Please provide a search query\\."
            
            return (
                f"🧠 *Memory Search*\n\n"
                f"Query: {query}\n\n"
                f"⚠️ Memory search not yet implemented\\. "
                f"This feature will be available in Phase 6\\."
            )
        
        if subcommand == "pause":
            return (
                "⏸️ *Memory Paused*\n\n"
                "⚠️ Memory system not yet implemented\\. "
                "This feature will be available in Phase 6\\."
            )
        
        if subcommand == "resume":
            return (
                "▶️ *Memory Resumed*\n\n"
                "⚠️ Memory system not yet implemented\\. "
                "This feature will be available in Phase 6\\."
            )
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    # =========================================================================
    # Scheduler Commands (Stubs for Phase 9)
    # =========================================================================
    
    async def handle_jobs(
        self,
        chat_id: int,
        user_id: int
    ) -> str:
        """
        Handle /jobs command.
        
        Stub for Phase 9 implementation.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Jobs info or stub message
        """
        return (
            "📅 *Scheduled Jobs*\n\n"
            "⚠️ Scheduler not yet implemented\\. "
            "This feature will be available in Phase 9\\."
        )
    
    async def handle_pause(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /pause command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments (jobs, all)
        
        Returns:
            str: Pause confirmation
        """
        if not args:
            return (
                "⏸️ *Pause Commands*\n\n"
                "/pause jobs \\- Pause all scheduled jobs\n"
                "/pause all \\- Pause everything"
            )
        
        subcommand = args[0].lower()
        
        if subcommand == "jobs":
            self._paused_jobs.add(chat_id)
            logger.info(
                f"Jobs paused for chat {chat_id}",
                extra={"event": "jobs_paused", "chat_id": chat_id}
            )
            return (
                "⏸️ *Jobs Paused*\n\n"
                "Scheduled jobs are now paused\\. Use /resume to resume\\.\n\n"
                "⚠️ Full scheduler functionality coming in Phase 9\\."
            )
        
        if subcommand == "all":
            self._all_paused = True
            logger.warning(
                f"All operations paused by chat {chat_id}",
                extra={"event": "all_paused", "chat_id": chat_id}
            )
            return (
                "⏸️ *ALL PAUSED*\n\n"
                "All operations are now paused\\. Use /resume to resume\\."
            )
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    async def handle_resume(
        self,
        chat_id: int,
        user_id: int
    ) -> str:
        """
        Handle /resume command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Resume confirmation
        """
        chat_id_str = str(chat_id)
        
        # Clear all pause states
        self._paused_chats.discard(chat_id)
        self._paused_jobs.discard(chat_id)
        
        if self._all_paused:
            self._all_paused = False
            logger.info(
                f"All operations resumed by chat {chat_id}",
                extra={"event": "all_resumed", "chat_id": chat_id}
            )
            return "▶️ *ALL RESUMED*\n\nAll operations have been resumed\\."
        
        logger.info(
            f"Operations resumed for chat {chat_id}",
            extra={"event": "resumed", "chat_id": chat_id}
        )
        
        return "▶️ *Resumed*\n\nOperations have been resumed\\."
    
    # =========================================================================
    # Admin Commands
    # =========================================================================
    
    async def handle_admin(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /admin command.
        
        Requires admin privileges.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments (stats, trace)
        
        Returns:
            str: Admin info or error
        """
        if not self._is_admin(chat_id):
            return self._format_admin_required()
        
        if not args:
            return (
                "🔐 *Admin Commands*\n\n"
                "/admin stats \\- Show admin statistics\n"
                "/admin trace \\<job\\_id\\> \\- Show job trace"
            )
        
        subcommand = args[0].lower()
        
        if subcommand == "stats":
            return await self._admin_stats(chat_id)
        
        if subcommand == "trace":
            if len(args) < 2:
                return "❌ Please provide a job ID\\."
            return await self._admin_trace(chat_id, args[1])
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    async def _admin_stats(self, chat_id: int) -> str:
        """
        Generate admin statistics.
        
        Args:
            chat_id: Telegram chat ID
        
        Returns:
            str: Admin statistics
        """
        stats_lines = ["📊 *Admin Statistics*\n"]
        
        # Queue stats
        dispatcher = get_dispatcher()
        if dispatcher:
            stats = dispatcher.get_stats()
            stats_lines.append("📦 *Queue:*")
            stats_lines.append(f"  Depth: {stats.get('queue_depth', 0)}")
            stats_lines.append(f"  Processed: {stats.get('total_processed', 0)}")
            stats_lines.append(f"  Failed: {stats.get('total_failed', 0)}")
        
        # Worker stats
        worker_pool = get_worker_pool()
        if worker_pool:
            worker_status = worker_pool.get_status()
            stats_lines.append("\n👷 *Workers:*")
            stats_lines.append(f"  Active: {worker_status.get('active_workers', 0)}")
            stats_lines.append(f"  Total: {worker_status.get('total_workers', 0)}")
            stats_lines.append(f"  Jobs Completed: {worker_status.get('jobs_completed', 0)}")
        
        # Mode distribution
        if self.current_modes:
            stats_lines.append("\n🎯 *Mode Distribution:*")
            mode_counts: Dict[str, int] = {}
            for mode in self.current_modes.values():
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
            for mode, count in mode_counts.items():
                stats_lines.append(f"  {mode}: {count}")
        
        # Pause status
        stats_lines.append("\n⏸️ *Pause Status:*")
        stats_lines.append(f"  All Paused: {'Yes' if self._all_paused else 'No'}")
        stats_lines.append(f"  Paused Jobs: {len(self._paused_jobs)}")
        
        return "\n".join(stats_lines)
    
    async def _admin_trace(self, chat_id: int, job_id: str) -> str:
        """
        Show job trace.
        
        Args:
            chat_id: Telegram chat ID
            job_id: Job ID to trace
        
        Returns:
            str: Job trace info
        """
        dispatcher = get_dispatcher()
        if not dispatcher:
            return "❌ Dispatcher not available\\."
        
        # Try to get job from dispatcher
        job_info = await dispatcher.get_job_info(job_id)
        
        if not job_info:
            return f"❌ Job not found: {job_id}"
        
        trace_lines = [f"🔍 *Job Trace: {job_id}*\n"]
        
        trace_lines.append(f"Status: {job_info.get('status', 'unknown')}")
        trace_lines.append(f"Source: {job_info.get('source', 'unknown')}")
        trace_lines.append(f"Type: {job_info.get('type', 'unknown')}")
        trace_lines.append(f"Priority: {job_info.get('priority', 'unknown')}")
        trace_lines.append(f"Created: {job_info.get('created_at', 'unknown')}")
        trace_lines.append(f"Attempts: {job_info.get('attempts', 0)}")
        
        if job_info.get('error'):
            trace_lines.append(f"\n❌ Error: {job_info['error'][:200]}")
        
        return "\n".join(trace_lines)
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def is_paused(self, chat_id: int) -> bool:
        """Check if a chat is paused."""
        return self._all_paused or chat_id in self._paused_chats
    
    def get_current_mode(self, chat_id: int) -> str:
        """Get the current mode for a chat."""
        return self.current_modes.get(str(chat_id), "default")


__all__ = ["CommandRouter"]
