"""
Deterministic memory extraction orchestrator for v1.5.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.memory.audit import MemoryAuditLogger
from app.memory.error_codes import (
    ERR_MEM_BLOCKED_CATEGORY,
    ERR_MEM_NOT_ELIGIBLE,
    ERR_MEM_PAUSED,
)
from app.memory.extraction_rules import MemoryExtractionRules, get_extraction_rules
from app.memory.memory_store_v15 import MemoryStoreV15


class MemoryExtractor:
    """Process user messages into deterministic memory cards."""

    def __init__(
        self,
        rules: Optional[MemoryExtractionRules] = None,
        memory_store: Optional[MemoryStoreV15] = None,
        audit_logger: Optional[MemoryAuditLogger] = None,
    ):
        self._rules = rules or get_extraction_rules()
        self._memory_store = memory_store or MemoryStoreV15()
        self._audit = audit_logger or MemoryAuditLogger()

    def process_user_message(
        self,
        *,
        thread_id: int,
        memory_enabled: bool,
        message_text: str,
        source_message_id: int,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not memory_enabled:
            return self._failure("extract", ERR_MEM_PAUSED, "Memory is paused for this thread.")

        if not self._rules.should_consider_memory(message_text):
            return self._failure("extract", ERR_MEM_NOT_ELIGIBLE, "Message does not meet memory triggers.")

        blocked, reason = self._rules.blocked_category_filter(message_text)
        if blocked:
            self._audit.log(
                thread_id=thread_id,
                agent_id=agent_id,
                source_message_id=source_message_id,
                op="blocked",
                memory_id=None,
                category=None,
                key=None,
                status="blocked",
                reason_code=reason,
                details={"why": "blocked_by_filter"},
            )
            return self._failure(
                "extract",
                reason or ERR_MEM_BLOCKED_CATEGORY,
                "I won't store sensitive or blocked information.",
                hint="If you meant a preference, rephrase without credentials or sensitive details.",
            )

        candidate = self._rules.extract_candidate(message_text)
        if not candidate:
            return self._failure(
                "extract",
                ERR_MEM_NOT_ELIGIBLE,
                "No deterministic memory mapping found for this message.",
            )

        blocked_value, reason_value = self._rules.blocked_category_filter(candidate.value)
        if blocked_value:
            self._audit.log(
                thread_id=thread_id,
                agent_id=agent_id,
                source_message_id=source_message_id,
                op="blocked",
                memory_id=None,
                category=candidate.category,
                key=candidate.key,
                status="blocked",
                reason_code=reason_value,
                details={"why": "candidate_value_blocked"},
            )
            return self._failure(
                "extract",
                reason_value or ERR_MEM_BLOCKED_CATEGORY,
                "I won't store sensitive or blocked information.",
            )

        memory, action = self._memory_store.upsert_memory(
            thread_id=thread_id,
            category=candidate.category,
            key=candidate.key,
            value=candidate.value,
            source_message_id=source_message_id,
            confidence=candidate.confidence,
        )
        self._audit.log(
            thread_id=thread_id,
            agent_id=agent_id,
            source_message_id=source_message_id,
            op=action,
            memory_id=memory.id,
            category=memory.category,
            key=memory.key,
            status="ok",
            details={"memory_public_id": memory.public_id},
        )
        return {
            "ok": True,
            "op": action,
            "thread_id": thread_id,
            "memory_ref": memory.public_id,
            "message": f"{action.capitalize()}d memory {memory.public_id}",
            "metadata": {
                "category": memory.category,
                "key": memory.key,
            },
        }

    @staticmethod
    def _failure(op: str, code: str, message: str, hint: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "op": op,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if hint:
            payload["error"]["hint"] = hint
        return payload


_extractor: Optional[MemoryExtractor] = None


def get_memory_extractor() -> MemoryExtractor:
    global _extractor
    if _extractor is None:
        _extractor = MemoryExtractor()
    return _extractor


def set_memory_extractor(extractor: MemoryExtractor) -> None:
    global _extractor
    _extractor = extractor
