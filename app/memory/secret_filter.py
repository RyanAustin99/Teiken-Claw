"""
Secret detection for memory extraction safety.
"""

from __future__ import annotations

import math
import re
from typing import Optional, Tuple


SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bxoxb-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{12,}\b"),
    re.compile(r"\bapi[_\-\s]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.IGNORECASE),
    re.compile(r"\b(password|token|api[_\s-]?key)\s+is\s+\S+", re.IGNORECASE),
]


def _shannon_entropy(token: str) -> float:
    if not token:
        return 0.0
    probs = [token.count(c) / len(token) for c in set(token)]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def looks_like_secret(text: str) -> Tuple[bool, Optional[str]]:
    source = text or ""
    for pattern in SECRET_PATTERNS:
        if pattern.search(source):
            return True, "ERR_MEM_SECRET_DETECTED"

    # conservative high-entropy detector for long compact tokens
    for token in re.findall(r"[A-Za-z0-9_\-]{24,}", source):
        if _shannon_entropy(token) >= 3.5:
            return True, "ERR_MEM_SECRET_DETECTED"

    return False, None
