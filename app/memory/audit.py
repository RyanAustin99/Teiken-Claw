"""
Memory v1.5 audit helper with redaction.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.memory.audit_store import MemoryAuditStore


SENSITIVE_DETAIL_KEYS = {"content", "value", "raw_text", "message"}


def _redact_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    safe = dict(details or {})
    for key in list(safe.keys()):
        if key.lower() in SENSITIVE_DETAIL_KEYS:
            safe[key] = "[redacted]"
    return safe


class MemoryAuditLogger:
    """Audit logger that enforces detail redaction."""

    def __init__(self, store: Optional[MemoryAuditStore] = None):
        self._store = store or MemoryAuditStore()

    def log(
        self,
        *,
        thread_id: Optional[int],
        agent_id: Optional[str],
        source_message_id: Optional[int],
        op: str,
        memory_id: Optional[int],
        category: Optional[str],
        key: Optional[str],
        status: str,
        reason_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._store.log_event(
            thread_id=thread_id,
            agent_id=agent_id,
            source_message_id=source_message_id,
            op=op,
            memory_id=memory_id,
            category=category,
            key=key,
            status=status,
            reason_code=reason_code,
            details_json=_redact_details(details),
        )
