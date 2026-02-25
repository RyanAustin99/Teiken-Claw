"""
Embedding service for Teiken Claw.

This module provides embedding generation and management using Ollama,
with support for:
    - Single and batch embedding generation
    - Embedding storage and retrieval
    - Similarity computation
    - Nearest neighbor search
    - Model version tracking and re-embedding

Key Features:
    - Uses Ollama nomic-embed-text model by default
    - Efficient batch processing
    - Cosine similarity computation
    - Integration with memory store
"""

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.memory.models import EmbeddingRecord, MemoryRecord
from app.memory.store import MemoryStore, get_memory_store

logger = logging.getLogger(__name__)


# Default embedding model
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Default embedding dimension (for nomic-embed-text)
DEFAULT_EMBEDDING_DIMENSION = 768

# Maximum batch size for embedding
MAX_BATCH_SIZE = 32


@dataclass
class EmbeddingConfig:
    """Configuration for embedding service."""
    
    model: str = DEFAULT_EMBEDDING_MODEL
    dimension: int = DEFAULT_EMBEDDING_DIMENSION
    enabled: bool = True
    batch_size: int = MAX_BATCH_SIZE
    
    def __post_init__(self):
        # Get model from settings if not specified
        if self.model == DEFAULT_EMBEDDING_MODEL:
            self.model = getattr(settings, "OLLAMA_EMBED_MODEL", DEFAULT_EMBEDDING_MODEL)


