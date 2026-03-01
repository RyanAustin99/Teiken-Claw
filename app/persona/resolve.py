"""Soul/mode resolution and effective policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Set

from app.modes.registry import LoadedMode, get_mode_registry
from app.souls.registry import LoadedSoul, get_soul_registry

ERR_SOUL_NOT_FOUND = "ERR_SOUL_NOT_FOUND"
ERR_MODE_NOT_FOUND = "ERR_MODE_NOT_FOUND"
ERR_MODE_LOCKED = "ERR_MODE_LOCKED"
ERR_SOUL_SCHEMA_INVALID = "ERR_SOUL_SCHEMA_INVALID"
ERR_MODE_SCHEMA_INVALID = "ERR_MODE_SCHEMA_INVALID"
ERR_PERSONA_REF_INVALID = "ERR_PERSONA_REF_INVALID"

MODE_ALIASES: Dict[str, str] = {
    "default": "builder",
    "operator": "builder",
    "coder": "builder",
    "researcher": "research",
    "coding": "builder",
    "analysis": "architect",
    "precise": "minimal",
    "creative": "research",
}

TOOL_NAME_ALIASES: Dict[str, str] = {
    "web.search": "web",
}

PLATFORM_PROFILE_TOOL_ALLOWLIST: Dict[str, Set[str]] = {
    "safe": {"echo", "time", "status", "files.read", "files.list", "files.exists", "web"},
    "balanced": {
        "echo",
        "time",
        "status",
        "files.read",
        "files.list",
        "files.exists",
        "files.write",
        "web",
        "exec",
    },
    "dangerous": set(),
}


class PersonaResolutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedPersona:
    soul: LoadedSoul
    mode: LoadedMode
    resolved_soul_ref: str
    resolved_mode_ref: str
    effective_allowed_tools: Optional[Set[str]]
    max_tool_turns: Optional[int]
    effective_file_policy: Dict[str, Any]


def _normalize_mode_name(name_or_ref: str) -> str:
    raw = (name_or_ref or "").strip()
    if not raw:
        return raw
    if "@" in raw:
        mode_name, version = raw.split("@", 1)
        canonical = MODE_ALIASES.get(mode_name.strip().lower(), mode_name.strip().lower())
        return f"{canonical}@{version.strip()}"
    return MODE_ALIASES.get(raw.lower(), raw.lower())


def _resolve_soul_ref(soul_ref: Optional[str]) -> LoadedSoul:
    registry = get_soul_registry()
    if soul_ref:
        try:
            return registry.get_soul(soul_ref)
        except KeyError as exc:
            raise PersonaResolutionError(ERR_SOUL_NOT_FOUND, f"Unknown soul: {soul_ref}") from exc
    return registry.get_default_soul()


def _resolve_mode_ref(mode_ref: Optional[str]) -> LoadedMode:
    registry = get_mode_registry()
    if mode_ref:
        normalized = _normalize_mode_name(mode_ref)
        try:
            return registry.get_mode(normalized)
        except KeyError as exc:
            raise PersonaResolutionError(ERR_MODE_NOT_FOUND, f"Unknown mode: {mode_ref}") from exc
    return registry.get_default_mode()


def _build_effective_allowed_tools(
    *,
    profile: str,
    soul_allowed_tools: Iterable[str],
    mode_avoid_tools: Iterable[str],
) -> Optional[Set[str]]:
    normalized_profile = (profile or "safe").strip().lower()
    platform_allowed = PLATFORM_PROFILE_TOOL_ALLOWLIST.get(normalized_profile)
    if platform_allowed is None:
        platform_allowed = PLATFORM_PROFILE_TOOL_ALLOWLIST["safe"]

    canonical_soul_allowed = {
        _canonical_tool_name(item.strip())
        for item in soul_allowed_tools
        if item and item.strip()
    }
    canonical_mode_avoid = {
        _canonical_tool_name(item.strip())
        for item in mode_avoid_tools
        if item and item.strip()
    }

    if normalized_profile == "dangerous":
        if "*" in canonical_soul_allowed:
            return None
        allowed = set(canonical_soul_allowed)
    else:
        if "*" in canonical_soul_allowed:
            allowed = set(platform_allowed)
        else:
            allowed = set(platform_allowed) & canonical_soul_allowed

    for tool in canonical_mode_avoid:
        allowed.discard(tool)

    return allowed


def _canonical_tool_name(tool_name: str) -> str:
    return TOOL_NAME_ALIASES.get(tool_name, tool_name)


def build_effective_file_policy(base_policy: Dict[str, Any], *overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    effective = dict(base_policy)
    for override in overrides:
        if not override:
            continue
        if "max_read_bytes" in override and override["max_read_bytes"] is not None:
            effective["max_read_bytes"] = min(int(effective.get("max_read_bytes", override["max_read_bytes"])), int(override["max_read_bytes"]))
        if "max_write_bytes" in override and override["max_write_bytes"] is not None:
            effective["max_write_bytes"] = min(int(effective.get("max_write_bytes", override["max_write_bytes"])), int(override["max_write_bytes"]))
        if "allowed_extensions" in override and override["allowed_extensions"]:
            base_ext = {str(item).lower() for item in effective.get("allowed_extensions", [])}
            incoming = {str(item).lower() for item in override["allowed_extensions"]}
            effective["allowed_extensions"] = sorted(base_ext & incoming) if base_ext else sorted(incoming)
    return effective


def resolve_persona(
    *,
    mode_ref: Optional[str],
    soul_ref: Optional[str],
    tool_profile: str,
    base_file_policy: Optional[Dict[str, Any]] = None,
) -> ResolvedPersona:
    soul = _resolve_soul_ref(soul_ref)
    mode = _resolve_mode_ref(mode_ref)

    allowed = _build_effective_allowed_tools(
        profile=tool_profile,
        soul_allowed_tools=soul.definition.constraints.allowed_tools,
        mode_avoid_tools=mode.definition.tool_bias.avoid,
    )

    effective_file_policy = build_effective_file_policy(
        base_file_policy or {},
        soul.definition.constraints.file_policy_override,
    )

    return ResolvedPersona(
        soul=soul,
        mode=mode,
        resolved_soul_ref=soul.ref,
        resolved_mode_ref=mode.ref,
        effective_allowed_tools=allowed,
        max_tool_turns=mode.definition.tool_bias.max_tool_turns,
        effective_file_policy=effective_file_policy,
    )
