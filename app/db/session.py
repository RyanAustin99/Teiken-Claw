"""
Async session factory and dependency injection for Teiken Claw.

This module provides the async session factory and the get_db()
dependency injection function for FastAPI endpoints.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import get_engine, get_database_url


# Global session factory
_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the async session factory.
    
    Returns:
        async_sessionmaker: Factory for creating async sessions.
    """
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for database sessions.
    
    Yields an async session and ensures proper cleanup after use.
    Use this in FastAPI endpoints with Depends():
    
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    
    Yields:
        AsyncSession: An async database session.
    """
    factory = get_session_factory()
    session = factory()
    
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    
    Use this when you need a session outside of FastAPI dependency injection:
    
        async with get_db_context() as db:
            result = await db.execute(query)
    
    Yields:
        AsyncSession: An async database session.
    """
    factory = get_session_factory()
    session = factory()
    
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Backward-compatible async session context manager alias."""
    async with get_db_context() as session:
        yield session


async def create_session() -> AsyncSession:
    """
    Create a new database session.
    
    The caller is responsible for committing/rolling back and closing
    the session. Prefer get_db() or get_db_context() for automatic cleanup.
    
    Returns:
        AsyncSession: A new async database session.
    """
    factory = get_session_factory()
    return factory()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Backward-compatible async generator for direct session iteration."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        await session.close()


def get_sync_session_factory() -> sessionmaker[Session]:
    """
    Get or create a sync SQLAlchemy session factory.

    This exists for legacy modules that still use sync ORM patterns.
    """
    global _sync_session_factory

    if _sync_session_factory is None:
        db_url = get_database_url()
        if db_url.startswith("sqlite+aiosqlite://"):
            db_url = db_url.replace("sqlite+aiosqlite://", "sqlite://", 1)

        engine_kwargs = {"future": True}
        if db_url.startswith("sqlite://") and ":memory:" not in db_url:
            # Test and bot command paths create many short-lived sync sessions.
            # Increase pool headroom to avoid QueuePool exhaustion under load.
            engine_kwargs.update({"pool_size": 50, "max_overflow": 100, "pool_timeout": 30})
        engine = create_engine(db_url, **engine_kwargs)
        _sync_session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    return _sync_session_factory


def get_db_session() -> Session:
    """Get a synchronous SQLAlchemy session for legacy sync modules."""
    factory = get_sync_session_factory()
    return factory()


# Export commonly used items
__all__ = [
    "get_db",
    "get_db_context",
    "get_session",
    "create_session",
    "get_async_session",
    "get_sync_session_factory",
    "get_session_factory",
    "get_db_session",
]
