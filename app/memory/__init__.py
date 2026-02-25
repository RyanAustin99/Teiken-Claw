# Memory package
"""
Memory module for Teiken Claw.

Contains memory management and state persistence, including:
- Memory store (CRUD operations)
- Thread state management
- Memory extraction rules
- LLM-based memory extraction
- Memory deduplication
- Embedding generation and management
- Hybrid retrieval system
"""

from app.memory.store import (
    MemoryStore,
    get_memory_store,
    set_memory_store,
)
from app.memory.thread_state import (
    ThreadState,
    get_thread_state,
    set_thread_state,
)
from app.memory.extraction_rules import (
    MemoryExtractionRules,
    get_extraction_rules,
    set_extraction_rules,
)
from app.memory.extractor_llm import (
    LLMMemoryExtractor,
    ExtractionConfig,
    ExtractionResult,
    ExtractedMemory,
    get_llm_extractor,
    set_llm_extractor,
    VALID_MEMORY_TYPES,
    VALID_SCOPES,
)
from app.memory.dedupe import (
    MemoryDeduplicator,
    DedupeConfig,
    get_deduplicator,
    set_deduplicator,
)
from app.memory.embeddings import (
    EmbeddingService,
    EmbeddingConfig,
    get_embedding_service,
    set_embedding_service,
)
from app.memory.retrieval import (
    MemoryRetriever,
    RetrievalConfig,
    RetrievalResult,
    get_retriever,
    set_retriever,
)

__all__ = [
    # Store
    "MemoryStore",
    "get_memory_store",
    "set_memory_store",
    # Thread State
    "ThreadState",
    "get_thread_state",
    "set_thread_state",
    # Extraction Rules
    "MemoryExtractionRules",
    "get_extraction_rules",
    "set_extraction_rules",
    # LLM Extractor
    "LLMMemoryExtractor",
    "ExtractionConfig",
    "ExtractionResult",
    "ExtractedMemory",
    "get_llm_extractor",
    "set_llm_extractor",
    "VALID_MEMORY_TYPES",
    "VALID_SCOPES",
    # Deduplication
    "MemoryDeduplicator",
    "DedupeConfig",
    "get_deduplicator",
    "set_deduplicator",
    # Embeddings
    "EmbeddingService",
    "EmbeddingConfig",
    "get_embedding_service",
    "set_embedding_service",
    # Retrieval
    "MemoryRetriever",
    "RetrievalConfig",
    "RetrievalResult",
    "get_retriever",
    "set_retriever",
]
