"""Phase 20: file operation audit table

Revision ID: 003_phase20_file_op_audits
Revises: 002_phase19_boot_columns
Create Date: 2026-02-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_phase20_file_op_audits"
down_revision: Union[str, None] = "002_phase19_boot_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Create file operation audit persistence."""
    if "file_op_audits" not in _table_names():
        op.create_table(
            "file_op_audits",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("agent_id", sa.String(length=255), nullable=True),
            sa.Column("thread_id", sa.String(length=255), nullable=True),
            sa.Column("session_id", sa.String(length=255), nullable=True),
            sa.Column("op", sa.String(length=64), nullable=False),
            sa.Column("path_rel", sa.String(length=2048), nullable=False),
            sa.Column("bytes_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bytes_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("correlation_id", sa.String(length=255), nullable=True),
            sa.CheckConstraint("status IN ('success', 'failure')", name="ck_file_op_audit_status"),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = _index_names("file_op_audits")
    if "ix_file_op_audits_ts" not in indexes:
        op.create_index("ix_file_op_audits_ts", "file_op_audits", ["ts"])
    if "ix_file_op_audits_session_ts" not in indexes:
        op.create_index("ix_file_op_audits_session_ts", "file_op_audits", ["session_id", "ts"])
    if "ix_file_op_audits_agent_id" not in indexes:
        op.create_index("ix_file_op_audits_agent_id", "file_op_audits", ["agent_id"])
    if "ix_file_op_audits_thread_id" not in indexes:
        op.create_index("ix_file_op_audits_thread_id", "file_op_audits", ["thread_id"])
    if "ix_file_op_audits_session_id" not in indexes:
        op.create_index("ix_file_op_audits_session_id", "file_op_audits", ["session_id"])
    if "ix_file_op_audits_op" not in indexes:
        op.create_index("ix_file_op_audits_op", "file_op_audits", ["op"])
    if "ix_file_op_audits_status" not in indexes:
        op.create_index("ix_file_op_audits_status", "file_op_audits", ["status"])
    if "ix_file_op_audits_error_code" not in indexes:
        op.create_index("ix_file_op_audits_error_code", "file_op_audits", ["error_code"])
    if "ix_file_op_audits_correlation_id" not in indexes:
        op.create_index("ix_file_op_audits_correlation_id", "file_op_audits", ["correlation_id"])


def downgrade() -> None:
    """Drop file operation audit persistence."""
    if "file_op_audits" not in _table_names():
        return

    indexes = _index_names("file_op_audits")
    for index_name in (
        "ix_file_op_audits_correlation_id",
        "ix_file_op_audits_error_code",
        "ix_file_op_audits_status",
        "ix_file_op_audits_op",
        "ix_file_op_audits_session_id",
        "ix_file_op_audits_thread_id",
        "ix_file_op_audits_agent_id",
        "ix_file_op_audits_session_ts",
        "ix_file_op_audits_ts",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name="file_op_audits")

    op.drop_table("file_op_audits")

