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
from app.memory.thread_store import ThreadStore
from app.memory.message_store import MessageStore
from app.memory.memory_store_v15 import MemoryStoreV15
from app.memory.audit_store import MemoryAuditStore
from app.memory.audit import MemoryAuditLogger
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
from app.memory.extractor import (
    MemoryExtractor,
    get_memory_extractor,
    set_memory_extractor,
)
from app.memory.secret_filter import looks_like_secret

__all__ = [
    # Store
    "MemoryStore",
    "get_memory_store",
    "set_memory_store",
    "ThreadStore",
    "MessageStore",
    "MemoryStoreV15",
    "MemoryAuditStore",
    "MemoryAuditLogger",
    # Thread State
    "ThreadState",
    "get_thread_state",
    "set_thread_state",
    "MemoryExtractor",
    "get_memory_extractor",
    "set_memory_extractor",
    "looks_like_secret",
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
