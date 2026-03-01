"""
Thread state manager for Memory v1.5.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import func

from app.memory.message_store import MessageStore
from app.memory.models import Session, SessionMessage, Thread
from app.memory.thread_store import ThreadStore


class ThreadState:
    """Authoritative helper for chat thread selection."""

    def __init__(self, session=None):
        self.thread_store = ThreadStore(session=session)
        self.message_store = MessageStore(session=session)
        self._session = self.thread_store._session

    def _chat_scope(self, session_or_chat_id: Union[str, int]) -> str:
        return str(session_or_chat_id)

    def resolve_thread(self, chat_id: Union[str, int], explicit_thread_id: Optional[str] = None) -> Thread:
        return self.thread_store.resolve_thread(self._chat_scope(chat_id), explicit_thread_id)

    def get_current_thread(self, session_id: Union[str, int]) -> Optional[str]:
        chat_id = self._chat_scope(session_id)
        thread = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.is_active.is_(True))
            .order_by(Thread.last_active_at.desc(), Thread.id.desc())
            .first()
        )
        return thread.public_id if thread else None

    def get_current_thread_row(self, session_id: Union[str, int]) -> Optional[Thread]:
        chat_id = self._chat_scope(session_id)
        return (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.is_active.is_(True))
            .order_by(Thread.last_active_at.desc(), Thread.id.desc())
            .first()
        )

    def set_current_thread(self, session_id: Union[str, int], thread_id: str) -> bool:
        try:
            self.thread_store.set_active_thread(self._chat_scope(session_id), thread_id)
            return True
        except ValueError:
            return False

    def create_new_thread(self, session_id: Union[str, int], metadata: Optional[Dict] = None) -> str:
        title = None
        if metadata:
            title = metadata.get("title")
        thread = self.thread_store.create_thread(self._chat_scope(session_id), title=title)
        return thread.public_id

    def get_thread_history(self, session_id: Union[str, int]) -> List[Dict]:
        chat_id = self._chat_scope(session_id)
        threads = self.thread_store.list_threads(chat_id)
        history: List[Dict[str, Any]] = []
        for thread in threads:
            count = (
                self._session.query(func.count(SessionMessage.id))
                .filter(SessionMessage.thread_id == thread.id)
                .scalar()
            ) or 0
            history.append(
                {
                    "thread_id": thread.public_id,
                    "title": thread.title,
                    "created_at": thread.created_at,
                    "last_active_at": thread.last_active_at,
                    "is_active": thread.is_active,
                    "message_count": int(count),
                    "memory_enabled": thread.memory_enabled,
                    "active_mode": thread.active_mode,
                    "active_soul": thread.active_soul,
                    "mode_locked": thread.mode_locked,
                }
            )
        return history

    def get_all_sessions(self) -> List[Dict]:
        sessions = self._session.query(Session).all()
        return [
            {
                "session_id": session.id,
                "chat_id": session.chat_id,
                "mode": session.mode,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "current_thread_id": self.get_current_thread(session.chat_id),
            }
            for session in sessions
        ]

    def get_session_stats(self, session_id: Union[str, int]) -> Dict:
        chat_id = self._chat_scope(session_id)
        threads = self.thread_store.list_threads(chat_id)
        message_count = (
            self._session.query(func.count(SessionMessage.id))
            .join(Thread, Thread.id == SessionMessage.thread_id)
            .filter(Thread.chat_id == chat_id)
            .scalar()
        ) or 0
        return {
            "chat_id": chat_id,
            "thread_count": len(threads),
            "message_count": int(message_count),
            "current_thread_id": self.get_current_thread(chat_id),
        }

    def switch_thread(self, session_id: Union[str, int], thread_id: str) -> bool:
        return self.set_current_thread(session_id, thread_id)

    def close_thread(self, session_id: Union[str, int], thread_id: str) -> bool:
        chat_id = self._chat_scope(session_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_id)
            .first()
        )
        if not target:
            return False
        target.is_active = False
        target.updated_at = datetime.utcnow()
        self._session.commit()
        return True

    def get_thread_context(self, thread_id: Union[str, int], max_messages: int = 20) -> Dict:
        if isinstance(thread_id, int):
            thread = self._session.query(Thread).filter(Thread.id == thread_id).first()
        else:
            thread = self._session.query(Thread).filter(Thread.public_id == str(thread_id)).first()
        if not thread:
            return {}

        messages = self.message_store.get_recent_messages(thread.id, max_messages)
        return {
            "thread_id": thread.public_id,
            "thread_pk": thread.id,
            "chat_id": thread.chat_id,
            "title": thread.title,
            "created_at": thread.created_at,
            "last_active_at": thread.last_active_at,
            "memory_enabled": thread.memory_enabled,
            "active_mode": thread.active_mode,
            "active_soul": thread.active_soul,
            "mode_locked": thread.mode_locked,
            "messages": [
                {"role": message.role, "content": message.content, "created_at": message.created_at}
                for message in messages
            ],
            "message_count": len(messages),
        }

    def set_active_mode(self, session_id: Union[str, int], mode_ref: str) -> bool:
        chat_id = self._chat_scope(session_id)
        current = self.get_current_thread_row(chat_id)
        if not current:
            return False
        updated = self.thread_store.set_active_mode(chat_id, current.public_id, mode_ref)
        return updated is not None

    def set_active_soul(self, session_id: Union[str, int], soul_ref: Optional[str]) -> bool:
        chat_id = self._chat_scope(session_id)
        current = self.get_current_thread_row(chat_id)
        if not current:
            return False
        updated = self.thread_store.set_active_soul(chat_id, current.public_id, soul_ref)
        return updated is not None

    def set_mode_locked(self, session_id: Union[str, int], locked: bool) -> bool:
        chat_id = self._chat_scope(session_id)
        current = self.get_current_thread_row(chat_id)
        if not current:
            return False
        updated = self.thread_store.set_mode_locked(chat_id, current.public_id, locked)
        return updated is not None

    def is_thread_active(self, session_id: Union[str, int], thread_id: str) -> bool:
        return self.get_current_thread(session_id) == thread_id

    def get_inactive_threads(self, session_id: Union[str, int], inactivity_threshold: int = 30) -> List[str]:
        chat_id = self._chat_scope(session_id)
        threshold_time = datetime.utcnow() - timedelta(minutes=inactivity_threshold)
        rows = (
            self._session.query(Thread.public_id)
            .filter(
                Thread.chat_id == chat_id,
                Thread.last_active_at.isnot(None),
                Thread.last_active_at < threshold_time,
            )
            .all()
        )
        return [row[0] for row in rows]

    def cleanup_inactive_threads(self, session_id: Union[str, int], inactivity_threshold: int = 30) -> int:
        inactive = self.get_inactive_threads(session_id, inactivity_threshold)
        for thread_ref in inactive:
            self.close_thread(session_id, thread_ref)
        return len(inactive)


_thread_state: Optional[ThreadState] = None


def get_thread_state() -> ThreadState:
    global _thread_state
    if _thread_state is None:
        _thread_state = ThreadState()
    return _thread_state


def set_thread_state(state: ThreadState) -> None:
    global _thread_state
    _thread_state = state
