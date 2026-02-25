# Interfaces package
"""
Interfaces module for Teiken Claw.

Contains API interfaces and external integrations:
- TelegramBot: Telegram bot implementation
- TelegramSender: Telegram message sender with retry logic
- CommandRouter: Command handling for Telegram commands
- TelegramAdapter: Message format conversion
- CLIInterface: Interactive CLI for local use
"""

from app.interfaces.telegram_bot import (
    TelegramBot,
    HAS_TELEGRAM,
    get_telegram_bot,
    set_telegram_bot,
)

from app.interfaces.telegram_sender import (
    TelegramSender,
    get_telegram_sender,
    set_telegram_sender,
)

from app.interfaces.telegram_commands import CommandRouter

from app.interfaces.adapters import (
    TelegramAdapter,
    escape_markdown_v2,
    escape_html,
    format_for_telegram,
)

from app.interfaces.cli import (
    CLIInterface,
    run_cli,
    get_cli_interface,
    set_cli_interface,
)


__all__ = [
    # Telegram Bot
    "TelegramBot",
    "HAS_TELEGRAM",
    "get_telegram_bot",
    "set_telegram_bot",
    # Telegram Sender
    "TelegramSender",
    "get_telegram_sender",
    "set_telegram_sender",
    # Command Router
    "CommandRouter",
    # Adapters
    "TelegramAdapter",
    "escape_markdown_v2",
    "escape_html",
    "format_for_telegram",
    # CLI
    "CLIInterface",
    "run_cli",
    "get_cli_interface",
    "set_cli_interface",
]
