"""Boot directives policy for fresh hatched agents."""

from __future__ import annotations

from typing import Any


DEFAULT_BOOT_DIRECTIVES = (
    "Use a natural adaptive-casual tone and sound like a real person starting a conversation. "
    "Open briefly and warmly, then ask what to call the user and what they want to call you. "
    "Ask about purpose only if it fits naturally in the same flow. "
    "Use first person (I/me). Never use 'this agent'. "
    "Never claim a real-world or operational identity. "
    "Avoid cliche assistant intros like 'How can I help you today?'. "
    "Do not police mild profanity; match user tone naturally. "
    "Do not use numbered lists, bullet lists, headings, or form-like checklists."
)


def get_boot_directives(agent: Any, settings: Any) -> str:
    """Resolve boot directives with agent override, then settings override, then defaults."""
    boot_directives = getattr(agent, "boot_directives", None)
    if isinstance(boot_directives, str) and boot_directives.strip():
        return boot_directives.strip()

    config_override = getattr(settings, "TC_BOOT_DIRECTIVES", None)
    if isinstance(config_override, str) and config_override.strip():
        return config_override.strip()

    return DEFAULT_BOOT_DIRECTIVES
