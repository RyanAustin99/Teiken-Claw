"""
SQLAlchemy base and engine setup for Teiken Claw.

This module provides the async engine, declarative base, and connection
pooling configuration for SQLite with WAL mode support.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from typing import Optional
import os

from app.config.settings import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Global engine instance
_engine: Optional[AsyncEngine] = None


def get_database_url() -> str:
    """
    Get the database URL, converting sqlite:// to sqlite+aiosqlite://
    for async support.
    """
    db_url = settings.DATABASE_URL
    
    # Convert sqlite:// to sqlite+aiosqlite:// for async support
    if db_url.startswith("sqlite://"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    
    return db_url


def create_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine with proper configuration.
    
    For SQLite:
    - Uses StaticPool for in-memory databases
    - Configures check_same_thread for SQLite
    - Sets up connection pooling for file-based databases
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    db_url = get_database_url()
    
    # Engine configuration
    engine_kwargs = {
        "echo": settings.DATABASE_ECHO,
        "future": True,  # Use SQLAlchemy 2.0 style
    }
    
    # SQLite-specific configuration
    if "sqlite" in db_url:
        if ":memory:" in db_url:
            # In-memory database needs StaticPool
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # File-based SQLite with connection pooling
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10
            engine_kwargs["pool_timeout"] = 30
            engine_kwargs["pool_recycle"] = 3600
            engine_kwargs["connect_args"] = {"check_same_thread": False}
    
    _engine = create_async_engine(db_url, **engine_kwargs)
    
    return _engine


def get_engine() -> AsyncEngine:
    """
    Get the existing engine or create a new one.
    
    Returns:
        AsyncEngine: The SQLAlchemy async engine instance.
    """
    global _engine
    
    if _engine is None:
        return create_engine()
    
    return _engine


async def dispose_engine() -> None:
    """
    Dispose of the engine and all connections.
    Call this during application shutdown.
    """
    global _engine
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None


# Export commonly used items
__all__ = [
    "Base",
    "create_engine",
    "get_engine",
    "dispose_engine",
    "get_database_url",
]
