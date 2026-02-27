"""Phase 19: memory record source/key columns

Revision ID: 002_phase19_boot_columns
Revises: 001_initial
Create Date: 2026-02-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_phase19_boot_columns"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply phase 19 memory schema updates."""
    op.add_column(
        "memory_records",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="USER"),
    )
    op.add_column(
        "memory_records",
        sa.Column("key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_memory_records_scope_source",
        "memory_records",
        ["scope", "source"],
    )


def downgrade() -> None:
    """Revert phase 19 memory schema updates."""
    op.drop_index("ix_memory_records_scope_source", table_name="memory_records")
    op.drop_column("memory_records", "key")
    op.drop_column("memory_records", "source")

