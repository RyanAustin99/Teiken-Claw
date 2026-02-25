"""
SQLite PRAGMA configuration for Teiken Claw.

This module provides WAL mode configuration and other SQLite optimizations
for better concurrency and reliability.
"""

import logging
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


# SQLite PRAGMA statements for optimal performance and reliability
SQLITE_PRAGMAS: List[Tuple[str, str]] = [
    # Enable WAL mode for better concurrent read/write performance
    ("journal_mode", "WAL"),
    
    # NORMAL is safe with WAL mode and faster than FULL
    ("synchronous", "NORMAL"),
    
    # Wait up to 5 seconds for locks before timing out
    ("busy_timeout", "5000"),
    
    # Enforce foreign key constraints
    ("foreign_keys", "ON"),
    
    # Set cache size (negative = KB, positive = pages)
    # -64000 = 64MB cache
    ("cache_size", "-64000"),
    
    # Use memory for temp tables
    ("temp_store", "MEMORY"),
    
    # Optimize for modern SSDs
    ("mmap_size", "268435456"),  # 256MB
]


async def apply_pragmas(connection: AsyncConnection) -> None:
    """
    Apply SQLite PRAGMA settings to a connection.
    
    This should be called when a new connection is established.
    
    Args:
        connection: The async database connection.
    """
    for pragma_name, pragma_value in SQLITE_PRAGMAS:
        try:
            await connection.execute(
                text(f"PRAGMA {pragma_name}={pragma_value}")
            )
            logger.debug(f"Applied PRAGMA {pragma_name}={pragma_value}")
        except Exception as e:
            logger.warning(
                f"Failed to apply PRAGMA {pragma_name}={pragma_value}: {e}"
            )


async def verify_pragmas(connection: AsyncConnection) -> dict:
    """
    Verify current PRAGMA settings on a connection.
    
    Args:
        connection: The async database connection.
        
    Returns:
        dict: Current PRAGMA values.
    """
    results = {}
    
    for pragma_name, _ in SQLITE_PRAGMAS:
        try:
            result = await connection.execute(
                text(f"PRAGMA {pragma_name}")
            )
            value = result.scalar()
            results[pragma_name] = value
            logger.debug(f"PRAGMA {pragma_name} = {value}")
        except Exception as e:
            logger.warning(f"Failed to verify PRAGMA {pragma_name}: {e}")
            results[pragma_name] = None
    
    return results


async def apply_pragmas_on_connect(connection: AsyncConnection) -> None:
    """
    Event handler to apply PRAGMAs when a new connection is established.
    
    This is intended to be used as a SQLAlchemy event listener:
    
        from sqlalchemy import event
        from app.db.pragmas import apply_pragmas_on_connect
        
        event.listen(engine.sync_engine, "connect", apply_pragmas_on_connect)
    
    Args:
        connection: The raw DB-API connection.
    """
    cursor = connection.cursor()
    
    for pragma_name, pragma_value in SQLITE_PRAGMAS:
        try:
            cursor.execute(f"PRAGMA {pragma_name}={pragma_value}")
        except Exception as e:
            logger.warning(
                f"Failed to apply PRAGMA {pragma_name}={pragma_value}: {e}"
            )
    
    cursor.close()


def get_wal_checkpoint_command(mode: str = "PASSIVE") -> str:
    """
    Get a WAL checkpoint command.
    
    Modes:
    - PASSIVE: Checkpoint without blocking writers (default)
    - FULL: Wait for writers to finish, then checkpoint
    - RESTART: Like FULL, but also blocks new writers
    - TRUNCATE: Like RESTART, but also truncates WAL file
    
    Args:
        mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE).
        
    Returns:
        str: The PRAGMA wal_checkpoint command.
    """
    return f"PRAGMA wal_checkpoint({mode})"


async def checkpoint_wal(connection: AsyncConnection, mode: str = "PASSIVE") -> dict:
    """
    Perform a WAL checkpoint.
    
    Args:
        connection: The async database connection.
        mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE).
        
    Returns:
        dict: Checkpoint results with keys:
            - busy: Number of busy callbacks
            - log: Number of WAL frames checkpointed
            - checkpointed: Number of WAL frames moved to database
    """
    result = await connection.execute(
        text(get_wal_checkpoint_command(mode))
    )
    row = result.fetchone()
    
    if row:
        return {
            "busy": row[0],
            "log": row[1],
            "checkpointed": row[2],
        }
    
    return {"busy": 0, "log": 0, "checkpointed": 0}


# Export commonly used items
__all__ = [
    "SQLITE_PRAGMAS",
    "apply_pragmas",
    "verify_pragmas",
    "apply_pragmas_on_connect",
    "checkpoint_wal",
    "get_wal_checkpoint_command",
]
