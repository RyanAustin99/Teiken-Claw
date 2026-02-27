"""Helpers for extracting and stripping hidden tc_profile blocks."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple


_TC_PROFILE_PATTERN = re.compile(r"<tc_profile>\s*(.*?)\s*</tc_profile>", flags=re.IGNORECASE | re.DOTALL)


def extract_tc_profile(raw_text: str) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """Extract first tc_profile JSON block and strip it from visible text.

    Returns:
        (profile_dict, stripped_text, error_message)
    """
    if not raw_text:
        return None, "", None

    match = _TC_PROFILE_PATTERN.search(raw_text)
    if not match:
        return None, raw_text, None

    profile_text = (match.group(1) or "").strip()
    stripped = (raw_text[: match.start()] + raw_text[match.end() :]).lstrip("\r\n ").rstrip()
    try:
        payload = json.loads(profile_text)
        if not isinstance(payload, dict):
            return None, stripped, "tc_profile JSON is not an object"
        return payload, stripped, None
    except Exception as exc:
        # Never leak the raw profile envelope in user-visible content.
        return None, stripped, f"tc_profile parse failed: {exc}"

