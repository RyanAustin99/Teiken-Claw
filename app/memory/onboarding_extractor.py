"""Onboarding preference extraction helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


_NAME_PATTERNS = [
    re.compile(r"\bcall me\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\byou can call me\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bmy name is\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
]

_AGENT_NAME_PATTERNS = [
    re.compile(r"\bcall (?:yourself|you)\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\byou can call yourself\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\bi(?:'ll| will)\s+call you\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\byour name should be\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
    re.compile(r"\byour name is\s+([A-Za-z][\w\-]{1,31})\b", re.IGNORECASE),
]

_PURPOSE_PATTERNS = [
    re.compile(r"\byour job is to\s+(.+)$", re.IGNORECASE),
    re.compile(r"\byour purpose is\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bi want you to\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bi need you to\s+(.+)$", re.IGNORECASE),
]

_TONE_PATTERNS = [
    re.compile(r"\b(be|sound)\s+(casual|direct|formal|witty|friendly|concise)\b", re.IGNORECASE),
    re.compile(r"\bkeep it\s+(casual|direct|formal|witty|friendly|concise)\b", re.IGNORECASE),
]

_PROFANITY_PATTERNS = [
    re.compile(r"\b(you can|feel free to|please)\s+(swear|cuss|use profanity)\b", re.IGNORECASE),
    re.compile(r"\b(swear|cuss|profanity)\s+(is|it's|its)\s+(fine|ok|okay|allowed)\b", re.IGNORECASE),
    re.compile(r"\b(no|dont|don't)\s+(swearing|cussing|profanity)\b", re.IGNORECASE),
    re.compile(r"\b(keep it clean|no cussing|no cursing)\b", re.IGNORECASE),
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
        "profanity_level": None,
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
            tone_group = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
            tone = _sanitize_text(tone_group)
            if tone:
                result["tone_preference"] = tone.lower()
            break

    lowered = text.lower()
    for pattern in _PROFANITY_PATTERNS:
        if not pattern.search(text):
            continue
        if "no " in lowered or "don't" in lowered or "dont" in lowered or "keep it clean" in lowered:
            result["profanity_level"] = "none"
        elif "swear" in lowered or "cuss" in lowered or "profanity" in lowered:
            result["profanity_level"] = "allowed"
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
            "profanity_level": None,
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
        "profanity_level": _sanitize_text(data.get("profanity_level")),
    }
    if parsed["tone_preference"]:
        parsed["tone_preference"] = parsed["tone_preference"].lower()
    if parsed["profanity_level"]:
        parsed["profanity_level"] = parsed["profanity_level"].lower()
    return parsed


def parse_llm_onboarding_json_with_confidence(
    raw: str,
) -> tuple[Dict[str, Optional[str]], Dict[str, float]]:
    parsed = parse_llm_onboarding_json(raw)
    payload = raw.strip()
    confidences: Dict[str, float] = {
        "user_preferred_name": 0.0,
        "agent_name_preference": 0.0,
        "agent_purpose": 0.0,
        "tone_preference": 0.0,
        "profanity_level": 0.0,
    }
    if not payload:
        return parsed, confidences
    if "{" in payload and "}" in payload:
        payload = payload[payload.find("{") : payload.rfind("}") + 1]
    data = json.loads(payload)
    if not isinstance(data, dict):
        return parsed, confidences

    field_conf = data.get("confidence")
    if isinstance(field_conf, dict):
        for key in list(confidences.keys()):
            confidences[key] = _normalize_confidence(field_conf.get(key))
    else:
        global_conf = _normalize_confidence(data.get("confidence_score"))
        if global_conf > 0:
            for key in list(confidences.keys()):
                confidences[key] = global_conf
    return parsed, confidences


def _normalize_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


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
    "parse_llm_onboarding_json_with_confidence",
]
