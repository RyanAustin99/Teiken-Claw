"""Phase 22: Souls and Modes deterministic persistence

Revision ID: 005_phase22_souls_modes
Revises: 004_phase21_memory_v15
Create Date: 2026-03-01 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_phase22_souls_modes"
down_revision: Union[str, None] = "004_phase21_memory_v15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "threads" in tables:
        columns = _column_names("threads")
        if "active_mode" not in columns:
            op.add_column(
                "threads",
                sa.Column("active_mode", sa.String(length=64), nullable=False, server_default="builder@1.5.0"),
            )
        if "active_soul" not in columns:
            op.add_column("threads", sa.Column("active_soul", sa.String(length=64), nullable=True))
        if "mode_locked" not in columns:
            op.add_column(
                "threads",
                sa.Column("mode_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

        bind.execute(sa.text("UPDATE threads SET active_mode = COALESCE(active_mode, 'builder@1.5.0')"))
        bind.execute(sa.text("UPDATE threads SET mode_locked = COALESCE(mode_locked, 0)"))

        indexes = _index_names("threads")
        if "ix_threads_active_mode" not in indexes:
            op.create_index("ix_threads_active_mode", "threads", ["active_mode"])
        if "ix_threads_active_soul" not in indexes:
            op.create_index("ix_threads_active_soul", "threads", ["active_soul"])
        if "ix_threads_mode_locked" not in indexes:
            op.create_index("ix_threads_mode_locked", "threads", ["mode_locked"])

    if "persona_audit_events" not in tables:
        op.create_table(
            "persona_audit_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("scope_type", sa.String(length=16), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=True),
            sa.Column("session_id", sa.String(length=255), nullable=True),
            sa.Column("agent_id", sa.String(length=255), nullable=True),
            sa.Column("op", sa.String(length=32), nullable=False),
            sa.Column("previous_value", sa.String(length=128), nullable=True),
            sa.Column("new_value", sa.String(length=128), nullable=True),
            sa.Column("prompt_fingerprint", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("reason_code", sa.String(length=128), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.CheckConstraint("scope_type IN ('thread', 'session', 'agent')", name="ck_persona_audit_scope"),
            sa.CheckConstraint(
                "op IN ('soul_set', 'mode_set', 'mode_lock', 'mode_unlock')",
                name="ck_persona_audit_op",
            ),
            sa.CheckConstraint("status IN ('ok', 'error')", name="ck_persona_audit_status"),
            sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "persona_audit_events" in _table_names():
        indexes = _index_names("persona_audit_events")
        if "ix_persona_audit_events_ts" not in indexes:
            op.create_index("ix_persona_audit_events_ts", "persona_audit_events", ["ts"])
        if "ix_persona_audit_events_scope_type" not in indexes:
            op.create_index("ix_persona_audit_events_scope_type", "persona_audit_events", ["scope_type"])
        if "ix_persona_audit_events_thread_id" not in indexes:
            op.create_index("ix_persona_audit_events_thread_id", "persona_audit_events", ["thread_id"])
        if "ix_persona_audit_events_session_id" not in indexes:
            op.create_index("ix_persona_audit_events_session_id", "persona_audit_events", ["session_id"])
        if "ix_persona_audit_events_agent_id" not in indexes:
            op.create_index("ix_persona_audit_events_agent_id", "persona_audit_events", ["agent_id"])
        if "ix_persona_audit_events_op" not in indexes:
            op.create_index("ix_persona_audit_events_op", "persona_audit_events", ["op"])
        if "ix_persona_audit_events_status" not in indexes:
            op.create_index("ix_persona_audit_events_status", "persona_audit_events", ["status"])
        if "ix_persona_audit_events_reason_code" not in indexes:
            op.create_index("ix_persona_audit_events_reason_code", "persona_audit_events", ["reason_code"])
        if "ix_persona_audit_scope_ts" not in indexes:
            op.create_index("ix_persona_audit_scope_ts", "persona_audit_events", ["scope_type", "ts"])


def downgrade() -> None:
    tables = _table_names()

    if "persona_audit_events" in tables:
        indexes = _index_names("persona_audit_events")
        for index_name in (
            "ix_persona_audit_scope_ts",
            "ix_persona_audit_events_reason_code",
            "ix_persona_audit_events_status",
            "ix_persona_audit_events_op",
            "ix_persona_audit_events_agent_id",
            "ix_persona_audit_events_session_id",
            "ix_persona_audit_events_thread_id",
            "ix_persona_audit_events_scope_type",
            "ix_persona_audit_events_ts",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="persona_audit_events")
        op.drop_table("persona_audit_events")

    if "threads" in tables:
        indexes = _index_names("threads")
        for index_name in (
            "ix_threads_mode_locked",
            "ix_threads_active_soul",
            "ix_threads_active_mode",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="threads")

        columns = _column_names("threads")
        for column_name in ("mode_locked", "active_soul", "active_mode"):
            if column_name in columns:
                op.drop_column("threads", column_name)
