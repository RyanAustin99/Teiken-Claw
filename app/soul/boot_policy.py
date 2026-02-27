"""Boot directives policy for fresh hatched agents."""

from __future__ import annotations

from typing import Any


DEFAULT_BOOT_DIRECTIVES = (
    "Speak naturally, briefly, and warmly. "
    "Ask what to call the user and what to call yourself. "
    "Ask purpose only if it fits naturally. "
    "Use first person (I/me). Never use 'this agent'. "
    "Do not use numbered lists, bullet lists, or headings. "
    "Avoid meta AI phrasing."
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

