"""
Thread persistence for Memory v1.5.

Thread records are chat-scoped and expose stable public IDs (t_...).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session as SQLAlchemySession

from app.db.base import Base
from app.db.session import get_db_session
from app.memory.error_codes import ERR_THREAD_NOT_FOUND, ERR_THREAD_REF_INVALID
from app.memory.models import Session, Thread


def _new_thread_public_id() -> str:
    return f"t_{uuid4().hex[:24]}"


class ThreadStore:
    """Store for creating and selecting chat threads."""

    def __init__(self, session: Optional[SQLAlchemySession] = None):
        self._session = session or get_db_session()
        self._ensure_phase21_schema()

    def _ensure_phase21_schema(self) -> None:
        """Best-effort schema backfill for legacy local/test SQLite files."""
        try:
            bind = self._session.get_bind()
            if bind is None:
                return
            inspector = sa_inspect(bind)
            tables = set(inspector.get_table_names())
            if "threads" not in tables or "session_messages" not in tables:
                Base.metadata.create_all(bind=bind)
                inspector = sa_inspect(bind)
                tables = set(inspector.get_table_names())
            if "threads" not in tables:
                return

            columns = {c["name"] for c in inspector.get_columns("threads")}
            if "public_id" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN public_id VARCHAR(26)"))
            if "chat_id" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN chat_id VARCHAR(255)"))
            if "title" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN title VARCHAR(255)"))
            if "is_active" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 0"))
            if "memory_enabled" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN memory_enabled BOOLEAN NOT NULL DEFAULT 1"))
            if "active_mode" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN active_mode VARCHAR(64) NOT NULL DEFAULT 'builder@1.5.0'"))
            if "active_soul" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN active_soul VARCHAR(64)"))
            if "mode_locked" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN mode_locked BOOLEAN NOT NULL DEFAULT 0"))
            if "last_active_at" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN last_active_at DATETIME"))
            if "topic_fingerprint" not in columns:
                self._session.execute(text("ALTER TABLE threads ADD COLUMN topic_fingerprint TEXT"))

            msg_columns = {c["name"] for c in inspector.get_columns("session_messages")}
            if "token_estimate" not in msg_columns:
                self._session.execute(text("ALTER TABLE session_messages ADD COLUMN token_estimate INTEGER"))

            # Create new v1.5 tables when missing.
            if "memory_items" not in tables or "memory_audit_events" not in tables:
                Base.metadata.create_all(bind=bind)

            # Backfill chat_id and public IDs for legacy rows.
            self._session.execute(
                text(
                    """
                    UPDATE threads
                    SET chat_id = (
                        SELECT sessions.chat_id
                        FROM sessions
                        WHERE sessions.id = threads.session_id
                    )
                    WHERE chat_id IS NULL
                    """
                )
            )
            self._session.execute(text("UPDATE threads SET active_mode = COALESCE(active_mode, 'builder@1.5.0')"))
            self._session.execute(text("UPDATE threads SET mode_locked = COALESCE(mode_locked, 0)"))
            missing_refs = self._session.execute(
                text("SELECT id FROM threads WHERE public_id IS NULL OR public_id = ''")
            ).fetchall()
            for row in missing_refs:
                self._session.execute(
                    text("UPDATE threads SET public_id = :ref WHERE id = :thread_id"),
                    {"ref": _new_thread_public_id(), "thread_id": row[0]},
                )

            self._session.commit()
        except Exception:
            self._session.rollback()

    def _get_or_create_session(self, chat_id: str) -> Session:
        session_row = (
            self._session.query(Session)
            .filter(Session.chat_id == str(chat_id))
            .order_by(Session.updated_at.desc(), Session.id.desc())
            .first()
        )
        if session_row:
            return session_row

        session_row = Session(chat_id=str(chat_id), mode="default", metadata_={})
        self._session.add(session_row)
        self._session.commit()
        self._session.refresh(session_row)
        return session_row

    def get_or_create_active_thread(self, chat_id: str) -> Thread:
        chat_id = str(chat_id)
        active = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.is_active.is_(True))
            .order_by(Thread.last_active_at.desc(), Thread.updated_at.desc(), Thread.id.desc())
            .first()
        )
        if active:
            return active
        return self.create_thread(chat_id=chat_id, title=None)

    def create_thread(self, chat_id: str, title: Optional[str] = None) -> Thread:
        chat_id = str(chat_id)
        now = datetime.utcnow()
        session_row = self._get_or_create_session(chat_id)

        # Ensure exactly one active thread per chat.
        (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.is_active.is_(True))
            .update({"is_active": False}, synchronize_session=False)
        )

        thread = Thread(
            session_id=session_row.id,
            public_id=_new_thread_public_id(),
            chat_id=chat_id,
            title=(title or "").strip() or "Untitled Thread",
            is_active=True,
            memory_enabled=True,
            active_mode="builder@1.5.0",
            active_soul=None,
            mode_locked=False,
            last_active_at=now,
            metadata_={},
        )
        self._session.add(thread)
        self._session.commit()
        self._session.refresh(thread)
        return thread

    def set_active_thread(self, chat_id: str, thread_public_id: str) -> Thread:
        chat_id = str(chat_id)
        thread_ref = (thread_public_id or "").strip()
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_ref)
            .first()
        )
        if not target:
            raise ValueError(ERR_THREAD_NOT_FOUND)

        (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.is_active.is_(True))
            .update({"is_active": False}, synchronize_session=False)
        )
        target.is_active = True
        target.last_active_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target

    def list_threads(self, chat_id: str) -> List[Thread]:
        chat_id = str(chat_id)
        return (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id)
            .order_by(Thread.last_active_at.desc(), Thread.updated_at.desc(), Thread.id.desc())
            .all()
        )

    def resolve_thread(self, chat_id: str, explicit_thread_id: Optional[str] = None) -> Thread:
        chat_id = str(chat_id)
        if explicit_thread_id:
            thread_ref = explicit_thread_id.strip()
            if not thread_ref.startswith("t_"):
                raise ValueError(ERR_THREAD_REF_INVALID)
            return self.set_active_thread(chat_id=chat_id, thread_public_id=thread_ref)
        return self.get_or_create_active_thread(chat_id)

    def update_thread_title(self, chat_id: str, thread_public_id: str, title: str) -> Optional[Thread]:
        chat_id = str(chat_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_public_id)
            .first()
        )
        if not target:
            return None
        target.title = (title or "").strip() or target.title
        target.updated_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target

    def set_memory_enabled(self, chat_id: str, thread_public_id: str, enabled: bool) -> Optional[Thread]:
        chat_id = str(chat_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_public_id)
            .first()
        )
        if not target:
            return None
        target.memory_enabled = bool(enabled)
        target.updated_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target

    def set_active_mode(self, chat_id: str, thread_public_id: str, mode_ref: str) -> Optional[Thread]:
        chat_id = str(chat_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_public_id)
            .first()
        )
        if not target:
            return None
        target.active_mode = (mode_ref or "").strip() or target.active_mode
        target.updated_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target

    def set_active_soul(self, chat_id: str, thread_public_id: str, soul_ref: Optional[str]) -> Optional[Thread]:
        chat_id = str(chat_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_public_id)
            .first()
        )
        if not target:
            return None
        value = (soul_ref or "").strip()
        target.active_soul = value or None
        target.updated_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target

    def set_mode_locked(self, chat_id: str, thread_public_id: str, locked: bool) -> Optional[Thread]:
        chat_id = str(chat_id)
        target = (
            self._session.query(Thread)
            .filter(Thread.chat_id == chat_id, Thread.public_id == thread_public_id)
            .first()
        )
        if not target:
            return None
        target.mode_locked = bool(locked)
        target.updated_at = datetime.utcnow()
        self._session.commit()
        self._session.refresh(target)
        return target
