"""
Database initialization for Teiken Claw.

This module provides functions to initialize the database:
- Create all tables
- Apply SQLite PRAGMAs
- Seed control state defaults
- Create FTS5 full-text search tables
"""

import logging
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import Base, get_engine
from app.db.models import ALL_MODELS, ControlState
from app.db.pragmas import apply_pragmas, verify_pragmas
from app.db.session import get_db_context

logger = logging.getLogger(__name__)


# Default control state values
DEFAULT_CONTROL_STATES: dict[str, str] = {
    "maintenance_mode": "false",
    "max_concurrent_jobs": "10",
    "memory_enabled": "true",
    "scheduler_enabled": "true",
    "last_migration_version": "0",
    "feature_flags": "{}",
}


# FTS5 table creation SQL
FTS5_TABLES = {
    "session_messages_fts": """
        CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts USING fts5(
            content,
            content='session_messages',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """,
    "memory_records_fts": """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts USING fts5(
            content,
            content='memory_records',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """,
}


# FTS5 trigger SQL for keeping search index in sync
FTS5_TRIGGERS = {
    "session_messages": {
        "insert": """
            CREATE TRIGGER IF NOT EXISTS session_messages_ai AFTER INSERT ON session_messages
            BEGIN
                INSERT INTO session_messages_fts(rowid, content)
                VALUES (new.id, new.content);
            END
        """,
        "delete": """
            CREATE TRIGGER IF NOT EXISTS session_messages_ad AFTER DELETE ON session_messages
            BEGIN
                INSERT INTO session_messages_fts(session_messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
            END
        """,
        "update": """
            CREATE TRIGGER IF NOT EXISTS session_messages_au AFTER UPDATE ON session_messages
            BEGIN
                INSERT INTO session_messages_fts(session_messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
                INSERT INTO session_messages_fts(rowid, content)
                VALUES (new.id, new.content);
            END
        """,
    },
    "memory_records": {
        "insert": """
            CREATE TRIGGER IF NOT EXISTS memory_records_ai AFTER INSERT ON memory_records
            BEGIN
                INSERT INTO memory_records_fts(rowid, content)
                VALUES (new.id, new.content);
            END
        """,
        "delete": """
            CREATE TRIGGER IF NOT EXISTS memory_records_ad AFTER DELETE ON memory_records
            BEGIN
                INSERT INTO memory_records_fts(memory_records_fts, rowid, content)
                VALUES('delete', old.id, old.content);
            END
        """,
        "update": """
            CREATE TRIGGER IF NOT EXISTS memory_records_au AFTER UPDATE ON memory_records
            BEGIN
                INSERT INTO memory_records_fts(memory_records_fts, rowid, content)
                VALUES('delete', old.id, old.content);
                INSERT INTO memory_records_fts(rowid, content)
                VALUES (new.id, new.content);
            END
        """,
    },
}


async def create_tables(connection: AsyncConnection) -> None:
    """
    Create all database tables.
    
    Args:
        connection: The async database connection.
    """
    logger.info("Creating database tables...")
    
    # Create all tables from models
    await connection.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def create_fts5_tables(connection: AsyncConnection) -> None:
    """
    Create FTS5 full-text search tables and triggers.
    
    Args:
        connection: The async database connection.
    """
    logger.info("Creating FTS5 tables...")
    
    # Create FTS5 tables
    for table_name, create_sql in FTS5_TABLES.items():
        try:
            await connection.execute(text(create_sql))
            logger.debug(f"Created FTS5 table: {table_name}")
        except Exception as e:
            logger.warning(f"Failed to create FTS5 table {table_name}: {e}")
    
    # Create FTS5 triggers
    for table_name, triggers in FTS5_TRIGGERS.items():
        for trigger_type, trigger_sql in triggers.items():
            try:
                await connection.execute(text(trigger_sql))
                logger.debug(f"Created FTS5 trigger: {table_name}_{trigger_type}")
            except Exception as e:
                logger.warning(
                    f"Failed to create FTS5 trigger {table_name}_{trigger_type}: {e}"
                )
    
    logger.info("FTS5 tables created successfully")


