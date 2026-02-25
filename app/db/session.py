"""
Async session factory and dependency injection for Teiken Claw.

This module provides the async session factory and the get_db()
dependency injection function for FastAPI endpoints.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import get_engine


# Global session factory
_session_factory: async_sessionmaker[AsyncSession] | None = None


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


# Export commonly used items
__all__ = [
    "get_db",
    "get_db_context",
    "create_session",
    "get_session_factory",
]
