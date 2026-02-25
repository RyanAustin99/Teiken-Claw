"""
Memory deduplication for Teiken Claw.

This module provides deduplication logic for memory records, including:
- Content hashing for exact duplicate detection
- Semantic similarity detection using embeddings
- Duplicate marking and management

Key Features:
    - SHA-256 content hashing
    - Semantic similarity via embeddings
    - Configurable similarity thresholds
    - Integration with memory store
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session as SQLAlchemySession

from app.config.settings import settings
from app.memory.models import MemoryRecord, MemoryAudit
from app.memory.store import MemoryStore, get_memory_store

logger = logging.getLogger(__name__)


# Default similarity threshold for semantic deduplication
DEFAULT_SIMILARITY_THRESHOLD = 0.9


@dataclass
class DedupeConfig:
    """Configuration for memory deduplication."""
    
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    enabled: bool = True
    check_semantic: bool = True
    max_candidates: int = 100


class MemoryDeduplicator:
    """
    Memory deduplication system.
    
    Provides both exact and semantic duplicate detection for memory records.
    
    Attributes:
        config: Deduplication configuration
        memory_store: Memory store for database access
        embedding_service: Embedding service for semantic similarity
    """
    
    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        config: Optional[DedupeConfig] = None,
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize the memory deduplicator.
        
        Args:
            memory_store: Memory store (uses global if None)
            config: Deduplication configuration
            embedding_service: Embedding service for semantic similarity
        """
        self._memory_store = memory_store or get_memory_store()
        self._config = config or DedupeConfig()
        self._embedding_service = embedding_service
        
        logger.info(
            f"MemoryDeduplicator initialized: threshold={self._config.similarity_threshold}, "
            f"semantic={self._config.check_semantic}"
        )
    
    def hash_content(self, content: str) -> str:
        """
        Generate a SHA-256 hash for content.
        
        Args:
            content: Content to hash
            
        Returns:
            SHA-256 hash string
        """
        normalized = content.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def check_duplicate(
        self,
        content: str,
        scope: Optional[str] = None,
    ) -> Optional[MemoryRecord]:
        """
        Check if content is an exact duplicate of an existing memory.
        
        Args:
            content: Content to check
            scope: Optional scope to limit search
            
        Returns:
            Existing memory record if duplicate found, None otherwise
        """
        if not self._config.enabled:
            return None
        
        content_hash = self.hash_content(content)
        
        # Query for exact content match
        session = self._memory_store._session
        query = session.query(MemoryRecord).filter(
            MemoryRecord.content == content
        )
        
        if scope:
            query = query.filter(MemoryRecord.scope == scope)
        
        existing = query.first()
        
        if existing:
            logger.debug(
                f"Exact duplicate found: memory_id={existing.id}, "
                f"hash={content_hash[:16]}..."
            )
            return existing
        
        return None
    
    def find_similar(
        self,
        content: str,
        scope: Optional[str] = None,
        threshold: Optional[float] = None,
        limit: int = 10,
    ) -> List[Tuple[MemoryRecord, float]]:
        """
        Find semantically similar memories.
        
        Args:
            content: Content to compare
            scope: Optional scope to limit search
            threshold: Similarity threshold (uses config default if None)
            limit: Maximum number of results
            
        Returns:
            List of (memory_record, similarity_score) tuples
        """
        if not self._config.enabled or not self._config.check_semantic:
            return []
        
        if not self._embedding_service:
            logger.warning("Embedding service not available for semantic similarity")
            return []
        
        threshold = threshold or self._config.similarity_threshold
        
        # Get embedding for content
        try:
            embedding = self._embedding_service.embed(content)
            if not embedding:
                return []
        except Exception as e:
            logger.error(f"Failed to get embedding for similarity check: {e}")
            return []
        
        # Find nearest neighbors
        try:
            nearest = self._embedding_service.find_nearest(
                embedding=embedding,
                source_type="memory",
                scope=scope,
                limit=self._config.max_candidates,
            )
        except Exception as e:
            logger.error(f"Failed to find nearest embeddings: {e}")
            return []
        
        results = []
        for source_id, score in nearest:
            if score < threshold:
                continue
            
            # Get the memory record
            memory = self._memory_store.get_memory(source_id)
            if memory:
                results.append((memory, score))
                
                if len(results) >= limit:
                    break
        
        if results:
            logger.debug(f"Found {len(results)} similar memories above threshold {threshold}")
        
        return results
    
    def semantic_similarity(
        self,
        content1: str,
        content2: str,
    ) -> float:
        """
        Compute semantic similarity between two content strings.
        
        Args:
            content1: First content string
            content2: Second content string
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not self._embedding_service:
            logger.warning("Embedding service not available for semantic similarity")
            return 0.0
        
        try:
            # Get embeddings for both contents
            embedding1 = self._embedding_service.embed(content1)
            embedding2 = self._embedding_service.embed(content2)
            
            if not embedding1 or not embedding2:
                return 0.0
            
            # Compute cosine similarity
            return self._embedding_service.compute_similarity(embedding1, embedding2)
            
        except Exception as e:
            logger.error(f"Failed to compute semantic similarity: {e}")
            return 0.0
    
    def mark_duplicate(
        self,
        memory_id: int,
        original_id: int,
        reason: str = "Duplicate detected",
    ) -> bool:
        """
        Mark a memory as a duplicate of another.
        
        This soft-deletes the duplicate memory and creates an audit record.
        
        Args:
            memory_id: ID of the duplicate memory
            original_id: ID of the original memory
            reason: Reason for marking as duplicate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = self._memory_store._session
            
            # Get both memories
            duplicate = session.query(MemoryRecord).filter(
                MemoryRecord.id == memory_id
            ).first()
            
            original = session.query(MemoryRecord).filter(
                MemoryRecord.id == original_id
            ).first()
            
            if not duplicate or not original:
                logger.warning(
                    f"Cannot mark duplicate: memory_id={memory_id} or original_id={original_id} not found"
                )
                return False
            
            # Create audit record for the duplicate
            audit = MemoryAudit(
                memory_id=memory_id,
                action="marked_duplicate",
                reason=f"{reason} (original_id={original_id})",
            )
            session.add(audit)
            
            # Soft-delete the duplicate by updating its scope
            duplicate.scope = f"duplicate_of_{original_id}"
            
            session.commit()
            
            logger.info(
                f"Marked memory {memory_id} as duplicate of {original_id}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark duplicate: {e}")
            session.rollback()
            return False
    
    def check_and_dedupe(
        self,
        content: str,
        scope: Optional[str] = None,
        auto_mark: bool = False,
    ) -> Tuple[bool, Optional[MemoryRecord], Optional[float]]:
        """
        Check for duplicates and optionally mark them.
        
        This is a convenience method that combines check_duplicate and find_similar.
        
        Args:
            content: Content to check
            scope: Optional scope to limit search
            auto_mark: Whether to automatically mark as duplicate
            
        Returns:
            Tuple of (is_duplicate, duplicate_record, similarity_score)
        """
        # First check for exact duplicate
        exact = self.check_duplicate(content, scope)
        if exact:
            return (True, exact, 1.0)
        
        # Then check for semantic similarity
        similar = self.find_similar(content, scope, limit=1)
        
        if similar:
            memory, score = similar[0]
            
            if auto_mark:
                # Note: We don't auto-mark here since the memory isn't created yet
                # The caller should handle this after memory creation
                pass
            
            return (True, memory, score)
        
        return (False, None, None)
    
    def get_duplicates_for_memory(
        self,
        memory_id: int,
    ) -> List[MemoryRecord]:
        """
        Get all memories marked as duplicates of a given memory.
        
        Args:
            memory_id: ID of the original memory
            
        Returns:
            List of duplicate memory records
        """
        session = self._memory_store._session
        
        # Find memories with scope "duplicate_of_{memory_id}"
        duplicates = session.query(MemoryRecord).filter(
            MemoryRecord.scope == f"duplicate_of_{memory_id}"
        ).all()
        
        return list(duplicates)
    
    def restore_duplicate(
        self,
        memory_id: int,
    ) -> bool:
        """
        Restore a memory that was marked as duplicate.
        
        Args:
            memory_id: ID of the duplicate memory
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = self._memory_store._session
            
            memory = session.query(MemoryRecord).filter(
                MemoryRecord.id == memory_id
            ).first()
            
            if not memory:
                return False
            
            # Check if it was marked as duplicate
            if not memory.scope.startswith("duplicate_of_"):
                return False
            
            # Restore original scope (default to "user")
            original_scope = "user"
            memory.scope = original_scope
            
            # Create audit record
            audit = MemoryAudit(
                memory_id=memory_id,
                action="restored_from_duplicate",
                reason="Restored from duplicate status",
            )
            session.add(audit)
            
            session.commit()
            
            logger.info(f"Restored memory {memory_id} from duplicate status")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore duplicate: {e}")
            session.rollback()
            return False
    
    def cleanup_duplicates(
        self,
        older_than_days: int = 30,
    ) -> int:
        """
        Permanently delete old duplicate memories.
        
        Args:
            older_than_days: Delete duplicates older than this many days
            
        Returns:
            Number of deleted records
        """
        from datetime import timedelta
        
        session = self._memory_store._session
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        
        # Find old duplicates
        duplicates = session.query(MemoryRecord).filter(
            MemoryRecord.scope.like("duplicate_of_%"),
            MemoryRecord.created_at < cutoff,
        ).all()
        
        count = 0
        for dup in duplicates:
            session.delete(dup)
            count += 1
        
        session.commit()
        
        if count > 0:
            logger.info(f"Cleaned up {count} old duplicate memories")
        
        return count


# Singleton instance
_deduplicator_instance: Optional[MemoryDeduplicator] = None


def get_deduplicator() -> MemoryDeduplicator:
    """
    Get the global memory deduplicator instance.
    
    Returns:
        MemoryDeduplicator instance
    """
    global _deduplicator_instance
    if _deduplicator_instance is None:
        _deduplicator_instance = MemoryDeduplicator()
    return _deduplicator_instance


def set_deduplicator(deduplicator: MemoryDeduplicator) -> None:
    """
    Set the global memory deduplicator instance.
    
    Args:
        deduplicator: The deduplicator instance to use
    """
    global _deduplicator_instance
    _deduplicator_instance = deduplicator


__all__ = [
    "MemoryDeduplicator",
    "DedupeConfig",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "get_deduplicator",
    "set_deduplicator",
]