async def seed_control_states(connection: AsyncConnection) -> None:
    """
    Seed default control state values.
    
    Args:
        connection: The async database connection.
    """
    logger.info("Seeding control states...")
    
    for key, value in DEFAULT_CONTROL_STATES.items():
        # Check if key already exists
        result = await connection.execute(
            text("SELECT id FROM control_states WHERE key = :key"),
            {"key": key}
        )
        
        if result.fetchone() is None:
            await connection.execute(
                text(
                    "INSERT INTO control_states (key, value, updated_at) "
                    "VALUES (:key, :value, datetime('now'))"
                ),
                {"key": key, "value": value}
            )
            logger.debug(f"Seeded control state: {key}={value}")
    
    logger.info("Control states seeded successfully")


async def init_db() -> dict:
    """
    Initialize the database with all tables, PRAGMAs, and seed data.
    
    This is the main entry point for database initialization.
    Should be called during application startup.
    
    Returns:
        dict: Initialization results including PRAGMA verification.
    """
    logger.info("Initializing database...")
    
    engine = get_engine()
    
    async with engine.begin() as connection:
        # Apply PRAGMAs first
        await apply_pragmas(connection)
        
        # Verify PRAGMAs
        pragma_results = await verify_pragmas(connection)
        logger.info(f"PRAGMA verification: {pragma_results}")
        
        # Create tables
        await create_tables(connection)
        
        # Create FTS5 tables
        await create_fts5_tables(connection)
        
        # Seed control states
        await seed_control_states(connection)
    
    logger.info("Database initialization complete")
    
    return {
        "status": "success",
        "pragmas": pragma_results,
        "tables_created": len(ALL_MODELS),
        "fts5_tables": list(FTS5_TABLES.keys()),
    }


async def verify_db() -> dict:
    """
    Verify database is properly initialized.
    
    Returns:
        dict: Verification results.
    """
    logger.info("Verifying database...")
    
    engine = get_engine()
    results = {
        "status": "healthy",
        "pragmas": {},
        "tables": [],
        "issues": [],
    }
    
    try:
        async with engine.connect() as connection:
            # Verify PRAGMAs
            results["pragmas"] = await verify_pragmas(connection)
            
            # Check WAL mode
            if results["pragmas"].get("journal_mode") != "wal":
                results["issues"].append("WAL mode not enabled")
            
            # Check foreign keys
            if results["pragmas"].get("foreign_keys") != 1:
                results["issues"].append("Foreign keys not enabled")
            
            # List tables
            table_result = await connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "ORDER BY name"
                )
            )
            results["tables"] = [row[0] for row in table_result.fetchall()]
            
            # Check for required tables
            required_tables = {model.__tablename__ for model in ALL_MODELS}
            existing_tables = set(results["tables"])
            missing_tables = required_tables - existing_tables
            
            if missing_tables:
                results["issues"].append(f"Missing tables: {missing_tables}")
            
            if results["issues"]:
                results["status"] = "issues_found"
            
    except Exception as e:
        results["status"] = "error"
        results["issues"].append(str(e))
        logger.error(f"Database verification failed: {e}")
    
    logger.info(f"Database verification: {results['status']}")
    return results


async def reset_db() -> dict:
    """
    Reset the database by dropping and recreating all tables.
    
    WARNING: This will delete all data!
    
    Returns:
        dict: Reset results.
    """
    logger.warning("Resetting database - all data will be lost!")
    
    engine = get_engine()
    
    async with engine.begin() as connection:
        # Drop all tables
        await connection.run_sync(Base.metadata.drop_all)
        logger.info("All tables dropped")
        
        # Recreate
        await apply_pragmas(connection)
        await create_tables(connection)
        await create_fts5_tables(connection)
        await seed_control_states(connection)
    
    logger.info("Database reset complete")
    
    return {
        "status": "success",
        "message": "Database reset complete",
    }


# Export commonly used items
__all__ = [
    "init_db",
    "verify_db",
    "reset_db",
    "create_tables",
    "create_fts5_tables",
    "seed_control_states",
    "DEFAULT_CONTROL_STATES",
]
