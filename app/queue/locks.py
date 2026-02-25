"""
Lock management for the Teiken Claw queue system.

This module provides:
- LockManager class for per-chat and per-session locking
- Async context managers for lock acquisition
- Lock timeout handling
- Deadlock prevention
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LockInfo:
    """Information about an active lock."""
    lock_id: str
    resource_type: str  # 'chat' or 'session'
    resource_id: str
    acquired_at: datetime
    timeout_seconds: int
    holder_task: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if this lock has expired."""
        expires_at = self.acquired_at + timedelta(seconds=self.timeout_seconds)
        return datetime.utcnow() > expires_at


class LockTimeoutError(Exception):
    """Raised when a lock cannot be acquired within the timeout."""
    pass


class LockManager:
    """
    Manager for per-chat and per-session locks.
    
    Prevents concurrent access to the same chat/session context,
    avoiding context corruption and race conditions.
    
    Features:
    - Per-chat locks for message processing
    - Per-session locks for conversation context
    - Configurable lock timeouts
    - Automatic expired lock cleanup
    - Deadlock prevention via timeout
    
    Attributes:
        default_timeout: Default lock timeout in seconds
        chat_locks: Dictionary of active chat locks
        session_locks: Dictionary of active session locks
    """
    
    def __init__(self, default_timeout: int = 300):
        """
        Initialize the lock manager.
        
        Args:
            default_timeout: Default lock timeout in seconds (default: 300 = 5 minutes)
        """
        self.default_timeout = default_timeout
        
        # Async locks for each resource
        self._chat_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        
        # Lock metadata
        self._lock_info: Dict[str, LockInfo] = {}
        
        # Track which task holds which lock
        self._lock_holders: Dict[str, Set[str]] = {}  # resource_id -> set of lock_ids
        
        # Global lock for managing the lock dictionaries
        self._manager_lock = asyncio.Lock()
        
        logger.info(
            f"LockManager initialized with default_timeout={default_timeout}s",
            extra={"event": "lock_manager_initialized"}
        )
    
    async def _get_or_create_chat_lock(self, chat_id: str) -> asyncio.Lock:
        """Get or create a lock for a chat ID."""
        async with self._manager_lock:
            if chat_id not in self._chat_locks:
                self._chat_locks[chat_id] = asyncio.Lock()
                self._lock_holders[f"chat:{chat_id}"] = set()
            return self._chat_locks[chat_id]
    
    async def _get_or_create_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a session ID."""
        async with self._manager_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
                self._lock_holders[f"session:{session_id}"] = set()
            return self._session_locks[session_id]
    
    def _generate_lock_id(self, resource_type: str, resource_id: str) -> str:
        """Generate a unique lock ID."""
        import uuid
        return f"{resource_type}:{resource_id}:{uuid.uuid4().hex[:8]}"
    
    async def _register_lock(self, lock_info: LockInfo) -> None:
        """Register a lock in the tracking system."""
        async with self._manager_lock:
            self._lock_info[lock_info.lock_id] = lock_info
            resource_key = f"{lock_info.resource_type}:{lock_info.resource_id}"
            if resource_key in self._lock_holders:
                self._lock_holders[resource_key].add(lock_info.lock_id)
    
    async def _unregister_lock(self, lock_id: str) -> None:
        """Unregister a lock from the tracking system."""
        async with self._manager_lock:
            if lock_id in self._lock_info:
                lock_info = self._lock_info.pop(lock_id)
                resource_key = f"{lock_info.resource_type}:{lock_info.resource_id}"
                if resource_key in self._lock_holders:
                    self._lock_holders[resource_key].discard(lock_id)
    
    @asynccontextmanager
    async def acquire_chat_lock(
        self,
        chat_id: str,
        timeout: Optional[int] = None,
    ):
        """
        Acquire a lock for a specific chat.
        
        This ensures only one job processes a chat at a time,
        preventing context corruption.
        
        Args:
            chat_id: The Telegram chat ID
            timeout: Lock timeout in seconds (default: uses default_timeout)
        
        Yields:
            LockInfo: Information about the acquired lock
        
        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        timeout = self.default_timeout if timeout is None else timeout
        lock = await self._get_or_create_chat_lock(chat_id)
        lock_id = self._generate_lock_id("chat", chat_id)
        
        # Try to acquire the lock with timeout
        try:
            if timeout <= 0:
                if lock.locked():
                    raise asyncio.TimeoutError()
                await lock.acquire()
            else:
                await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Failed to acquire chat lock: {chat_id} (timeout after {timeout}s)",
                extra={
                    "event": "lock_timeout",
                    "resource_type": "chat",
                    "resource_id": chat_id,
                    "timeout": timeout,
                }
            )
            raise LockTimeoutError(
                f"Could not acquire lock for chat {chat_id} within {timeout} seconds"
            )
        
        # Register the lock
        lock_info = LockInfo(
            lock_id=lock_id,
            resource_type="chat",
            resource_id=chat_id,
            acquired_at=datetime.utcnow(),
            timeout_seconds=timeout,
            holder_task=str(asyncio.current_task()) if asyncio.current_task() else None,
        )
        await self._register_lock(lock_info)
        
        logger.debug(
            f"Chat lock acquired: {chat_id}",
            extra={
                "event": "lock_acquired",
                "lock_id": lock_id,
                "resource_type": "chat",
                "resource_id": chat_id,
            }
        )
        
        try:
            yield lock_info
        finally:
            # Release the lock
            lock.release()
            await self._unregister_lock(lock_id)
            
            logger.debug(
                f"Chat lock released: {chat_id}",
                extra={
                    "event": "lock_released",
                    "lock_id": lock_id,
                    "resource_type": "chat",
                    "resource_id": chat_id,
                }
            )
    
    @asynccontextmanager
    async def acquire_session_lock(
        self,
        session_id: str,
        timeout: Optional[int] = None,
    ):
        """
        Acquire a lock for a specific session.
        
        This ensures only one job accesses a session context at a time.
        
        Args:
            session_id: The session ID
            timeout: Lock timeout in seconds (default: uses default_timeout)
        
        Yields:
            LockInfo: Information about the acquired lock
        
        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        timeout = self.default_timeout if timeout is None else timeout
        lock = await self._get_or_create_session_lock(session_id)
        lock_id = self._generate_lock_id("session", session_id)
        
        # Try to acquire the lock with timeout
        try:
            if timeout <= 0:
                if lock.locked():
                    raise asyncio.TimeoutError()
                await lock.acquire()
            else:
                await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Failed to acquire session lock: {session_id} (timeout after {timeout}s)",
                extra={
                    "event": "lock_timeout",
                    "resource_type": "session",
                    "resource_id": session_id,
                    "timeout": timeout,
                }
            )
            raise LockTimeoutError(
                f"Could not acquire lock for session {session_id} within {timeout} seconds"
            )
        
        # Register the lock
        lock_info = LockInfo(
            lock_id=lock_id,
            resource_type="session",
            resource_id=session_id,
            acquired_at=datetime.utcnow(),
            timeout_seconds=timeout,
            holder_task=str(asyncio.current_task()) if asyncio.current_task() else None,
        )
        await self._register_lock(lock_info)
        
        logger.debug(
            f"Session lock acquired: {session_id}",
            extra={
                "event": "lock_acquired",
                "lock_id": lock_id,
                "resource_type": "session",
                "resource_id": session_id,
            }
        )
        
        try:
            yield lock_info
        finally:
            # Release the lock
            lock.release()
            await self._unregister_lock(lock_id)
            
            logger.debug(
                f"Session lock released: {session_id}",
                extra={
                    "event": "lock_released",
                    "lock_id": lock_id,
                    "resource_type": "session",
                    "resource_id": session_id,
                }
            )
    
    def get_active_locks(self) -> Dict[str, LockInfo]:
        """
        Get information about all active locks.
        
        Returns:
            dict: Dictionary of lock_id -> LockInfo
        """
        return dict(self._lock_info)
    
    def get_lock_count(self) -> Dict[str, int]:
        """
        Get count of active locks by type.
        
        Returns:
            dict: Counts of chat_locks, session_locks, and total
        """
        chat_count = sum(1 for info in self._lock_info.values() if info.resource_type == "chat")
        session_count = sum(1 for info in self._lock_info.values() if info.resource_type == "session")
        
        return {
            "chat_locks": chat_count,
            "session_locks": session_count,
            "total": len(self._lock_info),
        }
    
    async def cleanup_expired_locks(self) -> int:
        """
        Remove metadata for expired locks.
        
        Note: This only cleans up the tracking metadata, not the actual locks.
        The actual asyncio.Lock objects will be garbage collected when no longer referenced.
        
        Returns:
            int: Number of expired locks cleaned up
        """
        expired_count = 0
        expired_lock_ids = [
            lock_id for lock_id, info in self._lock_info.items()
            if info.is_expired()
        ]
        
        for lock_id in expired_lock_ids:
            await self._unregister_lock(lock_id)
            expired_count += 1
            
            logger.warning(
                f"Cleaned up expired lock: {lock_id}",
                extra={"event": "lock_expired_cleanup", "lock_id": lock_id}
            )
        
        if expired_count > 0:
            logger.info(
                f"Cleaned up {expired_count} expired locks",
                extra={"event": "lock_cleanup", "count": expired_count}
            )
        
        return expired_count
    
    def is_chat_locked(self, chat_id: str) -> bool:
        """Check if a chat is currently locked."""
        lock = self._chat_locks.get(chat_id)
        return lock is not None and lock.locked()
    
    def is_session_locked(self, session_id: str) -> bool:
        """Check if a session is currently locked."""
        lock = self._session_locks.get(session_id)
        return lock is not None and lock.locked()


# Global lock manager instance (initialized by main app)
_lock_manager: Optional[LockManager] = None


def get_lock_manager() -> Optional[LockManager]:
    """Get the global lock manager instance."""
    return _lock_manager


def set_lock_manager(manager: LockManager) -> None:
    """Set the global lock manager instance."""
    global _lock_manager
    _lock_manager = manager


__all__ = [
    "LockManager",
    "LockInfo",
    "LockTimeoutError",
    "get_lock_manager",
    "set_lock_manager",
]
