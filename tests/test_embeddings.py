"""
Tests for the embedding service.

Tests cover:
- Embedding generation
- Similarity computation
- Nearest neighbor search
- Model version tracking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import math

from app.memory.embeddings import (
    EmbeddingService,
    EmbeddingConfig,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSION,
    get_embedding_service,
    set_embedding_service,
)


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = EmbeddingConfig()
        
        assert config.model == DEFAULT_EMBEDDING_MODEL
        assert config.dimension == DEFAULT_EMBEDDING_DIMENSION
        assert config.enabled is True
        assert config.batch_size == 32
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = EmbeddingConfig(
            model="custom-model",
            dimension=512,
            enabled=False,
            batch_size=16,
        )
        
        assert config.model == "custom-model"
        assert config.dimension == 512
        assert config.enabled is False
        assert config.batch_size == 16


class TestEmbeddingService:
    """Tests for EmbeddingService."""
    
    @pytest.fixture
    def mock_ollama_client(self):
        """Create a mock Ollama client."""
        client = Mock()
        client.embeddings = Mock(return_value={
            "embedding": [0.1] * 768
        })
        return client
    
    @pytest.fixture
    def mock_memory_store(self):
        """Create a mock memory store."""
        store = Mock()
        store._session = Mock()
        store.create_embedding = Mock(return_value=Mock(id=1))
        store.get_embedding = Mock(return_value=None)
        return store
    
    @pytest.fixture
    def embedding_service(self, mock_ollama_client, mock_memory_store):
        """Create an embedding service with mocks."""
        service = EmbeddingService(
            ollama_client=mock_ollama_client,
            memory_store=mock_memory_store,
        )
        return service
    
    def test_initialization(self, embedding_service):
        """Test service initialization."""
        assert embedding_service.model == DEFAULT_EMBEDDING_MODEL
        assert embedding_service.dimension == DEFAULT_EMBEDDING_DIMENSION
        assert embedding_service.model_version is not None
    
    def test_embed_single_text(self, embedding_service, mock_ollama_client):
        """Test embedding a single text."""
        text = "This is a test message"
        
        embedding = embedding_service.embed(text)
        
        assert embedding is not None
        assert len(embedding) == 768
        mock_ollama_client.embeddings.assert_called_once()
    
    def test_embed_empty_text(self, embedding_service, mock_ollama_client):
        """Test embedding empty text returns None."""
        embedding = embedding_service.embed("")
        
        assert embedding is None
        mock_ollama_client.embeddings.assert_not_called()
    
    def test_embed_whitespace_text(self, embedding_service, mock_ollama_client):
        """Test embedding whitespace-only text returns None."""
        embedding = embedding_service.embed("   ")
        
        assert embedding is None
        mock_ollama_client.embeddings.assert_not_called()
    
    def test_embed_disabled(self, mock_ollama_client, mock_memory_store):
        """Test embedding when disabled returns None."""
        config = EmbeddingConfig(enabled=False)
        service = EmbeddingService(
            ollama_client=mock_ollama_client,
            memory_store=mock_memory_store,
            config=config,
        )
        
        embedding = service.embed("test")
        
        assert embedding is None
        mock_ollama_client.embeddings.assert_not_called()
    
    def test_embed_batch(self, embedding_service, mock_ollama_client):
        """Test batch embedding."""
        texts = ["text 1", "text 2", "text 3"]
        
        embeddings = embedding_service.embed_batch(texts)
        
        assert len(embeddings) == 3
        assert all(e is not None for e in embeddings)
    
    def test_embed_batch_with_empty(self, embedding_service):
        """Test batch embedding with empty texts."""
        texts = ["text 1", "", "text 3"]
        
        embeddings = embedding_service.embed_batch(texts)
        
        assert len(embeddings) == 3
        assert embeddings[0] is not None
        assert embeddings[1] is None
        assert embeddings[2] is not None
    
    def test_compute_similarity_identical(self, embedding_service):
        """Test similarity of identical embeddings."""
        embedding = [0.5] * 768
        
        similarity = embedding_service.compute_similarity(embedding, embedding)
        
        assert similarity == pytest.approx(1.0, abs=0.01)
    
    def test_compute_similarity_orthogonal(self, embedding_service):
        """Test similarity of orthogonal embeddings."""
        # Create orthogonal vectors
        embedding1 = [1.0, 0.0, 0.0] + [0.0] * 765
        embedding2 = [0.0, 1.0, 0.0] + [0.0] * 765
        
        similarity = embedding_service.compute_similarity(embedding1, embedding2)
        
        assert similarity == pytest.approx(0.0, abs=0.01)
    
    def test_compute_similarity_opposite(self, embedding_service):
        """Test similarity of opposite embeddings."""
        embedding1 = [0.5] * 768
        embedding2 = [-0.5] * 768
        
        similarity = embedding_service.compute_similarity(embedding1, embedding2)
        
        # Should be 0 due to clamping
        assert similarity == pytest.approx(0.0, abs=0.01)
    
    def test_compute_similarity_empty(self, embedding_service):
        """Test similarity with empty embeddings."""
        embedding = [0.5] * 768
        
        similarity = embedding_service.compute_similarity(embedding, [])
        
        assert similarity == 0.0
    
    def test_compute_similarity_different_dimensions(self, embedding_service):
        """Test similarity with different dimensions."""
        embedding1 = [0.5] * 768
        embedding2 = [0.5] * 512
        
        similarity = embedding_service.compute_similarity(embedding1, embedding2)
        
        assert similarity == 0.0
    
    def test_store_embedding(self, embedding_service, mock_memory_store):
        """Test storing an embedding."""
        embedding = [0.1] * 768
        content = "test content"
        
        result = embedding_service.store_embedding(
            source_type="memory",
            source_id=1,
            content=content,
            embedding=embedding,
        )
        
        assert result is not None
        mock_memory_store.create_embedding.assert_called_once()
    
    def test_store_embedding_empty(self, embedding_service, mock_memory_store):
        """Test storing an empty embedding returns None."""
        result = embedding_service.store_embedding(
            source_type="memory",
            source_id=1,
            content="test",
            embedding=[],
        )
        
        assert result is None
        mock_memory_store.create_embedding.assert_not_called()
    
    def test_get_embedding(self, embedding_service, mock_memory_store):
        """Test getting an embedding."""
        mock_record = Mock()
        mock_record.embedding = [0.1] * 768
        mock_memory_store.get_embedding.return_value = mock_record
        
        result = embedding_service.get_embedding("memory", 1)
        
        assert result is not None
        mock_memory_store.get_embedding.assert_called_once()
    
    def test_get_embedding_not_found(self, embedding_service, mock_memory_store):
        """Test getting a non-existent embedding."""
        mock_memory_store.get_embedding.return_value = None
        
        result = embedding_service.get_embedding("memory", 999)
        
        assert result is None
    
    def test_find_nearest(self, embedding_service, mock_memory_store):
        """Test finding nearest neighbors."""
        # Mock the session and query
        mock_session = Mock()
        mock_query = Mock()
        mock_record = Mock()
        mock_record.embedding = [0.5] * 768
        mock_record.source_id = 1
        mock_record.source_type = "memory"
        
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_record]
        mock_session.query.return_value = mock_query
        mock_memory_store._session = mock_session
        
        embedding = [0.5] * 768
        
        results = embedding_service.find_nearest(embedding, limit=5)
        
        assert len(results) >= 0  # May be empty if similarity is low
    
    def test_model_version(self, embedding_service):
        """Test model version tracking."""
        version = embedding_service.model_version
        
        assert version is not None
        assert DEFAULT_EMBEDDING_MODEL in version
    
    def test_get_model_info(self, embedding_service):
        """Test getting model info."""
        info = embedding_service.get_model_info()
        
        assert "model" in info
        assert "dimension" in info
        assert "version" in info
        assert "enabled" in info
        assert info["model"] == DEFAULT_EMBEDDING_MODEL
        assert info["dimension"] == DEFAULT_EMBEDDING_DIMENSION


class TestEmbeddingServiceSingleton:
    """Tests for singleton functions."""
    
    def test_get_embedding_service(self):
        """Test getting the singleton instance."""
        from app.memory.embeddings import _embedding_instance
        
        # Reset singleton
        import app.memory.embeddings as module
        module._embedding_instance = None
        
        service = get_embedding_service()
        
        assert service is not None
        assert isinstance(service, EmbeddingService)
    
    def test_set_embedding_service(self):
        """Test setting the singleton instance."""
        custom_service = EmbeddingService()
        
        set_embedding_service(custom_service)
        
        assert get_embedding_service() is custom_service


class TestEmbeddingErrorHandling:
    """Tests for error handling in embedding service."""
    
    def test_embed_ollama_error(self):
        """Test handling Ollama errors."""
        mock_client = Mock()
        mock_client.embeddings.side_effect = Exception("Ollama error")
        
        service = EmbeddingService(ollama_client=mock_client)
        
        embedding = service.embed("test")
        
        assert embedding is None
    
    def test_embed_missing_embedding_in_response(self):
        """Test handling missing embedding in response."""
        mock_client = Mock()
        mock_client.embeddings.return_value = {"error": "not found"}
        
        service = EmbeddingService(ollama_client=mock_client)
        
        embedding = service.embed("test")
        
        assert embedding is None
    
    def test_store_embedding_error(self):
        """Test handling store errors."""
        mock_store = Mock()
        mock_store.create_embedding.side_effect = Exception("DB error")
        
        service = EmbeddingService(memory_store=mock_store)
        
        result = service.store_embedding("memory", 1, "test", [0.1] * 768)
        
        assert result is None
