"""
Thread-bound memory card persistence for Memory v1.5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session as SQLAlchemySession

from app.db.base import Base
from app.db.session import get_db_session
from app.memory.models import MemoryItem


def _new_memory_public_id() -> str:
    return f"m_{uuid4().hex[:24]}"


class MemoryStoreV15:
    """Store for deterministic thread-scoped memories."""

    def __init__(self, session: Optional[SQLAlchemySession] = None):
        self._session = session or get_db_session()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            bind = self._session.get_bind()
            if bind is None:
                return
            inspector = sa_inspect(bind)
            tables = set(inspector.get_table_names())
            if "memory_items" not in tables:
                Base.metadata.create_all(bind=bind)
        except Exception:
            self._session.rollback()

    def upsert_memory(
        self,
        thread_id: int,
        category: str,
        key: str,
        value: str,
        source_message_id: Optional[int],
        confidence: float = 1.0,
    ) -> Tuple[MemoryItem, str]:
        normalized_category = (category or "").strip().lower()
        normalized_key = (key or "").strip().lower()
        normalized_value = (value or "").strip()

        existing = (
            self._session.query(MemoryItem)
            .filter(
                MemoryItem.thread_id == thread_id,
                MemoryItem.category == normalized_category,
                MemoryItem.key == normalized_key,
                MemoryItem.is_deleted.is_(False),
            )
            .first()
        )
        if existing:
            existing.value = normalized_value
            existing.confidence = confidence
            existing.source_message_id = source_message_id
            existing.updated_at = datetime.utcnow()
            self._session.commit()
            self._session.refresh(existing)
            return existing, "update"

        memory = MemoryItem(
            public_id=_new_memory_public_id(),
            thread_id=thread_id,
            category=normalized_category,
            key=normalized_key,
            value=normalized_value,
            confidence=confidence,
            source_message_id=source_message_id,
            is_deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._session.add(memory)
        self._session.commit()
        self._session.refresh(memory)
        return memory, "add"

    def soft_delete_memory(self, thread_id: int, memory_public_id: str) -> bool:
        item = (
            self._session.query(MemoryItem)
            .filter(
                MemoryItem.thread_id == thread_id,
                MemoryItem.public_id == (memory_public_id or "").strip(),
                MemoryItem.is_deleted.is_(False),
            )
            .first()
        )
        if not item:
            return False
        item.is_deleted = True
        item.updated_at = datetime.utcnow()
        self._session.commit()
        return True

    def get_memory(self, thread_id: int, memory_public_id: str, include_deleted: bool = False) -> Optional[MemoryItem]:
        query = (
            self._session.query(MemoryItem)
            .filter(MemoryItem.thread_id == thread_id, MemoryItem.public_id == (memory_public_id or "").strip())
        )
        if not include_deleted:
            query = query.filter(MemoryItem.is_deleted.is_(False))
        return query.first()

    def list_memories(
        self,
        thread_id: int,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> List[MemoryItem]:
        query = self._session.query(MemoryItem).filter(MemoryItem.thread_id == thread_id)
        if not include_deleted:
            query = query.filter(MemoryItem.is_deleted.is_(False))
        return (
            query.order_by(MemoryItem.updated_at.desc(), MemoryItem.id.desc())
            .limit(max(1, limit))
            .all()
        )

    def search_memories(
        self,
        thread_id: int,
        query: str,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryItem]:
        pattern = f"%{(query or '').strip()}%"
        stmt = (
            self._session.query(MemoryItem)
            .filter(MemoryItem.thread_id == thread_id, MemoryItem.is_deleted.is_(False))
            .filter(or_(MemoryItem.key.ilike(pattern), MemoryItem.value.ilike(pattern)))
        )
        if category:
            stmt = stmt.filter(MemoryItem.category == category.strip().lower())
        return (
            stmt.order_by(MemoryItem.updated_at.desc(), MemoryItem.id.desc())
            .limit(max(1, limit))
            .all()
        )

    def stats_by_category(self, thread_id: int) -> Dict[str, int]:
        rows = (
            self._session.query(MemoryItem.category, func.count(MemoryItem.id))
            .filter(MemoryItem.thread_id == thread_id, MemoryItem.is_deleted.is_(False))
            .group_by(MemoryItem.category)
            .all()
        )
        return {category: int(count) for category, count in rows}
