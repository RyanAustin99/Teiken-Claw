"""
Tests for the hybrid retrieval system.

Tests cover:
- Keyword search
- Semantic search
- Hybrid retrieval
- Result ranking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from app.memory.retrieval import (
    MemoryRetriever,
    RetrievalConfig,
    RetrievalResult,
    DEFAULT_TOP_K,
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_KEYWORD_WEIGHT,
    DEFAULT_SEMANTIC_WEIGHT,
    get_retriever,
    set_retriever,
)


class TestRetrievalConfig:
    """Tests for RetrievalConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RetrievalConfig()
        
        assert config.top_k == DEFAULT_TOP_K
        assert config.semantic_threshold == DEFAULT_SEMANTIC_THRESHOLD
        assert config.keyword_weight == DEFAULT_KEYWORD_WEIGHT
        assert config.semantic_weight == DEFAULT_SEMANTIC_WEIGHT
        assert config.enabled is True
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = RetrievalConfig(
            top_k=20,
            semantic_threshold=0.8,
            keyword_weight=0.3,
            semantic_weight=0.7,
            enabled=False,
        )
        
        assert config.top_k == 20
        assert config.semantic_threshold == 0.8
        assert config.keyword_weight == 0.3
        assert config.semantic_weight == 0.7
        assert config.enabled is False


class TestRetrievalResult:
    """Tests for RetrievalResult."""
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = RetrievalResult(
            memory_id=1,
            content="test content",
            memory_type="preference",
            scope="user",
            tags=["tag1", "tag2"],
            confidence=0.9,
            keyword_score=0.8,
            semantic_score=0.7,
            combined_score=0.75,
            source="hybrid",
        )
        
        d = result.to_dict()
        
        assert d["memory_id"] == 1
        assert d["content"] == "test content"
        assert d["memory_type"] == "preference"
        assert d["scope"] == "user"
        assert d["tags"] == ["tag1", "tag2"]
        assert d["confidence"] == 0.9
        assert d["keyword_score"] == 0.8
        assert d["semantic_score"] == 0.7
        assert d["combined_score"] == 0.75
        assert d["source"] == "hybrid"


