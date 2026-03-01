"""
Deterministic thread context router for Memory v1.5.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.memory.thread_state import ThreadState


STOP_WORDS = {"the", "and", "is", "in", "it", "to", "of", "a", "for", "with", "that", "this"}


@dataclass
class RouteOutcome:
    thread_id: str
    reason: str
    created_new_thread: bool
    proposal: Optional[str] = None


class ContextRouter:
    """Route messages to deterministic per-chat threads."""

    def __init__(self, thread_state: Optional[ThreadState] = None) -> None:
        self.thread_state = thread_state or ThreadState()
        self._similarity_threshold = float(getattr(settings, "MEMORY_ROUTER_SIMILARITY_THRESHOLD", 0.35))
        self._propose_only = bool(getattr(settings, "MEMORY_THREAD_PROPOSE_ONLY", True))
        self._locks: Dict[str, asyncio.Lock] = {}

    def _chat_lock(self, chat_id: str) -> asyncio.Lock:
        chat_key = str(chat_id)
        lock = self._locks.get(chat_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_key] = lock
        return lock

    async def route_message(
        self,
        chat_id: str,
        message: str,
        explicit_thread_id: Optional[str] = None,
    ) -> RouteOutcome:
        chat_id = str(chat_id)
        text = (message or "").strip()
        async with self._chat_lock(chat_id):
            if explicit_thread_id:
                thread = self.thread_state.resolve_thread(chat_id, explicit_thread_id=explicit_thread_id)
                return RouteOutcome(thread_id=thread.public_id, reason="explicit_thread_use", created_new_thread=False)

            switch_title = self._extract_topic_switch_title(text)
            if switch_title is not None:
                thread_ref = self.thread_state.create_new_thread(chat_id, metadata={"title": switch_title})
                return RouteOutcome(thread_id=thread_ref, reason="explicit_topic_switch", created_new_thread=True)

            current_thread = self.thread_state.resolve_thread(chat_id)
            context = self.thread_state.get_thread_context(current_thread.public_id, max_messages=20)
            score = self.get_topic_similarity(context, text)
            if score < self._similarity_threshold and self._propose_only:
                return RouteOutcome(
                    thread_id=current_thread.public_id,
                    reason="similarity_low_propose_only",
                    created_new_thread=False,
                    proposal="This looks like a new topic. Use /thread new <title> to split it.",
                )

            return RouteOutcome(thread_id=current_thread.public_id, reason="active_thread", created_new_thread=False)

    def should_create_new_thread(
        self,
        current_thread_id: Optional[str],
        new_message: str,
        session_id: str,
    ) -> bool:
        del current_thread_id
        del session_id
        return self._extract_topic_switch_title(new_message or "") is not None

    def create_new_thread_if_needed(
        self,
        session_id: str,
        current_thread_id: Optional[str],
        new_message: str,
    ) -> Optional[str]:
        del current_thread_id
        title = self._extract_topic_switch_title(new_message or "")
        if title is None:
            return self.thread_state.get_current_thread(session_id)
        return self.thread_state.create_new_thread(session_id, metadata={"title": title})

    def get_thread_context(self, thread_id: str, max_messages: int = 20) -> Dict[str, Any]:
        return self.thread_state.get_thread_context(thread_id, max_messages=max_messages)

    def get_topic_similarity(self, thread_context: Dict[str, Any], new_message: str) -> float:
        context_keywords = self._extract_keywords(thread_context)
        message_keywords = self._extract_keywords_from_text(new_message)
        if not context_keywords or not message_keywords:
            return 0.0
        common = set(context_keywords) & set(message_keywords)
        return len(common) / max(len(context_keywords), len(message_keywords))

    def _extract_keywords(self, thread_context: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        title = thread_context.get("title")
        if isinstance(title, str) and title.strip():
            tokens.extend(self._extract_keywords_from_text(title))
        for message in thread_context.get("messages", []):
            tokens.extend(self._extract_keywords_from_text(message.get("content", "")))
        # keep uniqueness with stable order
        deduped: List[str] = []
        for token in tokens:
            if token not in deduped:
                deduped.append(token)
        return deduped

    def _extract_keywords_from_text(self, text: str) -> List[str]:
        words = re.findall(r"\b[a-zA-Z0-9_]+\b", (text or "").lower())
        return [word for word in words if len(word) > 2 and word not in STOP_WORDS]

    def _extract_topic_switch_title(self, text: str) -> Optional[str]:
        stripped = (text or "").strip()
        lower = stripped.lower()
        if lower.startswith("new topic:"):
            value = stripped[len("new topic:"):].strip()
            return value or "New Topic"
        if lower.startswith("topic:"):
            value = stripped[len("topic:"):].strip()
            return value or "New Topic"
        return None

    def set_similarity_threshold(self, threshold: float) -> None:
        self._similarity_threshold = max(0.0, min(1.0, float(threshold)))


_context_router: Optional[ContextRouter] = None


def get_context_router() -> ContextRouter:
    global _context_router
    if _context_router is None:
        _context_router = ContextRouter()
    return _context_router


def set_context_router(router: ContextRouter) -> None:
    global _context_router
    _context_router = router


__all__ = ["ContextRouter", "RouteOutcome", "get_context_router", "set_context_router"]
