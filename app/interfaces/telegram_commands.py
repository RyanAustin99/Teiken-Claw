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
from app.memory.store import get_memory_store
from app.memory.thread_store import ThreadStore
from app.memory.thread_state import ThreadState
from app.memory.memory_store_v15 import MemoryStoreV15
from app.memory.audit import MemoryAuditLogger
from app.persona import get_persona_audit_logger
from app.persona.resolve import (
    ERR_MODE_NOT_FOUND,
    ERR_SOUL_NOT_FOUND,
    ERR_MODE_LOCKED,
    MODE_ALIASES,
    PersonaResolutionError,
    resolve_persona,
)
from app.modes.registry import get_mode_registry
from app.souls.registry import get_soul_registry
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
    MODES = ["architect", "builder", "debugger", "research", "minimal"]
    
    def __init__(self, admin_chat_ids: Optional[List[int]] = None, control_plane_context: Optional[Any] = None):
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
        self._thread_store = ThreadStore()
        self._thread_state = ThreadState(session=self._thread_store._session)
        self._memory_store_v15 = MemoryStoreV15(session=self._thread_store._session)
        self._memory_audit = MemoryAuditLogger()
        self._persona_audit = get_persona_audit_logger()
        self.control_plane_context = control_plane_context
        self._hatch_sessions: Dict[str, Dict[str, str]] = {}
        
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
/mode list \\- List available modes
/mode show \\<name\\> \\- Show mode details
/mode \\<name\\> \\- Switch mode
/mode lock \\- Prevent mode switching
/mode unlock \\- Allow mode switching
  Modes: architect, builder, debugger, research, minimal

*Soul Commands:*
/soul list \\- List available souls
/soul show \\<name\\> \\- Show soul details
/soul use \\<name\\> \\- Set active soul override

*Thread Commands:*
/thread \\- Show current thread info
/thread new \\<title\\> \\- Start and activate a new thread
/thread list \\- List threads for this chat
/thread use \\<thread\\_ref\\> \\- Switch active thread

*Memory Commands:*
/memory review [limit] \\- List recent memories for active thread
/memory search \\<query\\> [\\-\\-category \\<name\\>] \\- Search memories
/memory forget \\<memory\\_ref\\> \\- Forget a memory
/memory pause \\- Pause auto\\-memory
/memory resume \\- Resume auto\\-memory
/memory stats \\- Show memory counts and status

*Scheduler Commands:*
/jobs \\- List scheduled jobs
/jobs \\<job\\_id\\> \\- Show job details
/jobs pause \\<job\\_id\\> \\- Pause a job
/jobs resume \\<job\\_id\\> \\- Resume a job
/pause jobs \\- Pause all scheduled jobs
/pause tools \\- Pause dangerous tools
/pause all \\- Pause everything
/resume \\- Resume from pause

