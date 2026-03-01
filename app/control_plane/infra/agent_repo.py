"""SQLite repository for control-plane agent registry."""

from __future__ import annotations

import sqlite3
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from app.control_plane.domain.models import AgentOnboardingState, AgentRecord, RunnerType, RuntimeStatus


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class AgentRepository:
    """Persistence layer for agents."""

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
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    model TEXT,
                    tool_profile TEXT NOT NULL DEFAULT 'safe',
                    workspace_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'stopped',
                    last_error TEXT,
                    last_seen_at TEXT,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    runner_type TEXT,
                    auto_restart INTEGER NOT NULL DEFAULT 1,
                    max_queue_depth INTEGER,
                    tool_profile_version TEXT,
                    agent_profile_user_name TEXT,
                    agent_profile_agent_name TEXT,
                    agent_profile_purpose TEXT,
                    onboarding_complete INTEGER NOT NULL DEFAULT 0,
                    onboarding_updated_at TEXT,
                    prompt_template_version TEXT NOT NULL DEFAULT '1.0.0',
                    is_fresh INTEGER NOT NULL DEFAULT 1,
                    onboarding_state TEXT NOT NULL DEFAULT 'NEW',
                    profile_json TEXT,
                    boot_directives TEXT,
                    degraded_reason TEXT,
                    default_soul TEXT NOT NULL DEFAULT 'teiken_claw_agent@1.5.0',
                    default_mode TEXT NOT NULL DEFAULT 'builder@1.5.0'
                )
                """
            )
            self._ensure_columns(conn)
            conn.commit()

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        required: Dict[str, str] = {
            "agent_profile_user_name": "TEXT",
            "agent_profile_agent_name": "TEXT",
            "agent_profile_purpose": "TEXT",
            "onboarding_complete": "INTEGER NOT NULL DEFAULT 0",
            "onboarding_updated_at": "TEXT",
            "prompt_template_version": "TEXT NOT NULL DEFAULT '1.0.0'",
            "is_fresh": "INTEGER NOT NULL DEFAULT 1",
            "onboarding_state": "TEXT NOT NULL DEFAULT 'NEW'",
            "profile_json": "TEXT",
            "boot_directives": "TEXT",
            "degraded_reason": "TEXT",
            "default_soul": "TEXT NOT NULL DEFAULT 'teiken_claw_agent@1.5.0'",
            "default_mode": "TEXT NOT NULL DEFAULT 'builder@1.5.0'",
        }
        for column, definition in required.items():
            if column in existing:
                continue
            conn.execute(f"ALTER TABLE agents ADD COLUMN {column} {definition}")

    @staticmethod
    def _decode_profile_json(raw: Optional[str]) -> Optional[dict]:
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> AgentRecord:
        return AgentRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            model=row["model"],
            tool_profile=row["tool_profile"],
            workspace_path=row["workspace_path"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            status=RuntimeStatus(row["status"]),
            last_error=row["last_error"],
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
            is_default=bool(row["is_default"]),
            runner_type=RunnerType(row["runner_type"]) if row["runner_type"] else None,
            auto_restart=bool(row["auto_restart"]),
            max_queue_depth=row["max_queue_depth"],
            tool_profile_version=row["tool_profile_version"],
            agent_profile_user_name=row["agent_profile_user_name"],
            agent_profile_agent_name=row["agent_profile_agent_name"],
            agent_profile_purpose=row["agent_profile_purpose"],
            onboarding_complete=bool(row["onboarding_complete"]),
            onboarding_updated_at=datetime.fromisoformat(row["onboarding_updated_at"])
            if row["onboarding_updated_at"]
            else None,
            prompt_template_version=row["prompt_template_version"] or "1.0.0",
            is_fresh=bool(row["is_fresh"]) if "is_fresh" in row.keys() else True,
            onboarding_state=AgentOnboardingState(row["onboarding_state"] or AgentOnboardingState.NEW.value)
            if "onboarding_state" in row.keys()
            else AgentOnboardingState.NEW,
            profile_json=AgentRepository._decode_profile_json(row["profile_json"]) if "profile_json" in row.keys() else None,
            boot_directives=row["boot_directives"] if "boot_directives" in row.keys() else None,
            degraded_reason=row["degraded_reason"] if "degraded_reason" in row.keys() else None,
            default_soul=row["default_soul"] if "default_soul" in row.keys() and row["default_soul"] else "teiken_claw_agent@1.5.0",
            default_mode=row["default_mode"] if "default_mode" in row.keys() and row["default_mode"] else "builder@1.5.0",
        )

    def create(
        self,
        name: str,
        workspace_path: str,
        description: Optional[str] = None,
        model: Optional[str] = None,
        tool_profile: str = "safe",
        runner_type: Optional[RunnerType] = None,
        auto_restart: bool = True,
        max_queue_depth: Optional[int] = None,
        tool_profile_version: Optional[str] = None,
        prompt_template_version: str = "1.0.0",
        default_soul: str = "teiken_claw_agent@1.5.0",
        default_mode: str = "builder@1.5.0",
    ) -> AgentRecord:
        agent_id = str(uuid4())
        now = _utcnow()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    id, name, description, model, tool_profile, workspace_path,
                    created_at, updated_at, status, last_error, last_seen_at,
                    is_default, runner_type, auto_restart, max_queue_depth, tool_profile_version,
                    agent_profile_user_name, agent_profile_agent_name, agent_profile_purpose,
                    onboarding_complete, onboarding_updated_at, prompt_template_version,
                    is_fresh, onboarding_state, profile_json, boot_directives, degraded_reason
                    , default_soul, default_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    name,
                    description,
                    model,
                    tool_profile,
                    workspace_path,
                    now,
                    now,
                    RuntimeStatus.STOPPED.value,
                    None,
                    None,
                    0,
                    runner_type.value if runner_type else None,
                    1 if auto_restart else 0,
                    max_queue_depth,
                    tool_profile_version,
                    None,
                    None,
                    None,
                    0,
                    None,
                    prompt_template_version,
                    1,
                    AgentOnboardingState.NEW.value,
                    None,
                    None,
                    None,
                    default_soul,
                    default_mode,
                ),
            )
            conn.commit()
        return self.get(agent_id)

    def get(self, agent_id: str) -> Optional[AgentRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if not row:
                return None
            return self._row_to_agent(row)

    def get_by_name(self, name: str) -> Optional[AgentRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
            if not row:
                return None
            return self._row_to_agent(row)

    def list(self) -> List[AgentRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY created_at ASC").fetchall()
            return [self._row_to_agent(row) for row in rows]

    def update(self, agent_id: str, patch: Dict[str, object]) -> Optional[AgentRecord]:
        if not patch:
            return self.get(agent_id)

        allowed = {
            "name",
            "description",
            "model",
            "tool_profile",
            "workspace_path",
            "status",
            "last_error",
            "last_seen_at",
            "is_default",
            "runner_type",
            "auto_restart",
            "max_queue_depth",
            "tool_profile_version",
            "agent_profile_user_name",
            "agent_profile_agent_name",
            "agent_profile_purpose",
            "onboarding_complete",
            "onboarding_updated_at",
            "prompt_template_version",
            "is_fresh",
            "onboarding_state",
            "profile_json",
            "boot_directives",
            "degraded_reason",
            "default_soul",
            "default_mode",
        }
        keys = [key for key in patch.keys() if key in allowed]
        if not keys:
            return self.get(agent_id)

        assignments = ", ".join(f"{key} = ?" for key in keys) + ", updated_at = ?"
        values: List[object] = []
        for key in keys:
            value = patch[key]
            if isinstance(value, RuntimeStatus):
                value = value.value
            if isinstance(value, RunnerType):
                value = value.value
            if isinstance(value, AgentOnboardingState):
                value = value.value
            if isinstance(value, bool):
                value = 1 if value else 0
            if isinstance(value, datetime):
                value = value.isoformat()
            if key == "profile_json":
                if value is None:
                    value = None
                elif isinstance(value, str):
                    # keep existing string payload as-is if already serialized
                    value = value
                else:
                    value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        values.append(_utcnow())
        values.append(agent_id)

        with closing(self._connect()) as conn:
            conn.execute(f"UPDATE agents SET {assignments} WHERE id = ?", values)
            conn.commit()
        return self.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        with closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_default(self, agent_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE agents SET is_default = 0")
            conn.execute("UPDATE agents SET is_default = 1, updated_at = ? WHERE id = ?", (_utcnow(), agent_id))
            conn.commit()

    def ping(self) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT 1").fetchone()
            return bool(row and row[0] == 1)

