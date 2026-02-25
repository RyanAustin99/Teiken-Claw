"""Initial migration with all core tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the initial migration."""
    
    # =========================================================================
    # Session Management Tables
    # =========================================================================
    
    # Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('mode', sa.String(50), nullable=False, server_default='default'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sessions_chat_id', 'sessions', ['chat_id'])
    op.create_index('ix_sessions_chat_id_created', 'sessions', ['chat_id', 'created_at'])
    
    # Threads table
    op.create_table(
        'threads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_threads_session_id', 'threads', ['session_id'])
    op.create_index('ix_threads_session_id_created', 'threads', ['session_id', 'created_at'])
    
    # Session messages table
    op.create_table(
        'session_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name='ck_message_role')
    )
    op.create_index('ix_session_messages_thread_id', 'session_messages', ['thread_id'])
    op.create_index('ix_session_messages_thread_id_created', 'session_messages', ['thread_id', 'created_at'])
    
    # Thread summaries table
    op.create_table(
        'thread_summaries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_thread_summaries_thread_id', 'thread_summaries', ['thread_id'])
    op.create_index('ix_thread_summaries_thread_id_version', 'thread_summaries', ['thread_id', 'version'])
    
    # =========================================================================
    # Memory System Tables
    # =========================================================================
    
    # Memory records table
    op.create_table(
        'memory_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('memory_type', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('scope', sa.String(50), nullable=False, server_default='global'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "memory_type IN ('episodic', 'semantic', 'procedural', 'working')",
            name='ck_memory_type'
        ),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_confidence_range')
    )
    op.create_index('ix_memory_records_type', 'memory_records', ['memory_type'])
    op.create_index('ix_memory_records_type_scope', 'memory_records', ['memory_type', 'scope'])
    op.create_index('ix_memory_records_created', 'memory_records', ['created_at'])
    
    # Memory audits table
    op.create_table(
        'memory_audits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('memory_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['memory_id'], ['memory_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete', 'archive', 'restore')",
            name='ck_audit_action'
        )
    )
    op.create_index('ix_memory_audits_memory_id', 'memory_audits', ['memory_id'])
    
    # Embedding records table
    op.create_table(
        'embedding_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('vector_dim', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('memory_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['memory_id'], ['memory_records.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', 'embedding_model', name='uq_embedding_source')
    )
    op.create_index('ix_embedding_records_source_type', 'embedding_records', ['source_type'])
    op.create_index('ix_embedding_records_source_id', 'embedding_records', ['source_id'])
    op.create_index('ix_embedding_records_hash', 'embedding_records', ['content_hash'])
    
    # =========================================================================
    # Job Queue Tables
    # =========================================================================
    
    # Job dead letter table
    op.create_table(
        'job_dead_letters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(255), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('error_type', sa.String(255), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_job_dead_letters_job_id', 'job_dead_letters', ['job_id'])
    op.create_index('ix_job_dead_letters_created', 'job_dead_letters', ['created_at'])
    
    # =========================================================================
    # Scheduler Tables
    # =========================================================================
    
    # Scheduler job meta table
    op.create_table(
        'scheduler_job_metas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(255), nullable=False),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('trigger_config', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id'),
        sa.CheckConstraint(
            "trigger_type IN ('interval', 'cron', 'date', 'once')",
            name='ck_trigger_type'
        )
    )
    
    # Scheduler job runs table
    op.create_table(
        'scheduler_job_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['scheduler_job_metas.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name='ck_job_run_status'
        )
    )
    op.create_index('ix_scheduler_job_runs_job_id', 'scheduler_job_runs', ['job_id'])
    op.create_index('ix_scheduler_job_runs_started', 'scheduler_job_runs', ['started_at'])
    
    # =========================================================================
    # Audit & Observability Tables
    # =========================================================================
    
    # Tool audits table
    op.create_table(
        'tool_audits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tool_name', sa.String(255), nullable=False),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('args', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('thread_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tool_audits_tool_name', 'tool_audits', ['tool_name'])
    op.create_index('ix_tool_audits_created', 'tool_audits', ['created_at'])
    op.create_index('ix_tool_audits_session_tool', 'tool_audits', ['session_id', 'tool_name'])
    
    # Subagent runs table
    op.create_table(
        'subagent_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parent_session_id', sa.Integer(), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['parent_session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name='ck_subagent_status'
        )
    )
    op.create_index('ix_subagent_runs_parent_session_id', 'subagent_runs', ['parent_session_id'])
    
    # =========================================================================
    # Control & Idempotency Tables
    # =========================================================================
    
    # Control states table
    op.create_table(
        'control_states',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    op.create_index('ix_control_states_key', 'control_states', ['key'])
    
    # Idempotency keys table
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    op.create_index('ix_idempotency_keys_expires', 'idempotency_keys', ['expires_at'])
    
    # =========================================================================
    # Events Table
    # =========================================================================
    
    # App events table
    op.create_table(
        'app_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(255), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_app_events_type', 'app_events', ['event_type'])
    op.create_index('ix_app_events_type_created', 'app_events', ['event_type', 'created_at'])
    
    # =========================================================================
    # FTS5 Full-Text Search Tables
    # =========================================================================
    
    # Session messages FTS
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts USING fts5(
            content,
            content='session_messages',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)
    
    # Memory records FTS
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts USING fts5(
            content,
            content='memory_records',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)
    
    # FTS triggers for session_messages
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_ai AFTER INSERT ON session_messages
        BEGIN
            INSERT INTO session_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_ad AFTER DELETE ON session_messages
        BEGIN
            INSERT INTO session_messages_fts(session_messages_fts, rowid, content)
            VALUES('delete', old.id, old.content);
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_au AFTER UPDATE ON session_messages
        BEGIN
            INSERT INTO session_messages_fts(session_messages_fts, rowid, content)
            VALUES('delete', old.id, old.content);
            INSERT INTO session_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)
    
    # FTS triggers for memory_records
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_records_ai AFTER INSERT ON memory_records
        BEGIN
            INSERT INTO memory_records_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_records_ad AFTER DELETE ON memory_records
        BEGIN
            INSERT INTO memory_records_fts(memory_records_fts, rowid, content)
            VALUES('delete', old.id, old.content);
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_records_au AFTER UPDATE ON memory_records
        BEGIN
            INSERT INTO memory_records_fts(memory_records_fts, rowid, content)
            VALUES('delete', old.id, old.content);
            INSERT INTO memory_records_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)
    
    # =========================================================================
    # Seed Control States
    # =========================================================================
    
    op.execute("""
        INSERT INTO control_states (key, value, updated_at) VALUES
        ('maintenance_mode', 'false', datetime('now')),
        ('max_concurrent_jobs', '10', datetime('now')),
        ('memory_enabled', 'true', datetime('now')),
        ('scheduler_enabled', 'true', datetime('now')),
        ('last_migration_version', '001_initial', datetime('now')),
        ('feature_flags', '{}', datetime('now'))
    """)