*Hatch Commands:*
/hatch [name] \\- Hatch or attach an agent and open chat
/identity \\- Show current hatched identity
/rename \\<name\\> \\- Rename current hatched display identity
/onboard \\- Re-enter onboarding state
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
        
        persona_state = self._get_persona_state(chat_id)
        if persona_state:
            status_lines.append(f"🧵 *Scope:* {persona_state.get('scope_ref')}")
            status_lines.append(f"🎭 *Soul:* {persona_state.get('resolved_soul_ref')}")
            status_lines.append(f"🎯 *Mode:* {persona_state.get('resolved_mode_ref')}")
            status_lines.append(f"🔒 *Mode Locked:* {persona_state.get('mode_locked')}")
            status_lines.append(f"🧠 *Memory:* {persona_state.get('memory_enabled')}")
            file_policy = persona_state.get("file_policy", {})
            if file_policy:
                status_lines.append(
                    f"📁 *File Policy:* read={file_policy.get('max_read_bytes')} write={file_policy.get('max_write_bytes')} ext={','.join(file_policy.get('allowed_extensions', []))}"
                )
        else:
            status_lines.append("🎯 *Mode:* unknown")
        
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
        if not args:
            persona = self._get_persona_state(chat_id)
            if not persona:
                return "🎯 *Mode*\n\nNo active thread/session\\. Use /thread new \\<title\\> first\\."
            return (
                f"🎯 *Current Mode:* {persona.get('resolved_mode_ref')}\n"
                f"🔒 Locked: {persona.get('mode_locked')}\n\n"
                f"Use /mode list, /mode show \\<name\\>, /mode \\<name\\>, /mode lock, /mode unlock"
            )

        sub = (args[0] or "").strip().lower()

        if sub == "list":
            modes = get_mode_registry().list_modes()
            if not modes:
                return "🎯 *Modes*\n\nNo modes registered\\."
            lines = ["🎯 *Modes*"]
            for item in modes:
                lines.append(f"• `{item.ref}` \\- {item.definition.description}")
            return "\n".join(lines)

        if sub == "show":
            if len(args) < 2:
                return "❌ Usage: /mode show \\<name\\>"
            target = self._normalize_mode_name(args[1])
            try:
                loaded = get_mode_registry().get_mode(target)
            except KeyError:
                return f"❌ Unknown mode: `{args[1]}`\\."
            must = ", ".join(loaded.definition.output_shape.must_include_sections) or "none"
            forbid = ", ".join(loaded.definition.output_shape.forbid_sections) or "none"
            avoid = ", ".join(loaded.definition.tool_bias.avoid) or "none"
            return (
                f"🎯 *Mode:* `{loaded.ref}`\n\n"
                f"{loaded.definition.description}\n"
                f"Risk: {loaded.definition.risk_posture}\n"
                f"Avoid tools: {avoid}\n"
                f"Must include: {must}\n"
                f"Forbid: {forbid}"
            )

        if sub == "lock":
            ok, msg = self._set_mode_lock(chat_id, True)
            return msg if ok else f"❌ {msg}"

        if sub == "unlock":
            ok, msg = self._set_mode_lock(chat_id, False)
            return msg if ok else f"❌ {msg}"

        target_mode = self._normalize_mode_name(sub)
        ok, message, previous = self._set_mode(chat_id, target_mode)
        if not ok:
            return f"❌ {message}"
        logger.info(
            "Mode changed",
            extra={
                "event": "mode_changed",
                "chat_id": chat_id,
                "old_mode": previous,
                "new_mode": message,
            },
        )
        return f"🎯 Mode changed: {previous} → {message}"

    async def handle_soul(
        self,
        chat_id: int,
        user_id: int,
        args: List[str],
    ) -> str:
        del user_id
        if not args:
            persona = self._get_persona_state(chat_id)
            if not persona:
                return "🎭 *Soul*\n\nNo active thread/session\\."
            return (
                f"🎭 *Current Soul:* {persona.get('resolved_soul_ref')}\n\n"
                "Use /soul list, /soul show \\<name\\>, /soul use \\<name\\>"
            )

        sub = (args[0] or "").strip().lower()
        if sub == "list":
            souls = get_soul_registry().list_souls()
            if not souls:
                return "🎭 *Souls*\n\nNo souls registered\\."
            lines = ["🎭 *Souls*"]
            for soul in souls:
                lines.append(f"• `{soul.ref}` \\- {soul.definition.description}")
            return "\n".join(lines)

        if sub == "show":
            if len(args) < 2:
                return "❌ Usage: /soul show \\<name\\>"
            target = args[1].strip()
            try:
                soul = get_soul_registry().get_soul(target)
            except KeyError:
                return f"❌ Unknown soul: `{target}`\\."
            principles = "\n".join(f"• {item}" for item in soul.definition.principles[:5]) or "• none"
            tools = ", ".join(soul.definition.constraints.allowed_tools)
            return (
                f"🎭 *Soul:* `{soul.ref}`\n\n"
                f"{soul.definition.description}\n"
                f"Tone: {soul.definition.style.tone or 'direct'}\n"
                f"Verbosity: {soul.definition.style.verbosity}\n"
                f"Allowed tools: {tools}\n"
                f"Principles:\n{principles}"
            )

        if sub == "use":
            if len(args) < 2:
                return "❌ Usage: /soul use \\<name\\>"
            target = args[1].strip()
            ok, message, previous = self._set_soul(chat_id, target)
            if not ok:
                return f"❌ {message}"
            return f"🎭 Soul changed: {previous} → {message}"

        return f"❌ Unknown subcommand: {sub}"
    
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
            current = self._thread_state.get_current_thread_row(chat_id_str)
            if not current:
                return "🧵 *Thread Info*\n\nNo active thread\\. Use /thread new \\<title\\>\\."
            return (
                "🧵 *Thread Info*\n\n"
                f"Ref: `{current.public_id}`\n"
                f"Title: {current.title}\n"
                f"Memory: {'enabled' if current.memory_enabled else 'paused'}\n"
                f"Soul: {current.active_soul or 'default'}\n"
                f"Mode: {current.active_mode}\n"
                f"Mode Locked: {current.mode_locked}\n"
                f"Last Active: {current.last_active_at or current.updated_at}"
            )

        subcommand = args[0].lower()

        if subcommand == "new":
            title = " ".join(args[1:]).strip() if len(args) > 1 else ""
            thread = self._thread_store.create_thread(chat_id_str, title=title or None)
            logger.info("Thread created", extra={"event": "thread_new", "chat_id": chat_id, "thread_id": thread.public_id})
            return f"🧵 New thread started: `{thread.public_id}` \\({thread.title}\\)"

        if subcommand == "list":
            threads = self._thread_store.list_threads(chat_id_str)
            if not threads:
                return "🧵 *Threads*\n\nNo threads yet\\. Use /thread new \\<title\\>\\."
            lines = ["🧵 *Threads*"]
            for thread in threads[:20]:
                marker = " \\(active\\)" if thread.is_active else ""
                lines.append(f"• `{thread.public_id}` {thread.title}{marker}")
            return "\n".join(lines)

        if subcommand == "use":
            if len(args) < 2:
                return "❌ Usage: /thread use \\<thread\\_ref\\>"
            thread_ref = args[1].strip()
            try:
                thread = self._thread_store.set_active_thread(chat_id_str, thread_ref)
            except ValueError:
                return f"❌ Thread `{thread_ref}` not found\\."
            return f"🧵 Active thread: `{thread.public_id}` \\({thread.title}\\)"

        if subcommand == "summary":
            return "🧵 Thread summary is not enabled in v1\\.5\\. Use /thread list or /memory review\\."

        return f"❌ Unknown subcommand: {subcommand}"
    
    # =========================================================================
    # Memory Commands
    # =========================================================================
    
    async def handle_memory(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /memory command.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments
        
        Returns:
            str: Memory info or action result
        """
        if not args:
            return (
                "🧠 *Memory Commands*\n\n"
                "/memory review \\- List recent memories\n"
                "/memory search \\<query\\> \\- Search memories\n"
                "/memory forget \\<id\\> \\- Delete a memory\n"
                "/memory pause \\- Pause auto\\-memory\n"
                "/memory resume \\- Resume auto\\-memory\n"
                "/memory stats \\- Show memory status"
            )
        
        subcommand = args[0].lower()
        
        if subcommand == "review":
            return await self._handle_memory_review(chat_id, args[1:])
        
        if subcommand == "search":
            query = " ".join(args[1:]) if len(args) > 1 else ""
            if not query:
                return "❌ Please provide a search query\\."
            return await self._handle_memory_search(chat_id, query)
        
        if subcommand == "forget":
            memory_id = args[1] if len(args) > 1 else ""
            if not memory_id:
                return "❌ Please provide a memory ID to forget\\."
            return await self._handle_memory_forget(chat_id, memory_id)
        
        if subcommand == "pause":
            return await self._handle_memory_pause(chat_id)
        
        if subcommand == "resume":
            return await self._handle_memory_resume(chat_id)
        
        if subcommand == "stats":
            return await self._handle_memory_stats(chat_id)
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    async def _handle_memory_review(self, chat_id: int, args: List[str]) -> str:
        """Handle memory review subcommand."""
        try:
            limit = 10
            if args and args[0].isdigit():
                limit = int(args[0])

            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "🧠 *Recent Memories*\n\nNo active thread\\. Use /thread new first\\."

            memories = self._memory_store_v15.list_memories(thread_id=active.id, limit=limit, include_deleted=False)
            if not memories:
                return "🧠 *Recent Memories*\n\nNo memories found\\."

            lines = [f"🧠 *Recent Memories* \\(`{active.public_id}`\\)\n"]
            for mem in memories[: max(1, limit)]:
                value = (mem.value or "").replace("_", "\\_").replace("*", "\\*")
                lines.append(f"• `[{mem.public_id}]` \\({mem.category}\\) {mem.key} = {value[:80]}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Memory review error: {e}", extra={"event": "memory_review_error"})
            return f"Error listing memories: {str(e)[:50]}"
    
    async def _handle_memory_search(self, chat_id: int, query: str) -> str:
        """Handle memory search subcommand."""
        try:
            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "🧠 *Memory Search*\n\nNo active thread\\."

            category: Optional[str] = None
            tokens = query.split()
            if "--category" in tokens:
                idx = tokens.index("--category")
                if idx + 1 < len(tokens):
                    category = tokens[idx + 1].strip().lower()
                    tokens = tokens[:idx] + tokens[idx + 2 :]
            query_text = " ".join(tokens).strip()
            if not query_text:
                return "❌ Please provide a search query\\."

            results = self._memory_store_v15.search_memories(
                thread_id=active.id,
                query=query_text,
                category=category,
                limit=10,
            )
            if not results:
                return f"🧠 *Memory Search*\n\nNo results for: {query_text}"

            lines = [f"🧠 *Memory Search*\n\nQuery: {query_text}\n"]
            for mem in results[:10]:
                value = (mem.value or "").replace("_", "\\_").replace("*", "\\*")
                lines.append(f"• `[{mem.public_id}]` \\({mem.category}\\) {mem.key} = {value[:90]}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Memory search error: {e}", extra={"event": "memory_search_error"})
            return f"Error searching memories: {str(e)[:50]}"
    
    async def _handle_memory_forget(self, chat_id: int, memory_id: str) -> str:
        """Handle memory forget subcommand."""
        try:
            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "❌ No active thread\\."

            success = self._memory_store_v15.soft_delete_memory(thread_id=active.id, memory_public_id=memory_id)
            if success:
                self._memory_audit.log(
                    thread_id=active.id,
                    agent_id=None,
                    source_message_id=None,
                    op="delete",
                    memory_id=None,
                    category=None,
                    key=None,
                    status="ok",
                    details={"memory_ref": memory_id},
                )
                return f"🗑️ Memory `{memory_id}` has been forgotten\\."
            self._memory_audit.log(
                thread_id=active.id,
                agent_id=None,
                source_message_id=None,
                op="delete",
                memory_id=None,
                category=None,
                key=None,
                status="error",
                reason_code="ERR_MEM_NOT_FOUND",
                details={"memory_ref": memory_id},
            )
            return f"❌ Memory `{memory_id}` not found\\."
        except Exception as e:
            logger.error(f"Memory forget error: {e}", extra={"event": "memory_forget_error"})
            return f"❌ Error forgetting memory: {str(e)[:50]}"
    
    async def _handle_memory_edit(self, chat_id: int, memory_id: str, new_text: str) -> str:
        """Handle memory edit subcommand."""
        del chat_id
        del memory_id
        del new_text
        return "❌ /memory edit is not supported in v1\\.5\\. Use /memory forget and restate preference\\."
    
    async def _handle_memory_pause(self, chat_id: int) -> str:
        """Handle memory pause subcommand."""
        try:
            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "❌ No active thread\\."
            thread = self._thread_store.set_memory_enabled(str(chat_id), active.public_id, enabled=False)
            if not thread:
                return "❌ Failed to pause memory\\."
            self._memory_audit.log(
                thread_id=thread.id,
                agent_id=None,
                source_message_id=None,
                op="pause",
                memory_id=None,
                category=None,
                key=None,
                status="ok",
            )
            return f"⏸️ Memory paused for `{thread.public_id}`\\."
        except Exception as e:
            logger.error(f"Memory pause error: {e}", extra={"event": "memory_pause_error"})
            return f"❌ Error pausing memory: {str(e)[:50]}"
    
    async def _handle_memory_resume(self, chat_id: int) -> str:
        """Handle memory resume subcommand."""
        try:
            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "❌ No active thread\\."
            thread = self._thread_store.set_memory_enabled(str(chat_id), active.public_id, enabled=True)
            if not thread:
                return "❌ Failed to resume memory\\."
            self._memory_audit.log(
                thread_id=thread.id,
                agent_id=None,
                source_message_id=None,
                op="resume",
                memory_id=None,
                category=None,
                key=None,
                status="ok",
            )
            return f"▶️ Memory resumed for `{thread.public_id}`\\."
        except Exception as e:
            logger.error(f"Memory resume error: {e}", extra={"event": "memory_resume_error"})
            return f"❌ Error resuming memory: {str(e)[:50]}"
    
    async def _handle_memory_policy(self, chat_id: int) -> str:
        """Handle memory policy subcommand."""
        del chat_id
        return "🧠 Deterministic memory is enabled\\. Use /memory stats for current thread status\\."

    async def _handle_memory_stats(self, chat_id: int) -> str:
        """Handle memory stats subcommand."""
        try:
            active = self._thread_state.get_current_thread_row(str(chat_id))
            if not active:
                return "🧠 *Memory Stats*\n\nNo active thread\\."
            counts = self._memory_store_v15.stats_by_category(active.id)
            recent = self._memory_store_v15.list_memories(active.id, limit=1, include_deleted=False)
            last_write = recent[0].updated_at if recent else "never"
            parts = [f"🧠 *Memory Stats* \\(`{active.public_id}`\\)", f"Memory Enabled: {active.memory_enabled}", f"Last Write: {last_write}"]
            if counts:
                parts.append("By Category:")
                for category, count in sorted(counts.items()):
                    parts.append(f"• {category}: {count}")
            else:
                parts.append("No stored memories.")
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Memory stats error: {e}", extra={"event": "memory_stats_error"})
            return f"❌ Error showing memory stats: {str(e)[:50]}"
    
    # =========================================================================
    # Scheduler Commands (Phase 9)
    # =========================================================================
    
    async def handle_jobs(
        self,
        chat_id: int,
        user_id: int,
        args: Optional[List[str]] = None
    ) -> str:
        """
        Handle /jobs command.
        
        Commands:
            /jobs - List all scheduled jobs
            /jobs <job_id> - Show job details
            /jobs pause <job_id> - Pause specific job
            /jobs resume <job_id> - Resume specific job
            /jobs delete <job_id> - Delete job (admin only)
            /jobs run <job_id> - Run job now (admin only)
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments
        
        Returns:
            str: Jobs info or action result
        """
        from app.scheduler import (
            get_scheduler_service,
            get_control_state_manager,
        )
        
        scheduler = get_scheduler_service()
        control_state = get_control_state_manager()
        
        # Check if scheduler is available
        if not scheduler or not scheduler.is_running():
            return (
                "📅 *Scheduled Jobs*\n\n"
                "⚠️ Scheduler is not running\\. "
                "Please check system status\\."
            )
        
        args = args or []
        
        # No args - list all jobs
        if not args:
            return await self._list_jobs(scheduler, control_state, chat_id)
        
        subcommand = args[0].lower()
        
        # Show job details
        if subcommand not in ("pause", "resume", "delete", "run"):
            return await self._show_job_details(scheduler, subcommand, chat_id)
        
        # Actions that require a job_id
        if len(args) < 2:
            return f"❌ Usage: /jobs {subcommand} <job\\_id>"
        
        job_id = args[1]
        
        if subcommand == "pause":
            return await self._pause_job(scheduler, job_id, chat_id)
        
        if subcommand == "resume":
            return await self._resume_job(scheduler, job_id, chat_id)
        
        if subcommand == "delete":
            if not self._is_admin(chat_id):
                return self._format_admin_required()
            return await self._delete_job(scheduler, job_id, chat_id)
        
        if subcommand == "run":
            if not self._is_admin(chat_id):
                return self._format_admin_required()
            return await self._run_job_now(scheduler, job_id, chat_id)
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    async def _list_jobs(
        self,
        scheduler,
        control_state,
        chat_id: int
    ) -> str:
        """List all scheduled jobs."""
        jobs = scheduler.list_jobs()
        
        if not jobs:
            return (
                "📅 *Scheduled Jobs*\n\n"
                "No scheduled jobs found\\.\n\n"
                "Use the scheduler tool to create jobs\\."
            )
        
        lines = ["📅 *Scheduled Jobs*\n"]
        
        # Show control state
        if control_state:
            state = control_state.get_state()
            if state != "normal":
                lines.append(f"⚠️ *State:* {state}")
                lines.append("")
        
        for job in jobs[:10]:
            status = "✅" if job.enabled else "⏸️"
            trigger = job.trigger_type.value if hasattr(job.trigger_type, 'value') else str(job.trigger_type)
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M") if job.next_run_time else "N/A"
            
            # Escape markdown
            name = job.name.replace("_", "\\_").replace("*", "\\*")[:30]
            
            lines.append(f"{status} `{job.job_id}` \\({trigger}\\)")
            lines.append(f"   └ {name}")
            lines.append(f"   └ Next: {next_run}")
        
        if len(jobs) > 10:
            lines.append(f"\n_\\.\\.\\. and {len(jobs) - 10} more_")
        
        lines.append(f"\n_Total: {len(jobs)} jobs_")
        
        return "\n".join(lines)
    
    async def _show_job_details(
        self,
        scheduler,
        job_id: str,
        chat_id: int
    ) -> str:
        """Show details for a specific job."""
        job = scheduler.get_job(job_id)
        
        if not job:
            return f"❌ Job not found: `{job_id}`"
        
        lines = [f"📅 *Job Details: `{job_id}`*\n"]
        
        status = "✅ Enabled" if job.enabled else "⏸️ Paused"
        lines.append(f"*Status:* {status}")
        escaped_name = job.name.replace("_", "\\_")
        lines.append(f"*Name:* {escaped_name}")
        
        trigger = job.trigger_type.value if hasattr(job.trigger_type, 'value') else str(job.trigger_type)
        lines.append(f"*Trigger:* {trigger}")
        
        if job.next_run_time:
            lines.append(f"*Next Run:* {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        if job.last_run_time:
            lines.append(f"*Last Run:* {job.last_run_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        lines.append(f"*Run Count:* {job.run_count}")
        
        # Show trigger config
        if job.trigger_config:
            config = job.trigger_config.model_dump(exclude_none=True)
            if config:
                lines.append("\n*Trigger Config:*")
                for key, value in config.items():
                    if value is not None:
                        lines.append(f"  {key}: {value}")
        
        # Show action
        if job.action:
            lines.append(f"\n*Action Type:* {job.action.type}")
            content = job.action.content[:100].replace("_", "\\_").replace("*", "\\*")
            lines.append(f"*Content:* {content}")
        
        return "\n".join(lines)
    
    async def _pause_job(
        self,
        scheduler,
        job_id: str,
        chat_id: int
    ) -> str:
        """Pause a specific job."""
        success = await scheduler.pause_job(job_id)
        
        if success:
            logger.info(
                f"Job {job_id} paused by chat {chat_id}",
                extra={"event": "job_paused", "job_id": job_id, "chat_id": chat_id}
            )
            return f"⏸️ Job `{job_id}` has been paused\\."
        
        return f"❌ Failed to pause job `{job_id}`\\."
    
    async def _resume_job(
        self,
        scheduler,
        job_id: str,
        chat_id: int
    ) -> str:
        """Resume a specific job."""
        success = await scheduler.resume_job(job_id)
        
        if success:
            logger.info(
                f"Job {job_id} resumed by chat {chat_id}",
                extra={"event": "job_resumed", "job_id": job_id, "chat_id": chat_id}
            )
            return f"▶️ Job `{job_id}` has been resumed\\."
        
        return f"❌ Failed to resume job `{job_id}`\\."
    
    async def _delete_job(
        self,
        scheduler,
        job_id: str,
        chat_id: int
    ) -> str:
        """Delete a job (admin only)."""
        success = await scheduler.remove_job(job_id)
        
        if success:
            logger.warning(
                f"Job {job_id} deleted by admin {chat_id}",
                extra={"event": "job_deleted", "job_id": job_id, "chat_id": chat_id}
            )
            return f"🗑️ Job `{job_id}` has been deleted\\."
        
        return f"❌ Failed to delete job `{job_id}`\\."
    
    async def _run_job_now(
        self,
        scheduler,
        job_id: str,
        chat_id: int
    ) -> str:
        """Run a job immediately (admin only)."""
        success = await scheduler.run_job_now(job_id)
        
        if success:
            logger.info(
                f"Job {job_id} triggered by admin {chat_id}",
                extra={"event": "job_triggered", "job_id": job_id, "chat_id": chat_id}
            )
            return f"▶️ Job `{job_id}` has been triggered to run now\\."
        
        return f"❌ Failed to trigger job `{job_id}`\\."
    
    async def handle_pause(
        self,
        chat_id: int,
        user_id: int,
        args: List[str]
    ) -> str:
        """
        Handle /pause command.
        
        Commands:
            /pause - Show pause options
            /pause jobs - Pause all scheduled jobs
            /pause tools - Pause dangerous tools
            /pause all - Pause everything (read-only mode)
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments (jobs, tools, all)
        
        Returns:
            str: Pause confirmation
        """
        from app.scheduler import get_control_state_manager
        
        control_state = get_control_state_manager()
        
        if not args:
            return (
                "⏸️ *Pause Commands*\n\n"
                "/pause jobs \\- Pause all scheduled jobs\n"
                "/pause tools \\- Pause dangerous tools\n"
                "/pause all \\- Pause everything \\(read\\-only\\)"
            )
        
        subcommand = args[0].lower()
        
        if not control_state:
            # Fallback to local state if control state manager not available
            if subcommand == "jobs":
                self._paused_jobs.add(chat_id)
                return "⏸️ Jobs paused locally \\(control state not available\\)\\."
            
            if subcommand == "all":
                self._all_paused = True
                return "⏸️ ALL PAUSED locally \\(control state not available\\)\\."
            
            return f"❌ Unknown subcommand: {subcommand}"
        
        if subcommand == "jobs":
            result = control_state.pause_jobs(changed_by=f"chat:{chat_id}")
            logger.info(
                f"Jobs paused by chat {chat_id}",
                extra={"event": "jobs_paused", "chat_id": chat_id}
            )
            return (
                "⏸️ *Jobs Paused*\n\n"
                "All scheduled jobs are now paused\\. Use /resume to resume\\."
            )
        
        if subcommand == "tools":
            result = control_state.pause_tools(changed_by=f"chat:{chat_id}")
            logger.info(
                f"Tools paused by chat {chat_id}",
                extra={"event": "tools_paused", "chat_id": chat_id}
            )
            return (
                "⏸️ *Tools Paused*\n\n"
                "Dangerous tools are now disabled:\n"
                "• exec\n"
                "• files\\_write\n"
                "• files\\_delete\n"
                "• web\\_post/put/delete\n\n"
                "Use /resume to restore\\."
            )
        
        if subcommand == "all":
            result = control_state.pause_all(changed_by=f"chat:{chat_id}")
            logger.warning(
                f"ALL operations paused by chat {chat_id}",
                extra={"event": "all_paused", "chat_id": chat_id}
            )
            return (
                "⏸️ *ALL PAUSED*\n\n"
                "System is now in read\\-only mode:\n"
                "• Scheduled jobs paused\n"
                "• Dangerous tools disabled\n"
                "• No modifications allowed\n\n"
                "Use /resume to restore\\."
            )
        
        return f"❌ Unknown subcommand: {subcommand}"
    
    async def handle_resume(
        self,
        chat_id: int,
        user_id: int
    ) -> str:
        """
        Handle /resume command.
        
        Restores normal operation from any pause state.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
        
        Returns:
            str: Resume confirmation
        """
        from app.scheduler import get_control_state_manager
        
        control_state = get_control_state_manager()
        
        # Clear local pause states
        self._paused_chats.discard(chat_id)
        self._paused_jobs.discard(chat_id)
        self._all_paused = False
        
        if not control_state:
            logger.info(
                f"Operations resumed locally by chat {chat_id}",
                extra={"event": "resumed_local", "chat_id": chat_id}
            )
            return "▶️ *Resumed*\n\nOperations have been resumed locally\\."
        
        # Get current state
        current_state = control_state.get_state()
        
        if current_state == "normal":
            return "✅ System is already in normal operation mode\\."
        
        # Resume to normal
        result = control_state.resume(changed_by=f"chat:{chat_id}")
        
        logger.info(
            f"Operations resumed by chat {chat_id} (was: {current_state})",
            extra={"event": "all_resumed", "chat_id": chat_id, "previous_state": current_state}
        )
        
        return (
            "▶️ *ALL RESUMED*\n\n"
            f"System restored to normal operation\\.\n"
            f"Previous state: {current_state}"
        )

    # =========================================================================
    # Skills Commands (Phase 10)
    # =========================================================================

    async def handle_skills(
        self,
        chat_id: int,
        user_id: int,
        args: Optional[List[str]] = None
    ) -> str:
        """
        Handle /skills command.

        Commands:
            /skills - List all available skills
            /skills <name> - Run a specific skill
            /skills <name> <params> - Run skill with parameters

        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            args: Command arguments

        Returns:
            str: Skills info or execution result
        """
        from app.skills import (
            get_skill_loader,
            get_skill_engine,
            get_skill_router,
        )

        loader = get_skill_loader()
        engine = get_skill_engine()
        router = get_skill_router()

        args = args or []

        # No args - list all skills
        if not args:
            return await self._list_skills(loader, router)

        skill_name = args[0].lower()

        # Check if skill exists
        skill = loader.get_skill(skill_name)
        if not skill:
            # Maybe it's a keyword trigger
            matched = router.get_skill_by_keyword(skill_name)
            if matched:
                skill_name = matched.name
                skill = matched
            else:
                # Check for suggestions
                suggestions = router.suggest_skills(skill_name, limit=3)
                if suggestions:
                    suggestion_text = "\n".join([f"• {s['name']} - {s['description'][:50]}..." for s in suggestions])
                    return (
                        f"❌ Skill '{skill_name}' not found.\n\n"
                        f"*Did you mean?*\n{suggestion_text}"
                    )
                return f"❌ Skill '{skill_name}' not found."

        # Parse remaining args as parameters
        params = {}
        for arg in args[1:]:
            if '=' in arg:
                key, value = arg.split('=', 1)
                params[key] = value

        # Execute the skill
        return await self._execute_skill(engine, skill_name, params)

    async def _list_skills(self, loader, router) -> str:
        """List all available skills."""
        skills = loader.list_skills()

        if not skills:
            return (
                "🔧 *Available Skills*\n\n"
                "No skills found. Skills should be defined in YAML files."
            )

        lines = ["🔧 *Available Skills*\n"]

        for skill_name in skills:
            skill = loader.get_skill(skill_name)
            if skill:
                # Get trigger keywords
                triggers = []
                for t in skill.triggers:
                    triggers.extend(t.keywords[:2])
                trigger_text = ", ".join(triggers) if triggers else "(no triggers)"

                lines.append(f"• *{skill_name}* - {skill.description[:40]}...")
                lines.append(f"  Triggers: {trigger_text}")

                # Show inputs
                if skill.inputs:
                    input_names = [inp.name for inp in skill.inputs[:3]]
                    lines.append(f"  Inputs: {', '.join(input_names)}")

        lines.append("")
        lines.append("Use /skills <name> to run a skill.")
        lines.append("Use /skill <name> param=value for parameters.")

        return "\n".join(lines)

    async def _execute_skill(self, engine, skill_name: str, params: dict) -> str:
        """Execute a skill and return the result."""
        try:
            result = engine.execute_skill(skill_name, params)

            if result.success:
                output_text = result.outputs.get("result", str(result.outputs))
                return (
                    f"✅ *Skill: {skill_name}*\n\n"
                    f"{output_text}\n\n"
                    f"_Executed in {result.execution_time_ms:.0f}ms_"
                )
            else:
                return (
                    f"❌ *Skill Failed: {skill_name}*\n\n"
                    f"{result.error}"
                )

        except Exception as e:
            logger.error(f"Skill execution error: {e}", exc_info=True)
            return f"❌ Error executing skill: {str(e)}"

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
        from app.scheduler import (
            get_scheduler_service,
            get_control_state_manager,
        )
        
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
        
        # Scheduler stats
        scheduler = get_scheduler_service()
        if scheduler and scheduler.is_running():
            scheduler_stats = scheduler.get_stats()
            stats_lines.append("\n📅 *Scheduler:*")
            stats_lines.append(f"  Total Jobs: {scheduler_stats.total_jobs}")
            stats_lines.append(f"  Enabled: {scheduler_stats.enabled_jobs}")
            stats_lines.append(f"  Disabled: {scheduler_stats.disabled_jobs}")
            if scheduler_stats.next_run_time:
                stats_lines.append(f"  Next Run: {scheduler_stats.next_run_time.strftime('%H:%M:%S')}")
        else:
            stats_lines.append("\n📅 *Scheduler:* Not running")
        
        # Control state
        control_state = get_control_state_manager()
        if control_state:
            state_status = control_state.get_status()
            stats_lines.append("\n⏸️ *Control State:*")
            stats_lines.append(f"  State: {state_status['state']}")
            stats_lines.append(f"  Jobs Paused: {'Yes' if state_status['is_jobs_paused'] else 'No'}")
            stats_lines.append(f"  Tools Paused: {'Yes' if state_status['is_tools_paused'] else 'No'}")
        
        # Mode distribution
        if self.current_modes:
            stats_lines.append("\n🎯 *Mode Distribution:*")
            mode_counts: Dict[str, int] = {}
            for mode in self.current_modes.values():
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
            for mode, count in mode_counts.items():
                stats_lines.append(f"  {mode}: {count}")
        
        # Pause status (legacy)
        stats_lines.append("\n⏸️ *Local Pause Status:*")
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

    @staticmethod
    def _normalize_mode_name(raw: str) -> str:
        value = (raw or "").strip()
        if not value:
            return value
        if "@" in value:
            name, version = value.split("@", 1)
            name = MODE_ALIASES.get(name.lower(), name.lower())
            return f"{name}@{version.strip()}"
        return MODE_ALIASES.get(value.lower(), value.lower())

    def _get_persona_state(self, chat_id: int) -> Optional[Dict[str, Any]]:
        chat_key = str(chat_id)
        try:
            # Hatched control-plane chat: session scope.
            hatch_state = self._hatch_sessions.get(chat_key)
            if hatch_state and self.control_plane_context:
                cp = self.control_plane_context
                session = cp.session_service.get_session(hatch_state["session_id"])
                agent = cp.agent_service.get_agent(hatch_state["agent_id"])
                if session and agent:
                    mode_ref = session.active_mode or agent.default_mode
                    soul_ref = session.active_soul or agent.default_soul
                    persona = resolve_persona(
                        mode_ref=mode_ref,
                        soul_ref=soul_ref,
                        tool_profile=agent.tool_profile,
                        base_file_policy={
                            "max_read_bytes": int(getattr(settings, "FILES_MAX_READ_BYTES", 1_048_576)),
                            "max_write_bytes": int(getattr(settings, "FILES_MAX_WRITE_BYTES", 262_144)),
                            "allowed_extensions": list(getattr(settings, "FILES_ALLOWED_WRITE_EXTENSIONS", [".md", ".txt", ".json", ".yaml", ".yml", ".log"])),
                        },
                    )
                    return {
                        "scope_type": "session",
                        "scope_ref": session.id,
                        "resolved_mode_ref": persona.resolved_mode_ref,
                        "resolved_soul_ref": persona.resolved_soul_ref,
                        "mode_locked": bool(session.mode_locked),
                        "memory_enabled": True,
                        "file_policy": persona.effective_file_policy,
                    }

            # Default queue path: thread scope.
            thread = self._thread_state.get_current_thread_row(chat_key)
            if not thread:
                return None
            persona = resolve_persona(
                mode_ref=thread.active_mode,
                soul_ref=thread.active_soul or getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0"),
                tool_profile="balanced",
                base_file_policy={
                    "max_read_bytes": int(getattr(settings, "FILES_MAX_READ_BYTES", 1_048_576)),
                    "max_write_bytes": int(getattr(settings, "FILES_MAX_WRITE_BYTES", 262_144)),
                    "allowed_extensions": list(getattr(settings, "FILES_ALLOWED_WRITE_EXTENSIONS", [".md", ".txt", ".json", ".yaml", ".yml", ".log"])),
                },
            )
            return {
                "scope_type": "thread",
                "scope_ref": thread.public_id,
                "resolved_mode_ref": persona.resolved_mode_ref,
                "resolved_soul_ref": persona.resolved_soul_ref,
                "mode_locked": bool(thread.mode_locked),
                "memory_enabled": bool(thread.memory_enabled),
                "file_policy": persona.effective_file_policy,
            }
        except PersonaResolutionError:
            return None

    def _set_mode(self, chat_id: int, mode_name_or_ref: str) -> tuple[bool, str, str]:
        chat_key = str(chat_id)
        target_mode = self._normalize_mode_name(mode_name_or_ref)
        try:
            loaded = get_mode_registry().get_mode(target_mode)
        except KeyError:
            return False, f"{ERR_MODE_NOT_FOUND}: Unknown mode `{mode_name_or_ref}`", ""

        hatch_state = self._hatch_sessions.get(chat_key)
        if hatch_state and self.control_plane_context:
            cp = self.control_plane_context
            session = cp.session_service.get_session(hatch_state["session_id"])
            agent = cp.agent_service.get_agent(hatch_state["agent_id"])
            if not session or not agent:
                return False, "No active hatched session", ""
            if session.mode_locked:
                return False, f"{ERR_MODE_LOCKED}: mode is locked for this session", session.active_mode
            previous = session.active_mode or agent.default_mode
            updated = cp.session_service.set_persona(session.id, active_soul=session.active_soul, active_mode=loaded.ref)
            if not updated:
                return False, "Failed to set session mode", previous
            self._persona_audit.log_event(
                scope_type="session",
                session_id=session.id,
                agent_id=agent.id,
                op="mode_set",
                previous_value=previous,
                new_value=loaded.ref,
                status="ok",
            )
            return True, loaded.ref, previous

        thread = self._thread_state.get_current_thread_row(chat_key) or self._thread_store.get_or_create_active_thread(chat_key)
        if thread.mode_locked:
            return False, f"{ERR_MODE_LOCKED}: mode is locked for this thread", thread.active_mode
        previous = thread.active_mode
        updated = self._thread_store.set_active_mode(chat_key, thread.public_id, loaded.ref)
        if not updated:
            return False, "Failed to set thread mode", previous
        self._persona_audit.log_event(
            scope_type="thread",
            thread_id=thread.id,
            session_id=None,
            agent_id=None,
            op="mode_set",
            previous_value=previous,
            new_value=loaded.ref,
            status="ok",
        )
        return True, loaded.ref, previous

    def _set_soul(self, chat_id: int, soul_name_or_ref: str) -> tuple[bool, str, str]:
        chat_key = str(chat_id)
        try:
            loaded = get_soul_registry().get_soul(soul_name_or_ref)
        except KeyError:
            return False, f"{ERR_SOUL_NOT_FOUND}: Unknown soul `{soul_name_or_ref}`", ""

        hatch_state = self._hatch_sessions.get(chat_key)
        if hatch_state and self.control_plane_context:
            cp = self.control_plane_context
            session = cp.session_service.get_session(hatch_state["session_id"])
            agent = cp.agent_service.get_agent(hatch_state["agent_id"])
            if not session or not agent:
                return False, "No active hatched session", ""
            previous = session.active_soul or agent.default_soul
            updated = cp.session_service.set_persona(session.id, active_soul=loaded.ref, active_mode=session.active_mode)
            if not updated:
                return False, "Failed to set session soul", previous
            self._persona_audit.log_event(
                scope_type="session",
                session_id=session.id,
                agent_id=agent.id,
                op="soul_set",
                previous_value=previous,
                new_value=loaded.ref,
                status="ok",
            )
            return True, loaded.ref, previous

        thread = self._thread_state.get_current_thread_row(chat_key) or self._thread_store.get_or_create_active_thread(chat_key)
        previous = thread.active_soul or getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")
        updated = self._thread_store.set_active_soul(chat_key, thread.public_id, loaded.ref)
        if not updated:
            return False, "Failed to set thread soul", previous
        self._persona_audit.log_event(
            scope_type="thread",
            thread_id=thread.id,
            op="soul_set",
            previous_value=previous,
            new_value=loaded.ref,
            status="ok",
        )
        return True, loaded.ref, previous

    def _set_mode_lock(self, chat_id: int, locked: bool) -> tuple[bool, str]:
        chat_key = str(chat_id)
        hatch_state = self._hatch_sessions.get(chat_key)
        if hatch_state and self.control_plane_context:
            cp = self.control_plane_context
            session = cp.session_service.get_session(hatch_state["session_id"])
            agent = cp.agent_service.get_agent(hatch_state["agent_id"])
            if not session or not agent:
                return False, "No active hatched session"
            updated = cp.session_service.set_mode_locked(session.id, locked=locked)
            if not updated:
                return False, "Failed to update mode lock"
            self._persona_audit.log_event(
                scope_type="session",
                session_id=session.id,
                agent_id=agent.id,
                op="mode_lock" if locked else "mode_unlock",
                previous_value=str(session.mode_locked),
                new_value=str(locked),
                status="ok",
            )
            return True, f"Mode {'locked' if locked else 'unlocked'} for session `{session.id}`\\."

        thread = self._thread_state.get_current_thread_row(chat_key) or self._thread_store.get_or_create_active_thread(chat_key)
        updated = self._thread_store.set_mode_locked(chat_key, thread.public_id, locked=locked)
        if not updated:
            return False, "Failed to update mode lock"
        self._persona_audit.log_event(
            scope_type="thread",
            thread_id=thread.id,
            op="mode_lock" if locked else "mode_unlock",
            previous_value=str(thread.mode_locked),
            new_value=str(locked),
            status="ok",
        )
        return True, f"Mode {'locked' if locked else 'unlocked'} for `{thread.public_id}`\\."

    def is_paused(self, chat_id: int) -> bool:
        """Check if a chat is paused."""
        return self._all_paused or chat_id in self._paused_chats
    
    def get_current_mode(self, chat_id: int) -> str:
        """Get the current mode for a chat."""
        persona = self._get_persona_state(chat_id)
        if not persona:
            return str(getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0"))
        return str(persona.get("resolved_mode_ref") or getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0"))

    def get_chat_persona_payload(self, chat_id: int) -> Dict[str, str]:
        persona = self._get_persona_state(chat_id)
        if not persona:
            return {
                "mode": str(getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0")),
                "soul_ref": str(getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")),
            }
        return {
            "mode": str(persona.get("resolved_mode_ref") or getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0")),
            "soul_ref": str(persona.get("resolved_soul_ref") or getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")),
        }

    # =========================================================================
    # Hatch Commands (Phase 19)
    # =========================================================================

    def has_hatch_session(self, chat_id: int) -> bool:
        """Whether chat is bound to a control-plane hatch session."""
        return str(chat_id) in self._hatch_sessions

    async def handle_hatch(self, chat_id: int, user_id: int, args: List[str]) -> str:
        """Handle /hatch command for Telegram-managed control-plane sessions."""
        if not self.control_plane_context:
            return "Hatch is unavailable in this runtime."

        cp = self.control_plane_context
        requested_name = " ".join(args).strip() if args else ""
        if not requested_name:
            requested_name = f"tg-agent-{chat_id}"
        agent_name = requested_name[:48]

        agent = cp.agent_service.get_agent(agent_name)
        if not agent:
            try:
                agent = cp.agent_service.create_agent(
                    name=agent_name,
                    description=f"Telegram hatched agent for chat {chat_id}",
                    tool_profile="balanced",
                    allow_dangerous_override=False,
                    prompt_template_version=cp.config_service.load().values.agent_prompt_template_version,
                )
            except Exception as exc:
                return f"Hatch failed: {exc}"

        try:
            await cp.runtime_supervisor.start_agent(agent.id)
        except Exception as exc:
            cp.agent_service.update_agent(agent.id, {"status": "crashed", "last_error": str(exc)})
            return f"Runtime start failed: {exc}"

        session = cp.session_service.new_session(agent.id, title=f"Telegram chat {chat_id}")
        self._hatch_sessions[str(chat_id)] = {"agent_id": agent.id, "session_id": session.id}

        try:
            boot = await cp.runtime_supervisor.trigger_hatch_boot(
                agent_id=agent.id,
                session_id=session.id,
                user_metadata={"username": str(user_id), "display_name": str(user_id)},
            )
        except Exception as exc:
            cp.agent_service.update_agent(agent.id, {"degraded_reason": f"boot_failed: {exc}", "status": "degraded"})
            return (
                f"Hatched {agent.name} ({agent.id[:8]})\n"
                f"Session: {session.id}\n"
                "First-message boot failed. Agent was kept as degraded."
            )

        return (
            f"Hatched {agent.name} ({agent.id[:8]})\n"
            f"Session: {session.id}\n\n"
            f"{boot}"
        )

    async def handle_identity(self, chat_id: int, user_id: int) -> str:
        """Handle /identity command."""
        if not self.control_plane_context:
            return "Identity is unavailable in this runtime."
        state = self._hatch_sessions.get(str(chat_id))
        if not state:
            return "No active hatched agent in this chat. Use /hatch first."

        cp = self.control_plane_context
        agent = cp.agent_service.get_agent(state["agent_id"])
        if not agent:
            return "Hatched agent not found anymore."

        profile = agent.profile_json or {}
        display_name = profile.get("agent_display_name") or agent.agent_profile_agent_name or agent.name
        voice = profile.get("agent_voice") or []
        principles = profile.get("agent_principles") or []
        lines = [f"Name: {display_name}"]
        if voice:
            lines.append(f"Voice: {', '.join(str(v) for v in voice)}")
        if principles:
            lines.append("Principles: " + "; ".join(str(p) for p in principles[:5]))
        return "\n".join(lines)

    async def handle_rename(self, chat_id: int, user_id: int, args: List[str]) -> str:
        """Handle /rename <name> command."""
        if not self.control_plane_context:
            return "Rename is unavailable in this runtime."
        state = self._hatch_sessions.get(str(chat_id))
        if not state:
            return "No active hatched agent in this chat. Use /hatch first."
        new_name = " ".join(args).strip()
        if len(new_name) < 2 or len(new_name) > 32:
            return "Name must be between 2 and 32 characters."

        cp = self.control_plane_context
        agent = cp.agent_service.get_agent(state["agent_id"])
        if not agent:
            return "Hatched agent not found anymore."

        profile = dict(agent.profile_json or {})
        profile["agent_display_name"] = new_name
        cp.agent_service.update_agent(
            agent.id,
            {
                "agent_profile_agent_name": new_name,
                "profile_json": profile,
            },
        )
        get_memory_store().create_memory(
            memory_type="semantic",
            content=new_name,
            scope=f"agent:{agent.id}",
            source="USER",
            key="agent_display_name",
            confidence=1.0,
            metadata={"scope": "AGENT_SELF"},
        )
        return f"Updated identity name to: {new_name}"

    async def handle_onboard(self, chat_id: int, user_id: int) -> str:
        """Handle /onboard command for re-entering onboarding."""
        if not self.control_plane_context:
            return "Onboarding reset is unavailable in this runtime."
        state = self._hatch_sessions.get(str(chat_id))
        if not state:
            return "No active hatched agent in this chat. Use /hatch first."

        cp = self.control_plane_context
        agent = cp.agent_service.get_agent(state["agent_id"])
        if not agent:
            return "Hatched agent not found anymore."

        cp.agent_service.update_agent(
            agent.id,
            {
                "is_fresh": True,
                "onboarding_state": "WAITING_USER_PREFS",
                "degraded_reason": None,
            },
        )
        try:
            boot = await cp.runtime_supervisor.trigger_hatch_boot(
                agent_id=agent.id,
                session_id=state["session_id"],
                user_metadata={"username": str(user_id), "display_name": str(user_id)},
                overwrite_profile=False,
            )
        except Exception as exc:
            cp.agent_service.update_agent(agent.id, {"degraded_reason": f"boot_failed: {exc}", "status": "degraded"})
            return "Onboarding reset, but boot regeneration failed."
        return boot

    async def handle_chat_message(self, chat_id: int, user_id: int, text: str) -> Optional[str]:
        """Handle normal chat message via control-plane runtime when hatched session exists."""
        if not self.control_plane_context:
            return None
        state = self._hatch_sessions.get(str(chat_id))
        if not state:
            return None

        cp = self.control_plane_context
        try:
            return await cp.runtime_supervisor.chat(
                agent_id=state["agent_id"],
                session_id=state["session_id"],
                message=text,
            )
        except Exception as exc:
            logger.error(
                "Telegram hatched chat failed",
                extra={"event": "telegram_hatched_chat_failed", "chat_id": chat_id, "error": str(exc)},
            )
            return f"Chat failed: {exc}"


__all__ = ["CommandRouter"]
