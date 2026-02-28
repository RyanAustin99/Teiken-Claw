"""Linter for first boot message quality constraints."""

from __future__ import annotations

import re
from typing import Any, List


def lint_boot_message(text: str, settings: Any) -> List[str]:
    """Return a list of lint problems for a boot message."""
    problems: List[str] = []
    normalized = (text or "").strip()
    lowered = normalized.lower()

    forbidden_phrases = getattr(settings, "TC_BOOT_FORBIDDEN_PHRASES", []) or []
    for phrase in forbidden_phrases:
        if phrase and phrase.lower() in lowered:
            problems.append(f"contains forbidden phrase: {phrase}")

    canned_phrases = getattr(settings, "TC_BOOT_CANNED_PHRASES", []) or []
    for phrase in canned_phrases:
        if phrase and phrase.lower() in lowered:
            problems.append(f"contains canned assistant phrasing: {phrase}")
            break
    if re.search(r"\bhello\b.{0,40}\bi am (your )?(agent|assistant)\b", lowered):
        problems.append("contains canned assistant intro")

    markers = getattr(settings, "TC_BOOT_LIST_MARKERS", []) or []
    lines = normalized.splitlines()
    for line in lines:
        for marker in markers:
            try:
                if re.search(marker, line):
                    problems.append("contains list formatting")
                    break
            except re.error:
                continue
        if "contains list formatting" in problems:
            break

    max_questions = int(getattr(settings, "TC_BOOT_MAX_QUESTIONS", 2) or 2)
    questions = normalized.count("?")
    if questions > max_questions:
        problems.append(f"too many questions: {questions}")

    max_words = int(getattr(settings, "TC_BOOT_MAX_WORDS", 140) or 140)
    words = len([token for token in re.split(r"\s+", normalized) if token])
    if words > max_words:
        problems.append(f"too many words: {words}")

    return problems
