"""
CLI Interface for Teiken Claw.

This module provides:
- CLIInterface class for interactive REPL
- Support for ENABLE_CLI flag
- Job creation and enqueueing
- Response printing to console
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional, Callable, Any

from app.config.logging import get_logger
from app.config.settings import settings
from app.queue.jobs import Job, JobSource, JobType, JobPriority, create_job
from app.queue.dispatcher import get_dispatcher
from app.queue.throttles import get_outbound_queue

logger = get_logger(__name__)


class CLIInterface:
    """
    Interactive CLI interface for Teiken Claw.
    
    Features:
    - Interactive REPL loop
    - Command processing
    - Job creation and enqueueing
    - Response handling
    
    Attributes:
        is_running: Whether the CLI is currently running
        session_id: Current session ID
    """
    
    # CLI prompt
    PROMPT = "teiken> "
    
    # CLI commands
    COMMANDS = {
        "/help": "Show available commands",
        "/exit": "Exit the CLI",
        "/quit": "Exit the CLI",
        "/status": "Show system status",
        "/mode": "Show or change mode",
        "/clear": "Clear the screen",
        "/history": "Show command history",
    }
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        on_response: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the CLI interface.
        
        Args:
            session_id: Optional session ID for tracking
            on_response: Optional callback for handling responses
        """
        self.session_id = session_id or f"cli_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.on_response = on_response
        self._running = False
        self._history: list = []
        self._current_mode = "default"
        self._dispatcher = None
        self._outbound_queue = None
        
        logger.info(
            f"CLIInterface initialized with session {self.session_id}",
            extra={"event": "cli_initialized", "session_id": self.session_id}
        )
    
    @property
    def is_running(self) -> bool:
        """Check if the CLI is running."""
        return self._running
    
    async def start(self) -> None:
        """
        Start the CLI interface.
        
        Initializes the REPL loop.
        """
        if not settings.ENABLE_CLI:
            logger.info(
                "CLI is disabled in settings",
                extra={"event": "cli_disabled"}
            )
            print("CLI is disabled. Set ENABLE_CLI=true to enable.")
            return
        
        self._running = True
        self._dispatcher = get_dispatcher()
        self._outbound_queue = get_outbound_queue()
        
        self._print_welcome()
        
        # Start REPL loop
        await self._repl_loop()
    
    async def stop(self) -> None:
        """Stop the CLI interface."""
        self._running = False
        logger.info(
            "CLI stopped",
            extra={"event": "cli_stopped", "session_id": self.session_id}
        )
    
    def _print_welcome(self) -> None:
        """Print welcome message."""
        print("\n" + "=" * 50)
        print("  Teiken Claw - AI Assistant CLI")
        print("=" * 50)
        print(f"\n  Session: {self.session_id}")
        print(f"  Mode: {self._current_mode}")
        print("\n  Type /help for available commands")
        print("  Type your message to chat with the AI")
        print("\n" + "-" * 50 + "\n")
    
    async def _repl_loop(self) -> None:
        """Run the REPL loop."""
        while self._running:
            try:
                # Get input
                user_input = await self._get_input()
                
                if not user_input:
                    continue
                
                # Add to history
                self._history.append({
                    "input": user_input,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                # Process input
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                else:
                    await self._handle_message(user_input)
                
            except KeyboardInterrupt:
                print("\n\nUse /exit to quit.")
            except EOFError:
                print("\n\nGoodbye!")
                await self.stop()
            except Exception as e:
                logger.error(
                    f"Error in REPL loop: {e}",
                    extra={"event": "cli_repl_error"},
                    exc_info=True
                )
                print(f"\nError: {e}\n")
    
    async def _get_input(self) -> str:
        """
        Get user input asynchronously.
        
        Returns:
            str: User input
        """
        # Use asyncio to run input in a thread
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input(self.PROMPT).strip())
    
    async def _handle_command(self, command: str) -> None:
        """
        Handle a CLI command.
        
        Args:
            command: Command string (starts with /)
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in ("/exit", "/quit"):
            print("\nGoodbye!")
            await self.stop()
        
        elif cmd == "/help":
            self._print_help()
        
        elif cmd == "/status":
            await self._print_status()
        
        elif cmd == "/mode":
            self._handle_mode_command(args)
        
        elif cmd == "/clear":
            self._clear_screen()
        
        elif cmd == "/history":
            self._print_history()
        
        else:
            print(f"\nUnknown command: {cmd}")
            print("Type /help for available commands.\n")
    
    def _print_help(self) -> None:
        """Print help message."""
        print("\n" + "-" * 50)
        print("  Available Commands")
        print("-" * 50)
        
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:<15} - {desc}")
        
        print("\n  Any other input will be sent to the AI.\n")
    
    async def _print_status(self) -> None:
        """Print system status."""
        print("\n" + "-" * 50)
        print("  System Status")
        print("-" * 50)
        
        # Queue status
        if self._dispatcher:
            queue_depth = self._dispatcher.queue_depth
            print(f"  Queue Depth: {queue_depth}")
        else:
            print("  Queue: Not available")
        
        # Session info
        print(f"  Session: {self.session_id}")
        print(f"  Mode: {self._current_mode}")
        print(f"  History: {len(self._history)} entries")
        
        print("-" * 50 + "\n")
    
    def _handle_mode_command(self, args: str) -> None:
        """Handle /mode command."""
        modes = ["default", "architect", "operator", "coder", "researcher"]
        
        if not args:
            print(f"\n  Current Mode: {self._current_mode}")
            print(f"  Available modes: {', '.join(modes)}\n")
            return
        
        new_mode = args.strip().lower()
        if new_mode not in modes:
            print(f"\n  Invalid mode: {new_mode}")
            print(f"  Available modes: {', '.join(modes)}\n")
            return
        
        old_mode = self._current_mode
        self._current_mode = new_mode
        
        print(f"\n  Mode changed: {old_mode} → {new_mode}\n")
        
        logger.info(
            f"CLI mode changed from {old_mode} to {new_mode}",
            extra={
                "event": "cli_mode_changed",
                "session_id": self.session_id,
                "old_mode": old_mode,
                "new_mode": new_mode,
            }
        )
    
    def _clear_screen(self) -> None:
        """Clear the terminal screen."""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        self._print_welcome()
    
    def _print_history(self) -> None:
        """Print command history."""
        print("\n" + "-" * 50)
        print("  Command History")
        print("-" * 50)
        
        if not self._history:
            print("  No history yet.")
        else:
            for i, entry in enumerate(self._history[-20:], 1):
                timestamp = entry.get("timestamp", "unknown")
                user_input = entry.get("input", "")
                print(f"  {i}. [{timestamp}] {user_input[:50]}...")
        
        print("-" * 50 + "\n")
    
    async def _handle_message(self, text: str) -> None:
        """
        Handle a non-command message.
        
        Creates a Job and enqueues it to the dispatcher.
        
        Args:
            text: Message text
        """
        if not self._dispatcher:
            print("\n  Error: Dispatcher not available.\n")
            return
        
        # Create job
        payload = {
            "text": text,
            "source": "cli",
            "mode": self._current_mode,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        job = create_job(
            source=JobSource.CLI,
            type=JobType.CHAT_MESSAGE,
            payload=payload,
            priority=JobPriority.INTERACTIVE,
            session_id=self.session_id,
        )
        
        # Enqueue job
        try:
            await self._dispatcher.enqueue(job)
            
            logger.info(
                f"CLI message enqueued as job {job.job_id}",
                extra={
                    "event": "cli_message_enqueued",
                    "job_id": job.job_id,
                    "session_id": self.session_id,
                }
            )
            
            print(f"\n  [Job {job.job_id[:8]}...] Processing...\n")
            
            # Wait for response (simplified - in real implementation, 
            # this would be handled by a callback or polling)
            await self._wait_for_response(job.job_id)
            
        except Exception as e:
            logger.error(
                f"Failed to enqueue CLI message: {e}",
                extra={"event": "cli_enqueue_error"},
                exc_info=True
            )
            print(f"\n  Error: {e}\n")
    
    async def _wait_for_response(self, job_id: str, timeout: float = 120.0) -> None:
        """
        Wait for a response to be processed.
        
        This is a simplified implementation. In a full implementation,
        this would use callbacks or polling to get the actual response.
        
        Args:
            job_id: Job ID to wait for
            timeout: Maximum time to wait
        """
        # For now, just indicate that the job was submitted
        # The actual response handling would be done through the
        # worker pool and result formatting
        print("  [Waiting for response...]")
        print("  (Response will be processed by worker pool)")
        print()


# =============================================================================
# Standalone CLI Entry Point
# =============================================================================

async def run_cli() -> None:
    """Run the CLI interface as a standalone application."""
    cli = CLIInterface()
    await cli.start()


def main() -> None:
    """Main entry point for CLI."""
    if not settings.ENABLE_CLI:
        print("CLI is disabled. Set ENABLE_CLI=true in settings.")
        sys.exit(1)
    
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")


# =============================================================================
# Global Instance Management
# =============================================================================

_cli_interface: Optional[CLIInterface] = None


def get_cli_interface() -> Optional[CLIInterface]:
    """Get the global CLIInterface instance."""
    return _cli_interface


def set_cli_interface(cli: Optional[CLIInterface]) -> None:
    """Set the global CLIInterface instance."""
    global _cli_interface
    _cli_interface = cli


__all__ = [
    "CLIInterface",
    "run_cli",
    "main",
    "get_cli_interface",
    "set_cli_interface",
]
