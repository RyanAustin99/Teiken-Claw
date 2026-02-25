"""
Thread state management for Teiken Claw.

This module provides thread tracking and session management functionality,
including:
- Current thread tracking per session
- Thread history management
- Session statistics
- Thread creation and switching
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.memory.models import MemoryRecord, Session, SessionMessage, Thread
from app.memory.store import MemoryStore


class ThreadState:
    """Thread state management for tracking conversation threads."""

    def __init__(self, session=None, store: Optional[MemoryStore] = None):
        self.store = store or MemoryStore(session=session)
        self._thread_cache: Dict[int, int] = {}
        self._session_cache: Dict[int, Dict[str, Any]] = {}

    # =========================================================================
    # Session Management
    # =========================================================================

    def get_current_thread(self, session_id: int) -> Optional[int]:
        """Get the current thread ID for a session."""
        if session_id in self._thread_cache:
            return self._thread_cache[session_id]

        session = self.store.get_session(session_id)
        if session and session.metadata_:
            current_thread_id = session.metadata_.get("current_thread_id")
            if current_thread_id:
                self._thread_cache[session_id] = current_thread_id
                return current_thread_id
        return None

    def set_current_thread(self, session_id: int, thread_id: int) -> bool:
        """Set the current thread for a session."""
        session = self.store.get_session(session_id)
        if not session:
            return False

        metadata = dict(session.metadata_ or {})
        metadata["current_thread_id"] = thread_id
        self.store.update_session(session_id, {"metadata_": metadata})
        self._thread_cache[session_id] = thread_id
        return True

    def create_new_thread(self, session_id: int, metadata: Optional[Dict] = None) -> int:
        """Create a new thread and set it as current."""
        thread = self.store.create_thread(session_id, metadata)
        self.set_current_thread(session_id, thread.id)
        return thread.id

    def get_thread_history(self, session_id: int) -> List[Dict]:
        """Get thread history for a session."""
        threads = (
            self.store._session.query(Thread)
            .filter(Thread.session_id == session_id)
            .order_by(Thread.created_at.desc())
            .all()
        )

        history: List[Dict[str, Any]] = []
        for thread in threads:
            message_count = (
                self.store._session.query(SessionMessage)
                .filter(SessionMessage.thread_id == thread.id)
                .count()
            )
            history.append(
                {
                    "thread_id": thread.id,
                    "created_at": thread.created_at,
                    "summary": thread.summary,
                    "message_count": message_count,
                }
            )
        return history

    def get_all_sessions(self) -> List[Dict]:
        """Get all sessions."""
        sessions = self.store._session.query(Session).all()
        return [
            {
                "session_id": session.id,
                "chat_id": session.chat_id,
                "mode": session.mode,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "current_thread_id": self.get_current_thread(session.id),
            }
            for session in sessions
        ]

    def get_session_stats(self, session_id: int) -> Dict:
        """Get statistics for a session."""
        session = self.store.get_session(session_id)
        if not session:
            return {}

        thread_count = (
            self.store._session.query(Thread)
            .filter(Thread.session_id == session_id)
            .count()
        )
        message_count = (
            self.store._session.query(SessionMessage)
            .join(Thread)
            .filter(Thread.session_id == session_id)
            .count()
        )
        memory_count = (
            self.store._session.query(MemoryRecord)
            .filter(MemoryRecord.scope == "session")
            .count()
        )

        return {
            "session_id": session.id,
            "chat_id": session.chat_id,
            "mode": session.mode,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "thread_count": thread_count,
            "message_count": message_count,
            "memory_count": memory_count,
            "current_thread_id": self.get_current_thread(session.id),
        }

    # =========================================================================
    # Thread Management
    # =========================================================================

    def switch_thread(self, session_id: int, thread_id: int) -> bool:
        """Switch to an existing thread."""
        thread = self.store.get_thread(thread_id)
        if thread and thread.session_id == session_id:
            return self.set_current_thread(session_id, thread_id)
        return False

    def close_thread(self, session_id: int, thread_id: int) -> bool:
        """Close a thread (mark as completed)."""
        thread = self.store.get_thread(thread_id)
        if thread and thread.session_id == session_id:
            self.store.update_thread(thread_id, {"summary": "Thread completed"})
            return True
        return False

    def get_thread_context(self, thread_id: int, max_messages: int = 20) -> Dict:
        """Get context for a thread."""
        thread = self.store.get_thread(thread_id)
        if not thread:
            return {}

        messages = self.store.get_messages_by_thread(thread_id, limit=max_messages)
        formatted_messages = [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in messages
        ]

        return {
            "thread_id": thread.id,
            "session_id": thread.session_id,
            "created_at": thread.created_at,
            "summary": thread.summary,
            "messages": formatted_messages,
            "message_count": len(messages),
        }

    # =========================================================================
    # Cache Management
    # =========================================================================

    def clear_cache(self) -> None:
        self._thread_cache.clear()
        self._session_cache.clear()

    def invalidate_session_cache(self, session_id: int) -> None:
        self._thread_cache.pop(session_id, None)
        self._session_cache.pop(session_id, None)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_thread_active(self, session_id: int, thread_id: int) -> bool:
        return self.get_current_thread(session_id) == thread_id

    def get_inactive_threads(self, session_id: int, inactivity_threshold: int = 30) -> List[int]:
        """Get threads that have been inactive for a given threshold."""
        threshold_time = datetime.now() - timedelta(minutes=inactivity_threshold)
        inactive_threads: List[int] = []

        threads = self.store._session.query(Thread).filter(Thread.session_id == session_id).all()
        for thread in threads:
            recent_message = (
                self.store._session.query(SessionMessage)
                .filter(SessionMessage.thread_id == thread.id)
                .filter(SessionMessage.created_at > threshold_time)
                .first()
            )
            if not recent_message:
                inactive_threads.append(thread.id)

        return inactive_threads

    def cleanup_inactive_threads(self, session_id: int, inactivity_threshold: int = 30) -> int:
        """Cleanup inactive threads."""
        inactive_threads = self.get_inactive_threads(session_id, inactivity_threshold)
        for thread_id in inactive_threads:
            self.close_thread(session_id, thread_id)
        return len(inactive_threads)


_thread_state: Optional[ThreadState] = None


def get_thread_state() -> ThreadState:
    """Get or create the global thread state instance."""
    global _thread_state
    if _thread_state is None:
        _thread_state = ThreadState()
    return _thread_state


def set_thread_state(state: ThreadState) -> None:
    """Set the global thread state instance (for testing or DI)."""
    global _thread_state
    _thread_state = state
