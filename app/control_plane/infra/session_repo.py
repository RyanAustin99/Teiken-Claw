"""SQLite repository for chat sessions/messages."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from app.control_plane.domain.models import OnboardingStatus, SessionMessageRecord, SessionRecord


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class SessionRepository:
    """Persistence layer for agent chat sessions."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    title TEXT,
                    onboarding_status TEXT NOT NULL DEFAULT 'pending',
                    onboarding_step INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tool_name TEXT,
                    tool_ok INTEGER,
                    tool_elapsed_ms INTEGER
                )
                """
            )
            self._ensure_columns(conn)
            conn.commit()

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(agent_sessions)").fetchall()}
        required = {
            "onboarding_status": "TEXT NOT NULL DEFAULT 'pending'",
            "onboarding_step": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in required.items():
            if column in existing:
                continue
            conn.execute(f"ALTER TABLE agent_sessions ADD COLUMN {column} {definition}")

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            title=row["title"],
            onboarding_status=OnboardingStatus(row["onboarding_status"]),
            onboarding_step=int(row["onboarding_step"] or 0),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> SessionMessageRecord:
        return SessionMessageRecord(
            id=int(row["id"]),
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            tool_name=row["tool_name"],
            tool_ok=bool(row["tool_ok"]) if row["tool_ok"] is not None else None,
            tool_elapsed_ms=row["tool_elapsed_ms"],
        )

    def new_session(self, agent_id: str, title: Optional[str] = None) -> SessionRecord:
        session_id = str(uuid4())
        now = _utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    id, agent_id, title, onboarding_status, onboarding_step, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    agent_id,
                    title,
                    OnboardingStatus.PENDING.value,
                    0,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row_to_session(row)

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def list_sessions(self, agent_id: str, limit: int = 50) -> List[SessionRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_sessions WHERE agent_id = ? ORDER BY updated_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def rename_session(self, session_id: str, title: str) -> Optional[SessionRecord]:
        now = _utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE agent_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, session_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def update_onboarding(self, session_id: str, status: OnboardingStatus, step: int) -> Optional[SessionRecord]:
        now = _utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE agent_sessions
                SET onboarding_status = ?, onboarding_step = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, step, now, session_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def delete_session(self, session_id: str) -> bool:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM agent_messages WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM agent_sessions WHERE id = ?", (session_id,))
            conn.commit()
        return cursor.rowcount > 0

    def delete_sessions_for_agent(self, agent_id: str) -> int:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                DELETE FROM agent_messages
                WHERE session_id IN (
                    SELECT id FROM agent_sessions WHERE agent_id = ?
                )
                """,
                (agent_id,),
            )
            cursor = conn.execute("DELETE FROM agent_sessions WHERE agent_id = ?", (agent_id,))
            conn.commit()
        return int(cursor.rowcount)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_ok: Optional[bool] = None,
        tool_elapsed_ms: Optional[int] = None,
    ) -> SessionMessageRecord:
        now = _utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO agent_messages (session_id, role, content, created_at, tool_name, tool_ok, tool_elapsed_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    now,
                    tool_name,
                    (1 if tool_ok else 0) if tool_ok is not None else None,
                    tool_elapsed_ms,
                ),
            )
            conn.execute("UPDATE agent_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            conn.commit()
            row = conn.execute("SELECT * FROM agent_messages WHERE id = last_insert_rowid()").fetchone()
        return self._row_to_message(row)

    def list_messages(self, session_id: str) -> List[SessionMessageRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def list_tool_messages(self, session_id: str, limit: int = 20) -> List[SessionMessageRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_messages
                WHERE session_id = ? AND tool_name IS NOT NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

