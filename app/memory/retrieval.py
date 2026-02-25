"""
Hybrid retrieval system for Teiken Claw.

This module provides hybrid retrieval combining:
    - FTS5 keyword search for exact term matching
    - Semantic search via embeddings for conceptual similarity
    - Result merging and ranking

Key Features:
    - Combines keyword and semantic search
    - Configurable retrieval budget
    - Score normalization and fusion
    - Scope-aware filtering
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session as SQLAlchemySession

from app.config.settings import settings
from app.memory.models import MemoryRecord, EmbeddingRecord
from app.memory.store import MemoryStore, get_memory_store

logger = logging.getLogger(__name__)


# Default retrieval parameters
DEFAULT_TOP_K = 10
DEFAULT_SEMANTIC_THRESHOLD = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.4
DEFAULT_SEMANTIC_WEIGHT = 0.6


@dataclass
class RetrievalConfig:
    """Configuration for hybrid retrieval."""
    
    top_k: int = DEFAULT_TOP_K
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT
    max_candidates: int = 100
    enabled: bool = True


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    
    memory_id: int
    content: str
    memory_type: str
    scope: str
    tags: List[str]
    confidence: float
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    combined_score: float = 0.0
    source: str = "hybrid"  # "keyword", "semantic", or "hybrid"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "memory_type": self.memory_type,
            "scope": self.scope,
            "tags": self.tags,
            "confidence": self.confidence,
            "keyword_score": self.keyword_score,
            "semantic_score": self.semantic_score,
            "combined_score": self.combined_score,
            "source": self.source,
        }


class MemoryRetriever:
    """
    Hybrid memory retrieval system.
    
    Combines keyword search (FTS5-like) with semantic search (embeddings)
    for comprehensive memory retrieval.
    
    Attributes:
        config: Retrieval configuration
        memory_store: Memory store for database access
        embedding_service: Embedding service for semantic search
    """
    
    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        embedding_service: Optional[Any] = None,
        config: Optional[RetrievalConfig] = None,
    ):
        """
        Initialize the memory retriever.
        
        Args:
            memory_store: Memory store (uses global if None)
            embedding_service: Embedding service for semantic search
            config: Retrieval configuration
        """
        self._memory_store = memory_store or get_memory_store()
        self._embedding_service = embedding_service
        self._config = config or RetrievalConfig()
        
        logger.info(
            f"MemoryRetriever initialized: top_k={self._config.top_k}, "
            f"keyword_weight={self._config.keyword_weight}, "
            f"semantic_weight={self._config.semantic_weight}"
        )
    
    def _get_embedding_service(self):
        """Get or create embedding service."""
        if self._embedding_service is None:
            from app.memory.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service
    
    def retrieve(
        self,
        query: str,
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories using hybrid search.
        
        Combines keyword and semantic search, merges and ranks results.
        
        Args:
            query: Search query
            scope: Optional scope filter
            memory_type: Optional memory type filter
            tags: Optional tags filter
            limit: Maximum results (uses config default if None)
            
        Returns:
            List of memory dictionaries with scores
        """
        if not self._config.enabled:
            return []
        
        limit = limit or self._config.top_k
        
        if not query or not query.strip():
            return []
        
        logger.debug(f"Hybrid retrieval for query: {query[:50]}...")
        
        # Get keyword search results
        keyword_results = self.keyword_search(
            query=query,
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=self._config.max_candidates,
        )
        
        # Get semantic search results
        semantic_results = self.semantic_search(
            query=query,
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=self._config.max_candidates,
        )
        
        # Merge and rank results
        merged = self.merge_results(keyword_results, semantic_results)
        
        # Rank and return top N
        ranked = self.rank_results(merged)
        
        return [r.to_dict() for r in ranked[:limit]]
    
    def keyword_search(
        self,
        query: str,
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[RetrievalResult]:
        """
        Perform keyword-based search.
        
        Uses SQL LIKE for text matching (FTS5 placeholder).
        
        Args:
            query: Search query
            scope: Optional scope filter
            memory_type: Optional memory type filter
            tags: Optional tags filter
            limit: Maximum results
            
        Returns:
            List of retrieval results with keyword scores
        """
        try:
            session = self._memory_store._session
            
            # Build query
            base_query = session.query(MemoryRecord)
            
            # Filter by scope
            if scope:
                base_query = base_query.filter(MemoryRecord.scope == scope)
            
            # Filter by memory type
            if memory_type:
                base_query = base_query.filter(MemoryRecord.memory_type == memory_type)
            
            # Filter by tags
            if tags:
                base_query = base_query.filter(MemoryRecord.tags.overlap(tags))
            
            # Text search on content
            # Split query into terms for better matching
            terms = query.lower().split()
            
            results = []
            
            # Search for each term and aggregate scores
            memories = base_query.limit(limit * 2).all()
            
            for memory in memories:
                content_lower = memory.content.lower()
                
                # Calculate keyword score based on term matches
                term_scores = []
                for term in terms:
                    if term in content_lower:
                        # Score based on term frequency and position
                        count = content_lower.count(term)
                        # Normalize by content length
                        score = min(1.0, count * 10 / max(1, len(content_lower.split())))
                        term_scores.append(score)
                
                if term_scores:
                    # Average term score
                    keyword_score = sum(term_scores) / len(terms)
                    
                    results.append(RetrievalResult(
                        memory_id=memory.id,
                        content=memory.content,
                        memory_type=memory.memory_type,
                        scope=memory.scope,
                        tags=memory.tags or [],
                        confidence=memory.confidence,
                        keyword_score=keyword_score,
                        semantic_score=0.0,
                        source="keyword",
                    ))
            
            # Sort by keyword score
            results.sort(key=lambda x: x.keyword_score, reverse=True)
            
            logger.debug(f"Keyword search found {len(results)} results")
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
    
    def semantic_search(
        self,
        query: str,
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[RetrievalResult]:
        """
        Perform semantic search using embeddings.
        
        Args:
            query: Search query
            scope: Optional scope filter
            memory_type: Optional memory type filter
            tags: Optional tags filter
            limit: Maximum results
            
        Returns:
            List of retrieval results with semantic scores
        """
        try:
            embedding_service = self._get_embedding_service()
            
            # Get query embedding
            query_embedding = embedding_service.embed(query)
            
            if not query_embedding:
                logger.warning("Failed to get query embedding")
                return []
            
            # Find nearest neighbors
            nearest = embedding_service.find_nearest(
                embedding=query_embedding,
                source_type="memory",
                scope=scope,
                limit=self._config.max_candidates,
            )
            
            results = []
            
            for memory_id, semantic_score in nearest:
                # Filter by threshold
                if semantic_score < self._config.semantic_threshold:
                    continue
                
                # Get memory record
                memory = self._memory_store.get_memory(memory_id)
                
                if not memory:
                    continue
                
                # Apply additional filters
                if memory_type and memory.memory_type != memory_type:
                    continue
                
                if tags and not any(t in (memory.tags or []) for t in tags):
                    continue
                
                results.append(RetrievalResult(
                    memory_id=memory.id,
                    content=memory.content,
                    memory_type=memory.memory_type,
                    scope=memory.scope,
                    tags=memory.tags or [],
                    confidence=memory.confidence,
                    keyword_score=0.0,
                    semantic_score=semantic_score,
                    source="semantic",
                ))
            
            # Sort by semantic score
            results.sort(key=lambda x: x.semantic_score, reverse=True)
            
            logger.debug(f"Semantic search found {len(results)} results")
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def merge_results(
        self,
        keyword_results: List[RetrievalResult],
        semantic_results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """
        Merge keyword and semantic search results.
        
        Combines scores from both sources using weighted fusion.
        
        Args:
            keyword_results: Results from keyword search
            semantic_results: Results from semantic search
            
        Returns:
            Merged results with combined scores
        """
        # Index results by memory_id
        merged_dict: Dict[int, RetrievalResult] = {}
        
        # Add keyword results
        for result in keyword_results:
            merged_dict[result.memory_id] = RetrievalResult(
                memory_id=result.memory_id,
                content=result.content,
                memory_type=result.memory_type,
                scope=result.scope,
                tags=result.tags,
                confidence=result.confidence,
                keyword_score=result.keyword_score,
                semantic_score=0.0,
                source="keyword",
            )
        
        # Merge semantic results
        for result in semantic_results:
            if result.memory_id in merged_dict:
                # Update existing result
                existing = merged_dict[result.memory_id]
                existing.semantic_score = result.semantic_score
                existing.source = "hybrid"
            else:
                # Add new result
                merged_dict[result.memory_id] = RetrievalResult(
                    memory_id=result.memory_id,
                    content=result.content,
                    memory_type=result.memory_type,
                    scope=result.scope,
                    tags=result.tags,
                    confidence=result.confidence,
                    keyword_score=0.0,
                    semantic_score=result.semantic_score,
                    source="semantic",
                )
        
        return list(merged_dict.values())
    
    def rank_results(
        self,
        results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """
        Rank results by combined score.
        
        Uses weighted combination of keyword and semantic scores.
        
        Args:
            results: Results to rank
            
        Returns:
            Ranked results
        """
        for result in results:
            # Compute combined score
            result.combined_score = (
                self._config.keyword_weight * result.keyword_score +
                self._config.semantic_weight * result.semantic_score
            )
            
            # Boost by confidence
            result.combined_score *= (0.5 + 0.5 * result.confidence)
        
        # Sort by combined score
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        return results
    
    def retrieve_with_budget(
        self,
        query: str,
        scope: Optional[str] = None,
        max_tokens: int = 2000,
        avg_tokens_per_memory: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories within a token budget.
        
        Args:
            query: Search query
            scope: Optional scope filter
            max_tokens: Maximum tokens to include
            avg_tokens_per_memory: Average tokens per memory (for estimation)
            
        Returns:
            List of memories within budget
        """
        # Estimate max memories based on budget
        max_memories = max_tokens // avg_tokens_per_memory
        
        # Retrieve more than needed, then truncate
        results = self.retrieve(
            query=query,
            scope=scope,
            limit=max_memories * 2,
        )
        
        # Truncate to budget
        return results[:max_memories]
    
    def get_relevant_memories(
        self,
        context: str,
        scope: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get memories relevant to a context.
        
        This is a convenience method for context building.
        
        Args:
            context: Context text to find relevant memories for
            scope: Optional scope filter
            limit: Maximum results
            
        Returns:
            List of relevant memories
        """
        return self.retrieve(
            query=context,
            scope=scope,
            limit=limit,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get retrieval statistics.
        
        Returns:
            Dictionary with retrieval statistics
        """
        try:
            session = self._memory_store._session
            
            # Count memories
            total_memories = session.query(MemoryRecord).count()
            
            # Count embeddings
            total_embeddings = session.query(EmbeddingRecord).count()
            
            return {
                "total_memories": total_memories,
                "total_embeddings": total_embeddings,
                "config": {
                    "top_k": self._config.top_k,
                    "semantic_threshold": self._config.semantic_threshold,
                    "keyword_weight": self._config.keyword_weight,
                    "semantic_weight": self._config.semantic_weight,
                },
            }
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Singleton instance
_retriever_instance: Optional[MemoryRetriever] = None


def get_retriever() -> MemoryRetriever:
    """
    Get the global memory retriever instance.
    
    Returns:
        MemoryRetriever instance
    """
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = MemoryRetriever()
    return _retriever_instance


def set_retriever(retriever: MemoryRetriever) -> None:
    """
    Set the global memory retriever instance.
    
    Args:
        retriever: The retriever instance to use
    """
    global _retriever_instance
    _retriever_instance = retriever


__all__ = [
    "MemoryRetriever",
    "RetrievalConfig",
    "RetrievalResult",
    "DEFAULT_TOP_K",
    "DEFAULT_SEMANTIC_THRESHOLD",
    "DEFAULT_KEYWORD_WEIGHT",
    "DEFAULT_SEMANTIC_WEIGHT",
    "get_retriever",
    "set_retriever",
]