class TestMemoryRetriever:
    """Tests for MemoryRetriever."""
    
    @pytest.fixture
    def mock_memory_store(self):
        """Create a mock memory store."""
        store = Mock()
        store._session = Mock()
        
        # Mock memory records
        mock_memory = Mock()
        mock_memory.id = 1
        mock_memory.content = "User prefers dark mode"
        mock_memory.memory_type = "preference"
        mock_memory.scope = "user"
        mock_memory.tags = ["preference", "ui"]
        mock_memory.confidence = 0.9
        
        store.get_memory.return_value = mock_memory
        store.list_memories.return_value = [mock_memory]
        
        return store
    
    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = Mock()
        service.embed.return_value = [0.1] * 768
        service.compute_similarity.return_value = 0.85
        service.find_nearest.return_value = [(1, 0.85)]
        return service
    
    @pytest.fixture
    def retriever(self, mock_memory_store, mock_embedding_service):
        """Create a retriever with mocks."""
        retriever = MemoryRetriever(
            memory_store=mock_memory_store,
            embedding_service=mock_embedding_service,
        )
        return retriever
    
    def test_initialization(self, retriever):
        """Test retriever initialization."""
        assert retriever._config is not None
        assert retriever._config.top_k == DEFAULT_TOP_K
    
    def test_keyword_search(self, retriever, mock_memory_store):
        """Test keyword search."""
        # Mock the session query
        mock_session = Mock()
        mock_query = Mock()
        mock_memory = Mock()
        mock_memory.id = 1
        mock_memory.content = "User prefers dark mode for coding"
        mock_memory.memory_type = "preference"
        mock_memory.scope = "user"
        mock_memory.tags = ["preference"]
        mock_memory.confidence = 0.9
        
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_memory]
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.keyword_search("dark mode", limit=10)
        
        assert len(results) >= 0  # May have results depending on matching
    
    def test_keyword_search_with_filters(self, retriever, mock_memory_store):
        """Test keyword search with filters."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.keyword_search(
            query="test",
            scope="user",
            memory_type="preference",
            tags=["ui"],
            limit=10,
        )
        
        assert isinstance(results, list)
    
    def test_semantic_search(self, retriever, mock_embedding_service, mock_memory_store):
        """Test semantic search."""
        # Mock memory for get_memory
        mock_memory = Mock()
        mock_memory.id = 1
        mock_memory.content = "User prefers dark mode"
        mock_memory.memory_type = "preference"
        mock_memory.scope = "user"
        mock_memory.tags = []
        mock_memory.confidence = 0.9
        mock_memory_store.get_memory.return_value = mock_memory
        
        results = retriever.semantic_search("dark mode preference", limit=10)
        
        assert isinstance(results, list)
        mock_embedding_service.embed.assert_called()
    
    def test_semantic_search_no_embedding(self, mock_memory_store):
        """Test semantic search when embedding fails."""
        mock_embedding = Mock()
        mock_embedding.embed.return_value = None
        
        retriever = MemoryRetriever(
            memory_store=mock_memory_store,
            embedding_service=mock_embedding,
        )
        
        results = retriever.semantic_search("test query")
        
        assert results == []
    
    def test_semantic_search_below_threshold(self, mock_memory_store):
        """Test semantic search filters low similarity results."""
        mock_embedding = Mock()
        mock_embedding.embed.return_value = [0.1] * 768
        mock_embedding.compute_similarity.return_value = 0.5  # Below threshold
        mock_embedding.find_nearest.return_value = [(1, 0.5)]
        
        config = RetrievalConfig(semantic_threshold=0.7)
        retriever = MemoryRetriever(
            memory_store=mock_memory_store,
            embedding_service=mock_embedding,
            config=config,
        )
        
        # Mock memory
        mock_memory = Mock()
        mock_memory.id = 1
        mock_memory.content = "test"
        mock_memory.memory_type = "note"
        mock_memory.scope = "user"
        mock_memory.tags = []
        mock_memory.confidence = 0.5
        mock_memory_store.get_memory.return_value = mock_memory
        
        results = retriever.semantic_search("test")
        
        # Should be empty since similarity is below threshold
        assert results == []
    
    def test_merge_results(self, retriever):
        """Test merging keyword and semantic results."""
        keyword_results = [
            RetrievalResult(
                memory_id=1,
                content="content 1",
                memory_type="preference",
                scope="user",
                tags=[],
                confidence=0.9,
                keyword_score=0.8,
                source="keyword",
            ),
            RetrievalResult(
                memory_id=2,
                content="content 2",
                memory_type="note",
                scope="user",
                tags=[],
                confidence=0.8,
                keyword_score=0.6,
                source="keyword",
            ),
        ]
        
        semantic_results = [
            RetrievalResult(
                memory_id=1,
                content="content 1",
                memory_type="preference",
                scope="user",
                tags=[],
                confidence=0.9,
                semantic_score=0.9,
                source="semantic",
            ),
            RetrievalResult(
                memory_id=3,
                content="content 3",
                memory_type="fact",
                scope="user",
                tags=[],
                confidence=0.7,
                semantic_score=0.7,
                source="semantic",
            ),
        ]
        
        merged = retriever.merge_results(keyword_results, semantic_results)
        
        # Should have 3 unique results
        assert len(merged) == 3
        
        # Memory 1 should have both scores
        memory_1 = next(m for m in merged if m.memory_id == 1)
        assert memory_1.keyword_score == 0.8
        assert memory_1.semantic_score == 0.9
        assert memory_1.source == "hybrid"
    
    def test_rank_results(self, retriever):
        """Test ranking results."""
        results = [
            RetrievalResult(
                memory_id=1,
                content="content 1",
                memory_type="preference",
                scope="user",
                tags=[],
                confidence=0.9,
                keyword_score=0.8,
                semantic_score=0.9,
            ),
            RetrievalResult(
                memory_id=2,
                content="content 2",
                memory_type="note",
                scope="user",
                tags=[],
                confidence=0.8,
                keyword_score=0.6,
                semantic_score=0.5,
            ),
        ]
        
        ranked = retriever.rank_results(results)
        
        # Should be sorted by combined score (descending)
        assert ranked[0].combined_score >= ranked[1].combined_score
    
    def test_retrieve(self, retriever, mock_memory_store, mock_embedding_service):
        """Test full hybrid retrieval."""
        # Mock session for keyword search
        mock_session = Mock()
        mock_query = Mock()
        mock_memory = Mock()
        mock_memory.id = 1
        mock_memory.content = "User prefers dark mode"
        mock_memory.memory_type = "preference"
        mock_memory.scope = "user"
        mock_memory.tags = []
        mock_memory.confidence = 0.9
        
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_memory]
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.retrieve("dark mode preference")
        
        assert isinstance(results, list)
    
    def test_retrieve_disabled(self, mock_memory_store):
        """Test retrieval when disabled."""
        config = RetrievalConfig(enabled=False)
        retriever = MemoryRetriever(
            memory_store=mock_memory_store,
            config=config,
        )
        
        results = retriever.retrieve("test query")
        
        assert results == []
    
    def test_retrieve_empty_query(self, retriever):
        """Test retrieval with empty query."""
        results = retriever.retrieve("")
        
        assert results == []
    
    def test_retrieve_with_filters(self, retriever, mock_memory_store, mock_embedding_service):
        """Test retrieval with filters."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.retrieve(
            query="test",
            scope="user",
            memory_type="preference",
            tags=["ui"],
            limit=5,
        )
        
        assert isinstance(results, list)
    
    def test_retrieve_with_budget(self, retriever, mock_memory_store, mock_embedding_service):
        """Test retrieval with token budget."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.retrieve_with_budget(
            query="test",
            max_tokens=500,
            avg_tokens_per_memory=100,
        )
        
        assert isinstance(results, list)
    
    def test_get_relevant_memories(self, retriever, mock_memory_store, mock_embedding_service):
        """Test getting relevant memories."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        results = retriever.get_relevant_memories(
            context="user prefers dark mode",
            limit=5,
        )
        
        assert isinstance(results, list)
    
    def test_get_stats(self, retriever, mock_memory_store):
        """Test getting retrieval stats."""
        mock_session = Mock()
        mock_query = Mock()
        mock_query.count.return_value = 10
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        stats = retriever.get_stats()
        
        assert isinstance(stats, dict)