class EmbeddingService:
    """
    Embedding service using Ollama.
    
    Provides embedding generation, storage, and similarity computation.
    
    Attributes:
        config: Embedding configuration
        memory_store: Memory store for database access
        ollama_client: Ollama API client
        model_version: Current model version string
    """
    
    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        ollama_client: Optional[Any] = None,
        config: Optional[EmbeddingConfig] = None,
    ):
        """
        Initialize the embedding service.
        
        Args:
            memory_store: Memory store (uses global if None)
            ollama_client: Ollama client (uses global if None)
            config: Embedding configuration
        """
        self._memory_store = memory_store or get_memory_store()
        self._ollama_client = ollama_client
        self._config = config or EmbeddingConfig()
        
        # Track model version for re-embedding
        self._model_version = f"{self._config.model}_v1"
        
        logger.info(
            f"EmbeddingService initialized: model={self._config.model}, "
            f"dimension={self._config.dimension}"
        )
    
    @property
    def model_version(self) -> str:
        """Get the current model version string."""
        return self._model_version
    
    @property
    def model(self) -> str:
        """Get the current embedding model name."""
        return self._config.model
    
    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        return self._config.dimension
    
    def _get_ollama_client(self):
        """Get or create Ollama client."""
        if self._ollama_client is None:
            from app.agent.ollama_client import get_ollama_client
            self._ollama_client = get_ollama_client()
        return self._ollama_client
    
    def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate an embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (list of floats), or None if failed
        """
        if not self._config.enabled:
            logger.debug("Embedding service disabled")
            return None
        
        if not text or not text.strip():
            logger.debug("Empty text, skipping embedding")
            return None
        
        try:
            client = self._get_ollama_client()
            
            # Call Ollama embeddings API
            response = client.embeddings(
                model=self._config.model,
                prompt=text,
            )
            
            if response and "embedding" in response:
                embedding = response["embedding"]
                
                # Validate dimension
                if len(embedding) != self._config.dimension:
                    logger.warning(
                        f"Embedding dimension mismatch: expected {self._config.dimension}, "
                        f"got {len(embedding)}"
                    )
                    # Update config to match actual dimension
                    self._config.dimension = len(embedding)
                
                return embedding
            
            logger.warning("No embedding in response")
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    def embed_batch(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (or None for failed items)
        """
        if not self._config.enabled:
            return [None] * len(texts)
        
        results = []
        
        # Process in batches
        for i in range(0, len(texts), self._config.batch_size):
            batch = texts[i:i + self._config.batch_size]
            batch_results = self._embed_batch_internal(batch)
            results.extend(batch_results)
        
        return results
    
    def _embed_batch_internal(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """Internal batch embedding implementation."""
        results = []
        
        for text in texts:
            if not text or not text.strip():
                results.append(None)
                continue
            
            embedding = self.embed(text)
            results.append(embedding)
        
        return results
    
    def store_embedding(
        self,
        source_type: str,
        source_id: int,
        content: str,
        embedding: List[float],
    ) -> Optional[EmbeddingRecord]:
        """
        Store an embedding in the database.
        
        Args:
            source_type: Type of source (e.g., "memory", "message", "document")
            source_id: ID of the source record
            content: The content that was embedded
            embedding: The embedding vector
            
        Returns:
            Created embedding record, or None if failed
        """
        if not embedding:
            return None
        
        try:
            # Generate content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Create embedding record
            record = self._memory_store.create_embedding(
                source_type=source_type,
                source_id=source_id,
                content_hash=content_hash,
                embedding_model=self._config.model,
                vector_dim=len(embedding),
                embedding=embedding,
            )
            
            logger.debug(
                f"Stored embedding: source_type={source_type}, source_id={source_id}"
            )
            
            return record
            
        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            return None
    
    def get_embedding(
        self,
        source_type: str,
        source_id: int,
    ) -> Optional[List[float]]:
        """
        Get an embedding for a source.
        
        Args:
            source_type: Type of source
            source_id: ID of the source record
            
        Returns:
            Embedding vector, or None if not found
        """
        try:
            record = self._memory_store.get_embedding(
                source_type=source_type,
                source_id=source_id,
                embedding_model=self._config.model,
            )
            
            if record:
                return record.embedding
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            return None
    
    def compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        if len(embedding1) != len(embedding2):
            logger.warning(
                f"Embedding dimension mismatch: {len(embedding1)} vs {len(embedding2)}"
            )
            return 0.0
        
        # Compute dot product
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        
        # Compute magnitudes
        magnitude1 = math.sqrt(sum(a * a for a in embedding1))
        magnitude2 = math.sqrt(sum(b * b for b in embedding2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        # Cosine similarity
        similarity = dot_product / (magnitude1 * magnitude2)
        
        # Clamp to [0, 1] range (handle floating point errors)
        return max(0.0, min(1.0, similarity))
    
    def find_nearest(
        self,
        embedding: List[float],
        source_type: Optional[str] = None,
        scope: Optional[str] = None,
        limit: int = 10,
    ) -> List[Tuple[int, float]]:
        """
        Find nearest neighbors for an embedding.
        
        Args:
            embedding: Query embedding vector
            source_type: Optional filter by source type
            scope: Optional filter by scope (requires join with source)
            limit: Maximum number of results
            
        Returns:
            List of (source_id, similarity_score) tuples
        """
        if not embedding:
            return []
        
        try:
            session = self._memory_store._session
            
            # Query all embeddings of the same model
            query = session.query(EmbeddingRecord).filter(
                EmbeddingRecord.embedding_model == self._config.model,
                EmbeddingRecord.vector_dim == len(embedding),
            )
            
            if source_type:
                query = query.filter(EmbeddingRecord.source_type == source_type)
            
            records = query.limit(1000).all()  # Limit for performance
            
            # Compute similarities
            similarities = []
            for record in records:
                sim = self.compute_similarity(embedding, record.embedding)
                if sim > 0:  # Only include positive similarities
                    similarities.append((record.source_id, sim, record.source_type))
            
            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Filter by scope if specified
            if scope:
                filtered = []
                for source_id, sim, stype in similarities:
                    if stype == "memory":
                        memory = session.query(MemoryRecord).filter(
                            MemoryRecord.id == source_id
                        ).first()
                        if memory and memory.scope == scope:
                            filtered.append((source_id, sim))
                    else:
                        # For non-memory sources, include without scope filter
                        filtered.append((source_id, sim))
                similarities = filtered
            else:
                similarities = [(s[0], s[1]) for s in similarities]
            
            return similarities[:limit]
            
        except Exception as e:
            logger.error(f"Failed to find nearest embeddings: {e}")
            return []
    
    def needs_re_embedding(
        self,
        source_type: str,
        source_id: int,
        content: str,
    ) -> bool:
        """
        Check if a source needs re-embedding.
        
        Re-embedding is needed if:
        - No embedding exists
        - Content has changed (hash mismatch)
        - Model version has changed
        
        Args:
            source_type: Type of source
            source_id: ID of the source
            content: Current content
            
        Returns:
            True if re-embedding is needed
        """
        try:
            record = self._memory_store.get_embedding(
                source_type=source_type,
                source_id=source_id,
                embedding_model=self._config.model,
            )
            
            if not record:
                return True
            
            # Check content hash
            current_hash = hashlib.sha256(content.encode()).hexdigest()
            if record.content_hash != current_hash:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check re-embedding status: {e}")
            return True
    
    def re_embed(
        self,
        source_type: str,
        source_id: int,
        content: str,
    ) -> Optional[EmbeddingRecord]:
        """
        Re-embed a source.
        
        Args:
            source_type: Type of source
            source_id: ID of the source
            content: Content to embed
            
        Returns:
            New embedding record, or None if failed
        """
        # Generate new embedding
        embedding = self.embed(content)
        
        if not embedding:
            return None
        
        # Delete old embedding if exists
        try:
            session = self._memory_store._session
            session.query(EmbeddingRecord).filter(
                EmbeddingRecord.source_type == source_type,
                EmbeddingRecord.source_id == source_id,
                EmbeddingRecord.embedding_model == self._config.model,
            ).delete()
            session.commit()
        except Exception as e:
            logger.warning(f"Failed to delete old embedding: {e}")
        
        # Store new embedding
        return self.store_embedding(
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding=embedding,
        )
    
    def re_embed_all(
        self,
        source_type: str = "memory",
        batch_size: int = 100,
    ) -> Tuple[int, int]:
        """
        Re-embed all sources of a given type.
        
        This is useful when the embedding model changes.
        
        Args:
            source_type: Type of sources to re-embed
            batch_size: Number of records to process at once
            
        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failure = 0
        
        try:
            session = self._memory_store._session
            
            if source_type == "memory":
                # Get all memories
                memories = session.query(MemoryRecord).all()
                
                for memory in memories:
                    try:
                        result = self.re_embed(
                            source_type="memory",
                            source_id=memory.id,
                            content=memory.content,
                        )
                        
                        if result:
                            success += 1
                        else:
                            failure += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to re-embed memory {memory.id}: {e}")
                        failure += 1
                
                logger.info(
                    f"Re-embedding complete: success={success}, failure={failure}"
                )
            
            return (success, failure)
            
        except Exception as e:
            logger.error(f"Re-embedding failed: {e}")
            return (success, failure)
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current embedding model.
        
        Returns:
            Dictionary with model information
        """
        return {
            "model": self._config.model,
            "dimension": self._config.dimension,
            "version": self._model_version,
            "enabled": self._config.enabled,
        }


# Singleton instance
_embedding_instance: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get the global embedding service instance.
    
    Returns:
        EmbeddingService instance
    """
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = EmbeddingService()
    return _embedding_instance


def set_embedding_service(service: EmbeddingService) -> None:
    """
    Set the global embedding service instance.
    
    Args:
        service: The embedding service instance to use
    """
    global _embedding_instance
    _embedding_instance = service


__all__ = [
    "EmbeddingService",
    "EmbeddingConfig",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSION",
    "MAX_BATCH_SIZE",
    "get_embedding_service",
    "set_embedding_service",
]
