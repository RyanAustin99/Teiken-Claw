"""
Deterministic memory extraction rules for Memory v1.5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.memory.secret_filter import looks_like_secret


TRIGGER_PHRASES = (
    "remember that",
    "from now on",
    "always",
    "never",
    "my preference is",
    "call me",
    "default should be",
    "we decided",
)

ALLOWED_CATEGORIES = {
    "identity",
    "preference",
    "project_setting",
    "workflow",
    # Compatibility categories retained for legacy callers/tests.
    "project",
    "fact",
    "note",
    "environment",
    "schedule_pattern",
}

BLOCKED_CATEGORY_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(account|routing)\s+number\b", re.IGNORECASE), "ERR_MEM_BLOCKED_CATEGORY"),
    (re.compile(r"\b(credit\s*card|card\s*number)\b", re.IGNORECASE), "ERR_MEM_BLOCKED_CATEGORY"),
    (re.compile(r"\b(health|diagnosis|medication|medical)\b", re.IGNORECASE), "ERR_MEM_BLOCKED_CATEGORY"),
    (re.compile(r"\b(ssn|social security|passport number)\b", re.IGNORECASE), "ERR_MEM_BLOCKED_CATEGORY"),
)


@dataclass(frozen=True)
class MemoryCandidate:
    category: str
    key: str
    value: str
    confidence: float = 1.0


class MemoryExtractionRules:
    """Deterministic extraction rules and policy checks."""

    def should_consider_memory(self, message_text: str) -> bool:
        text = (message_text or "").strip().lower()
        if not text:
            return False
        return any(phrase in text for phrase in TRIGGER_PHRASES)

    def blocked_category_filter(self, text: str) -> Tuple[bool, Optional[str]]:
        body = text or ""
        secret_like, reason = looks_like_secret(body)
        if secret_like:
            return True, reason
        for pattern, code in BLOCKED_CATEGORY_PATTERNS:
            if pattern.search(body):
                return True, code
        return False, None

    def extract_candidate(self, message_text: str) -> Optional[MemoryCandidate]:
        text = (message_text or "").strip()
        if not text:
            return None

        # 1) identity.preferred_name
        identity_match = re.search(r"\b(?:call me|my name is)\s+([A-Za-z][A-Za-z0-9 _'\-]{0,48})", text, re.IGNORECASE)
        if identity_match:
            return MemoryCandidate(category="identity", key="preferred_name", value=identity_match.group(1).strip())

        # 2) project_setting.default_*
        default_match = re.search(r"\bdefault\s+(.+?)\s+(?:should be|is)\s+(.+)$", text, re.IGNORECASE)
        if default_match:
            lhs = default_match.group(1).strip().lower()
            rhs = default_match.group(2).strip()
            key = self._project_setting_key(lhs)
            if key:
                return MemoryCandidate(category="project_setting", key=key, value=rhs)

        # 3) preference
        pref_match = re.search(r"\b(?:my preference is|i prefer)\s+(.+)$", text, re.IGNORECASE)
        if pref_match:
            value = pref_match.group(1).strip()
            key = self._preference_key(value)
            if key:
                return MemoryCandidate(category="preference", key=key, value=value)

        # 4) explicit team decision
        decided_match = re.search(r"\bwe decided\s+(.+)$", text, re.IGNORECASE)
        if decided_match:
            value = decided_match.group(1).strip()
            if value:
                return MemoryCandidate(category="project_setting", key="decision", value=value)

        # 5) workflow directives
        workflow_match = re.search(r"\bfrom now on[, ]+always\s+(.+)$", text, re.IGNORECASE)
        if workflow_match:
            value = workflow_match.group(1).strip()
            if value:
                return MemoryCandidate(category="workflow", key="default_rule", value=value)

        return None

    def dedupe_key(self, category: str, key: str) -> str:
        return f"{(category or '').strip().lower()}:{(key or '').strip().lower()}"

    def _project_setting_key(self, lhs: str) -> Optional[str]:
        if "write cap" in lhs or "max write" in lhs:
            return "write_cap"
        if "read cap" in lhs or "max read" in lhs:
            return "read_cap"
        if "mode" in lhs:
            return "mode_default"
        clean = re.sub(r"[^a-z0-9]+", "_", lhs).strip("_")
        if not clean:
            return None
        return clean[:64]

    def _preference_key(self, value: str) -> Optional[str]:
        lower = value.lower()
        if "concise" in lower:
            return "tone"
        if "verbose" in lower:
            return "tone"
        if "markdown" in lower or "format" in lower:
            return "format"
        return "general"

    # ---------------------------------------------------------------------
    # Backward-compatible wrappers for existing callers/tests.
    # ---------------------------------------------------------------------

    def classify_candidates(self, candidates: List[str]) -> List[Dict]:
        results: List[Dict] = []
        for item in candidates:
            blocked, reason = self.blocked_category_filter(item)
            if blocked:
                continue
            candidate = self.extract_candidate(item)
            if not candidate:
                continue
            results.append(
                {
                    "content": candidate.value,
                    "category": candidate.category,
                    "key": candidate.key,
                    "confidence": candidate.confidence,
                }
            )
        return results

    def is_allowed_category(self, category: str) -> bool:
        return (category or "").strip().lower() in ALLOWED_CATEGORIES

    def is_sensitive_content(self, content: str) -> bool:
        blocked, reason = self.blocked_category_filter(content or "")
        return bool(blocked and reason is not None)

    def get_category(self, content: str) -> Optional[str]:
        text = (content or "").strip()
        candidate = self.extract_candidate(text)
        if candidate:
            return candidate.category
        lower = text.lower()
        if "project" in lower:
            return "project"
        if "prefer" in lower or "preference" in lower:
            return "preference"
        if re.search(r"\b(is|are|was|were|has|have)\b", lower):
            return "fact"
        if lower:
            return "note"
        return None

    def extract_facts(self, content: str) -> List[str]:
        text = (content or "").strip()
        if not text:
            return []
        # keep deterministic and conservative for compatibility paths
        segments = [segment.strip() for segment in re.split(r"[.!?]\s*", text) if segment.strip()]
        return [segment for segment in segments if len(segment.split()) >= 4][:3]

    def extract_preferences(self, content: str) -> List[str]:
        text = (content or "").strip()
        matches = re.findall(r"\b(?:my preference is|i prefer)\s+([^.!?]+)", text, re.IGNORECASE)
        return [m.strip() for m in matches if m.strip()][:3]


_extraction_rules: Optional[MemoryExtractionRules] = None


def get_extraction_rules() -> MemoryExtractionRules:
    global _extraction_rules
    if _extraction_rules is None:
        _extraction_rules = MemoryExtractionRules()
    return _extraction_rules


def set_extraction_rules(rules: MemoryExtractionRules) -> None:
    global _extraction_rules
    _extraction_rules = rules