def downgrade() -> None:
    """Revert the initial migration."""
    
    # Drop FTS triggers and tables
    op.execute("DROP TRIGGER IF EXISTS memory_records_au")
    op.execute("DROP TRIGGER IF EXISTS memory_records_ad")
    op.execute("DROP TRIGGER IF EXISTS memory_records_ai")
    op.execute("DROP TRIGGER IF EXISTS session_messages_au")
    op.execute("DROP TRIGGER IF EXISTS session_messages_ad")
    op.execute("DROP TRIGGER IF EXISTS session_messages_ai")
    op.execute("DROP TABLE IF EXISTS memory_records_fts")
    op.execute("DROP TABLE IF EXISTS session_messages_fts")
    
    # Drop tables in reverse order
    op.drop_table('app_events')
    op.drop_table('idempotency_keys')
    op.drop_table('control_states')
    op.drop_table('subagent_runs')
    op.drop_table('tool_audits')
    op.drop_table('scheduler_job_runs')
    op.drop_table('scheduler_job_metas')
    op.drop_table('job_dead_letters')
    op.drop_table('embedding_records')
    op.drop_table('memory_audits')
    op.drop_table('memory_records')
    op.drop_table('thread_summaries')
    op.drop_table('session_messages')
    op.drop_table('threads')
    op.drop_table('sessions')
