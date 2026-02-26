"""Control-plane audit persistence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class ControlPlaneAuditRepository:
    """Simple sqlite-backed audit event storage for control-plane actions."""

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
                CREATE TABLE IF NOT EXISTS control_plane_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    details_json TEXT
                )
                """
            )
            conn.commit()

    def log(self, action: str, target: Optional[str], details: Optional[Dict[str, Any]], actor: str = "system") -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO control_plane_audit_events (created_at, actor, action, target, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_utcnow(), actor, action, target, json.dumps(details or {})),
            )
            conn.commit()

    def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, created_at, actor, action, target, details_json FROM control_plane_audit_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "actor": row["actor"],
                    "action": row["action"],
                    "target": row["target"],
                    "details": json.loads(row["details_json"] or "{}"),
                }
            )
        return result

