"""Phase 21: deterministic thread-safe memory v1.5

Revision ID: 004_phase21_memory_v15
Revises: 003_phase20_file_op_audits
Create Date: 2026-02-28 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_phase21_memory_v15"
down_revision: Union[str, None] = "003_phase20_file_op_audits"
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


def _next_thread_public_id() -> str:
    return f"t_{uuid4().hex[:24]}"


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "threads" in tables:
        columns = _column_names("threads")
        if "public_id" not in columns:
            op.add_column("threads", sa.Column("public_id", sa.String(length=26), nullable=True))
        if "chat_id" not in columns:
            op.add_column("threads", sa.Column("chat_id", sa.String(length=255), nullable=True))
        if "title" not in columns:
            op.add_column("threads", sa.Column("title", sa.String(length=255), nullable=True))
        if "is_active" not in columns:
            op.add_column(
                "threads",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )
        if "memory_enabled" not in columns:
            op.add_column(
                "threads",
                sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )
        if "last_active_at" not in columns:
            op.add_column("threads", sa.Column("last_active_at", sa.DateTime(), nullable=True))
        if "topic_fingerprint" not in columns:
            op.add_column("threads", sa.Column("topic_fingerprint", sa.Text(), nullable=True))

        # Backfill chat_id and last_active_at from existing relationships.
        bind.execute(
            sa.text(
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
        bind.execute(sa.text("UPDATE threads SET last_active_at = COALESCE(last_active_at, updated_at, created_at)"))

        # Backfill public IDs deterministically.
        rows = bind.execute(sa.text("SELECT id FROM threads WHERE public_id IS NULL OR public_id = ''")).fetchall()
        for row in rows:
            bind.execute(
                sa.text("UPDATE threads SET public_id = :public_id WHERE id = :thread_id"),
                {"public_id": _next_thread_public_id(), "thread_id": row[0]},
            )

        # Set one active thread per chat when absent.
        chat_rows = bind.execute(
            sa.text("SELECT DISTINCT chat_id FROM threads WHERE chat_id IS NOT NULL AND chat_id <> ''")
        ).fetchall()
        for chat_row in chat_rows:
            chat_id = chat_row[0]
            active_count = bind.execute(
                sa.text("SELECT COUNT(1) FROM threads WHERE chat_id = :chat_id AND is_active = 1"),
                {"chat_id": chat_id},
            ).scalar() or 0
            if active_count == 0:
                winner = bind.execute(
                    sa.text(
                        """
                        SELECT id
                        FROM threads
                        WHERE chat_id = :chat_id
                        ORDER BY COALESCE(last_active_at, updated_at, created_at) DESC, id DESC
                        LIMIT 1
                        """
                    ),
                    {"chat_id": chat_id},
                ).scalar()
                if winner is not None:
                    bind.execute(sa.text("UPDATE threads SET is_active = 0 WHERE chat_id = :chat_id"), {"chat_id": chat_id})
                    bind.execute(sa.text("UPDATE threads SET is_active = 1 WHERE id = :thread_id"), {"thread_id": winner})

        indexes = _index_names("threads")
        if "ix_threads_public_id" not in indexes:
            op.create_index("ix_threads_public_id", "threads", ["public_id"], unique=True)
        if "ix_threads_chat_id" not in indexes:
            op.create_index("ix_threads_chat_id", "threads", ["chat_id"])
        if "ix_threads_is_active" not in indexes:
            op.create_index("ix_threads_is_active", "threads", ["is_active"])
        if "ix_threads_last_active_at" not in indexes:
            op.create_index("ix_threads_last_active_at", "threads", ["last_active_at"])
        if "ix_threads_chat_active_unique" not in indexes:
            op.create_index(
                "ix_threads_chat_active_unique",
                "threads",
                ["chat_id"],
                unique=True,
                sqlite_where=sa.text("is_active = 1 AND chat_id IS NOT NULL"),
            )

    if "session_messages" in tables:
        columns = _column_names("session_messages")
        if "token_estimate" not in columns:
            op.add_column("session_messages", sa.Column("token_estimate", sa.Integer(), nullable=True))

    if "memory_items" not in tables:
        op.create_table(
            "memory_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("public_id", sa.String(length=26), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("source_message_id", sa.Integer(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_item_confidence_range"),
            sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_message_id"], ["session_messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = _index_names("memory_items")
    if "ix_memory_items_public_id" not in indexes:
        op.create_index("ix_memory_items_public_id", "memory_items", ["public_id"], unique=True)
    if "ix_memory_items_thread_id" not in indexes:
        op.create_index("ix_memory_items_thread_id", "memory_items", ["thread_id"])
    if "ix_memory_items_category" not in indexes:
        op.create_index("ix_memory_items_category", "memory_items", ["category"])
    if "ix_memory_items_key" not in indexes:
        op.create_index("ix_memory_items_key", "memory_items", ["key"])
    if "ix_memory_items_source_message_id" not in indexes:
        op.create_index("ix_memory_items_source_message_id", "memory_items", ["source_message_id"])
    if "ix_memory_items_is_deleted" not in indexes:
        op.create_index("ix_memory_items_is_deleted", "memory_items", ["is_deleted"])
    if "ix_memory_items_thread_category_key" not in indexes:
        op.create_index("ix_memory_items_thread_category_key", "memory_items", ["thread_id", "category", "key"])
    if "ix_memory_items_active_unique" not in indexes:
        op.create_index(
            "ix_memory_items_active_unique",
            "memory_items",
            ["thread_id", "category", "key"],
            unique=True,
            sqlite_where=sa.text("is_deleted = 0"),
        )

    if "memory_audit_events" not in tables:
        op.create_table(
            "memory_audit_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=True),
            sa.Column("agent_id", sa.String(length=255), nullable=True),
            sa.Column("source_message_id", sa.Integer(), nullable=True),
            sa.Column("op", sa.String(length=32), nullable=False),
            sa.Column("memory_id", sa.Integer(), nullable=True),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("key", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("reason_code", sa.String(length=128), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.CheckConstraint(
                "op IN ('add', 'update', 'delete', 'pause', 'resume', 'blocked')",
                name="ck_memory_audit_event_op",
            ),
            sa.CheckConstraint("status IN ('ok', 'blocked', 'error')", name="ck_memory_audit_event_status"),
            sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_message_id"], ["session_messages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["memory_id"], ["memory_items.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = _index_names("memory_audit_events")
    if "ix_memory_audit_events_ts" not in indexes:
        op.create_index("ix_memory_audit_events_ts", "memory_audit_events", ["ts"])
    if "ix_memory_audit_events_thread_id" not in indexes:
        op.create_index("ix_memory_audit_events_thread_id", "memory_audit_events", ["thread_id"])
    if "ix_memory_audit_events_agent_id" not in indexes:
        op.create_index("ix_memory_audit_events_agent_id", "memory_audit_events", ["agent_id"])
    if "ix_memory_audit_events_source_message_id" not in indexes:
        op.create_index("ix_memory_audit_events_source_message_id", "memory_audit_events", ["source_message_id"])
    if "ix_memory_audit_events_op" not in indexes:
        op.create_index("ix_memory_audit_events_op", "memory_audit_events", ["op"])
    if "ix_memory_audit_events_memory_id" not in indexes:
        op.create_index("ix_memory_audit_events_memory_id", "memory_audit_events", ["memory_id"])
    if "ix_memory_audit_events_category" not in indexes:
        op.create_index("ix_memory_audit_events_category", "memory_audit_events", ["category"])
    if "ix_memory_audit_events_key" not in indexes:
        op.create_index("ix_memory_audit_events_key", "memory_audit_events", ["key"])
    if "ix_memory_audit_events_status" not in indexes:
        op.create_index("ix_memory_audit_events_status", "memory_audit_events", ["status"])
    if "ix_memory_audit_events_reason_code" not in indexes:
        op.create_index("ix_memory_audit_events_reason_code", "memory_audit_events", ["reason_code"])
    if "ix_memory_audit_events_thread_ts" not in indexes:
        op.create_index("ix_memory_audit_events_thread_ts", "memory_audit_events", ["thread_id", "ts"])


def downgrade() -> None:
    tables = _table_names()

    if "memory_audit_events" in tables:
        indexes = _index_names("memory_audit_events")
        for index_name in (
            "ix_memory_audit_events_thread_ts",
            "ix_memory_audit_events_reason_code",
            "ix_memory_audit_events_status",
            "ix_memory_audit_events_key",
            "ix_memory_audit_events_category",
            "ix_memory_audit_events_memory_id",
            "ix_memory_audit_events_op",
            "ix_memory_audit_events_source_message_id",
            "ix_memory_audit_events_agent_id",
            "ix_memory_audit_events_thread_id",
            "ix_memory_audit_events_ts",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="memory_audit_events")
        op.drop_table("memory_audit_events")

    if "memory_items" in tables:
        indexes = _index_names("memory_items")
        for index_name in (
            "ix_memory_items_active_unique",
            "ix_memory_items_thread_category_key",
            "ix_memory_items_is_deleted",
            "ix_memory_items_source_message_id",
            "ix_memory_items_key",
            "ix_memory_items_category",
            "ix_memory_items_thread_id",
            "ix_memory_items_public_id",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="memory_items")
        op.drop_table("memory_items")

    if "threads" in tables:
        indexes = _index_names("threads")
        for index_name in (
            "ix_threads_chat_active_unique",
            "ix_threads_last_active_at",
            "ix_threads_is_active",
            "ix_threads_chat_id",
            "ix_threads_public_id",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="threads")

        columns = _column_names("threads")
        for column_name in (
            "topic_fingerprint",
            "last_active_at",
            "memory_enabled",
            "is_active",
            "title",
            "chat_id",
            "public_id",
        ):
            if column_name in columns:
                op.drop_column("threads", column_name)

    if "session_messages" in tables:
        columns = _column_names("session_messages")
        if "token_estimate" in columns:
            op.drop_column("session_messages", "token_estimate")