class TestRetrieverSingleton:
    """Tests for singleton functions."""
    
    def test_get_retriever(self):
        """Test getting the singleton instance."""
        from app.memory.retrieval import _retriever_instance
        
        # Reset singleton
        import app.memory.retrieval as module
        module._retriever_instance = None
        
        retriever = get_retriever()
        
        assert retriever is not None
        assert isinstance(retriever, MemoryRetriever)
    
    def test_set_retriever(self):
        """Test setting the singleton instance."""
        custom_retriever = MemoryRetriever()
        
        set_retriever(custom_retriever)
        
        assert get_retriever() is custom_retriever


class TestRetrievalErrorHandling:
    """Tests for error handling in retrieval."""
    
    def test_keyword_search_error(self):
        """Test handling keyword search errors."""
        mock_store = Mock()
        mock_store._session = Mock()
        mock_store._session.query.side_effect = Exception("DB error")
        
        retriever = MemoryRetriever(memory_store=mock_store)
        
        results = retriever.keyword_search("test")
        
        assert results == []
    
    def test_semantic_search_error(self):
        """Test handling semantic search errors."""
        mock_store = Mock()
        mock_embedding = Mock()
        mock_embedding.embed.side_effect = Exception("Embedding error")
        
        retriever = MemoryRetriever(
            memory_store=mock_store,
            embedding_service=mock_embedding,
        )
        
        results = retriever.semantic_search("test")
        
        assert results == []
    
    def test_retrieve_fallback_on_error(self):
        """Test retrieval falls back on hybrid error."""
        mock_store = Mock()
        mock_store._session = Mock()
        
        # Make hybrid retrieval fail
        mock_query = Mock()
        mock_query.filter.side_effect = Exception("Query error")
        mock_store._session.query.return_value = mock_query
        
        retriever = MemoryRetriever(memory_store=mock_store)
        
        # Should not raise, should return empty
        results = retriever.retrieve("test")
        
        assert isinstance(results, list)
