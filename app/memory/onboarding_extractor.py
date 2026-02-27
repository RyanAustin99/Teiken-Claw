"""Onboarding preference extraction helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


_NAME_PATTERNS = [
    re.compile(r"\bcall me\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bmy name is\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bname'?s\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
]

_AGENT_NAME_PATTERNS = [
    re.compile(r"\bcall (?:yourself|you)\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bi(?:'ll| will)\s+call you\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\byour name should be\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
]

_PURPOSE_PATTERNS = [
    re.compile(r"\byour job is to\s+(.+)$", re.IGNORECASE),
    re.compile(r"\byour purpose is\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bi need you to\s+(.+)$", re.IGNORECASE),
]

_TONE_PATTERNS = [
    re.compile(r"\b(be|sound)\s+(casual|direct|formal|witty|friendly|concise)\b", re.IGNORECASE),
    re.compile(r"\bkeep it\s+(casual|direct|formal|witty|friendly|concise)\b", re.IGNORECASE),
]


def extract_onboarding_prefs(
    user_text: str,
    last_assistant_text: str,
    agent_profile_json: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Extract onboarding preferences conservatively from user text."""
    text = (user_text or "").strip()
    result: Dict[str, Optional[str]] = {
        "user_preferred_name": None,
        "agent_name_preference": None,
        "agent_purpose": None,
        "tone_preference": None,
    }

    if not text:
        return result

    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            result["user_preferred_name"] = _sanitize_name(match.group(1))
            break

    for pattern in _AGENT_NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            result["agent_name_preference"] = _sanitize_name(match.group(1))
            break

    for pattern in _PURPOSE_PATTERNS:
        match = pattern.search(text)
        if match:
            purpose = _sanitize_text(match.group(1))
            if purpose:
                result["agent_purpose"] = purpose
            break

    for pattern in _TONE_PATTERNS:
        match = pattern.search(text)
        if match:
            tone = _sanitize_text(match.group(2))
            if tone:
                result["tone_preference"] = tone.lower()
            break

    return result


def parse_llm_onboarding_json(raw: str) -> Dict[str, Optional[str]]:
    """Parse strict JSON output from fallback LLM extractor."""
    payload = raw.strip()
    if not payload:
        return {
            "user_preferred_name": None,
            "agent_name_preference": None,
            "agent_purpose": None,
            "tone_preference": None,
        }
    if "{" in payload and "}" in payload:
        payload = payload[payload.find("{") : payload.rfind("}") + 1]
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("LLM onboarding extractor payload is not an object")

    parsed = {
        "user_preferred_name": _sanitize_name(data.get("user_preferred_name")),
        "agent_name_preference": _sanitize_name(data.get("agent_name_preference")),
        "agent_purpose": _sanitize_text(data.get("agent_purpose")),
        "tone_preference": _sanitize_text(data.get("tone_preference")),
    }
    if parsed["tone_preference"]:
        parsed["tone_preference"] = parsed["tone_preference"].lower()
    return parsed


def _sanitize_name(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip(".,!?")
    if not cleaned:
        return None
    if len(cleaned) < 2 or len(cleaned) > 32:
        return None
    return cleaned


def _sanitize_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > 240:
        cleaned = cleaned[:240].rstrip()
    return cleaned


__all__ = [
    "extract_onboarding_prefs",
    "parse_llm_onboarding_json",
]

