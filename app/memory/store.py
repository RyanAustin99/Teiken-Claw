"""
Memory store implementation for Teiken Claw.

This module provides CRUD operations for the memory system, including:
- Session and thread management
- Message persistence
- Memory record operations
- Search and retrieval functionality
- Audit trail management
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session as SQLAlchemySession

from app.db.session import get_db_session
from app.memory.models import (
    Session, Thread, SessionMessage, ThreadSummary, 
    MemoryRecord, MemoryAudit, EmbeddingRecord,
    ControlState, IdempotencyKey, AppEvent
)


class MemoryStore:
    """Memory store for managing all memory-related operations."""
    
    def __init__(self):
        self._session = get_db_session()
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def create_session(self, chat_id: str, mode: str = "default", metadata: Optional[Dict] = None) -> Session:
        """Create a new session."""
        session = Session(
            chat_id=chat_id,
            mode=mode,
            metadata=metadata or {}
        )
        self._session.add(session)
        self._session.commit()
        self._session.refresh(session)
        return session
    
    def get_session(self, session_id: int) -> Optional[Session]:
        """Get a session by ID."""
        return self._session.query(Session).filter(Session.id == session_id).first()
    
    def get_session_by_chat_id(self, chat_id: str) -> Optional[Session]:
        """Get a session by chat ID."""
        return self._session.query(Session).filter(Session.chat_id == chat_id).first()
    
    def update_session(self, session_id: int, updates: Dict[str, Any]) -> Optional[Session]:
        """Update a session."""
        session = self.get_session(session_id)
        if session:
            for key, value in updates.items():
                setattr(session, key, value)
            self._session.commit()
            self._session.refresh(session)
        return session
    
    def delete_session(self, session_id: int, reason: Optional[str] = None) -> bool:
        """Delete a session."""
        session = self.get_session(session_id)
        if session:
            self._session.delete(session)
            self._session.commit()
            return True
        return False
    
    # =========================================================================
    # Thread Management
    # =========================================================================
    
    def create_thread(self, session_id: int, metadata: Optional[Dict] = None) -> Thread:
        """Create a new thread."""
        thread = Thread(
            session_id=session_id,
            metadata=metadata or {}
        )
        self._session.add(thread)
        self._session.commit()
        self._session.refresh(thread)
        return thread
    
    def get_thread(self, thread_id: int) -> Optional[Thread]:
        """Get a thread by ID."""
        return self._session.query(Thread).filter(Thread.id == thread_id).first()
    
    def update_thread(self, thread_id: int, updates: Dict[str, Any]) -> Optional[Thread]:
        """Update a thread."""
        thread = self.get_thread(thread_id)
        if thread:
            for key, value in updates.items():
                setattr(thread, key, value)
            self._session.commit()
            self._session.refresh(thread)
        return thread
    
    def delete_thread(self, thread_id: int, reason: Optional[str] = None) -> bool:
        """Delete a thread."""
        thread = self.get_thread(thread_id)
        if thread:
            self._session.delete(thread)
            self._session.commit()
            return True
        return False
    
    # =========================================================================
    # Message Management
    # =========================================================================
    
    def append_message(
        self, 
        thread_id: int, 
        role: str, 
        content: str, 
        metadata: Optional[Dict] = None
    ) -> SessionMessage:
        """Append a message to a thread."""
        message = SessionMessage(
            thread_id=thread_id,
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._session.add(message)
        self._session.commit()
        self._session.refresh(message)
        return message
    
    def get_messages_by_thread(
        self, 
        thread_id: int, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[SessionMessage]:
        """Get messages for a thread."""
        return (
            self._session.query(SessionMessage)
            .filter(SessionMessage.thread_id == thread_id)
            .order_by(SessionMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    
    def get_recent_messages(
        self, 
        limit: int = 100, 
        chat_id: Optional[str] = None
    ) -> List[SessionMessage]:
        """Get recent messages across all threads."""
        query = self._session.query(SessionMessage)
        
        if chat_id:
            query = query.join(Thread).join(Session)
            query = query.filter(Session.chat_id == chat_id)
        
        return (
            query.order_by(SessionMessage.created_at.desc())
            .limit(limit)
            .all()
        )
    
    # =========================================================================
    # Memory Management
    # =========================================================================
    
    def create_memory(
        self, 
        memory_type: str, 
        content: str, 
        tags: Optional[List[str]] = None,
        scope: str = "user",
        confidence: float = 0.0,
        metadata: Optional[Dict] = None,
        generate_embedding: bool = True
    ) -> MemoryRecord:
        """
        Create a new memory record.
        
        Args:
            memory_type: Type of memory (preference, project, workflow, etc.)
            content: Memory content
            tags: Optional list of tags
            scope: Memory scope (user, global, project, thread)
            confidence: Confidence score (0.0-1.0)
            metadata: Optional metadata dictionary
            generate_embedding: Whether to generate embedding for the memory
            
        Returns:
            Created MemoryRecord
        """
        memory = MemoryRecord(
            memory_type=memory_type,
            content=content,
            tags=tags,
            scope=scope,
            confidence=confidence,
            metadata=metadata or {}
        )
        self._session.add(memory)
        self._session.commit()
        self._session.refresh(memory)
        
        # Create audit record
        self.audit_memory(memory.id, "created", "Initial creation")
        
        # Generate embedding if requested
        if generate_embedding:
            self._generate_memory_embedding(memory)
        
        return memory
    
    def _generate_memory_embedding(self, memory: MemoryRecord) -> bool:
        """Generate and store embedding for a memory record."""
        try:
            from app.memory.embeddings import get_embedding_service
            embedding_service = get_embedding_service()
            
            # Generate embedding
            embedding = embedding_service.embed(memory.content)
            
            if embedding:
                # Store embedding
                embedding_service.store_embedding(
                    source_type="memory",
                    source_id=memory.id,
                    content=memory.content,
                    embedding=embedding,
                )
                return True
            
        except Exception as e:
            # Log but don't fail memory creation
            import logging
            logging.getLogger(__name__).warning(f"Failed to generate embedding: {e}")
        
        return False
    
    def get_memory(self, memory_id: int) -> Optional[MemoryRecord]:
        """Get a memory record by ID."""
        return self._session.query(MemoryRecord).filter(MemoryRecord.id == memory_id).first()
    
    def get_memories_by_type(self, memory_type: str, limit: int = 100) -> List[MemoryRecord]:
        """Get memories by type."""
        return (
            self._session.query(MemoryRecord)
            .filter(MemoryRecord.memory_type == memory_type)
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_memories_by_scope(self, scope: str, limit: int = 100) -> List[MemoryRecord]:
        """Get memories by scope."""
        return (
            self._session.query(MemoryRecord)
            .filter(MemoryRecord.scope == scope)
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_memories_by_tags(self, tags: List[str], limit: int = 100) -> List[MemoryRecord]:
        """Get memories by tags."""
        return (
            self._session.query(MemoryRecord)
            .filter(MemoryRecord.tags.overlap(tags))
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def update_memory(self, memory_id: int, updates: Dict[str, Any]) -> Optional[MemoryRecord]:
        """Update a memory record."""
        memory = self.get_memory(memory_id)
        if memory:
            for key, value in updates.items():
                setattr(memory, key, value)
            self._session.commit()
            self._session.refresh(memory)
            
            # Create audit record
            self.audit_memory(memory.id, "updated", "Manual update")
        return memory
    
    def delete_memory(self, memory_id: int, reason: Optional[str] = None) -> bool:
        """Delete a memory record."""
        memory = self.get_memory(memory_id)
        if memory:
            self._session.delete(memory)
            self._session.commit()
            
            # Create audit record
            self.audit_memory(memory_id, "deleted", reason or "Manual deletion")
            return True
        return False
    
    def list_memories(
        self, 
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[MemoryRecord]:
        """List memories with filtering."""
        query = self._session.query(MemoryRecord)
        
        if scope:
            query = query.filter(MemoryRecord.scope == scope)
        
        if memory_type:
            query = query.filter(MemoryRecord.memory_type == memory_type)
        
        if tags:
            query = query.filter(MemoryRecord.tags.overlap(tags))
        
        return (
            query.order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    
    def search_memories(
        self, 
        query: str, 
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        use_hybrid: bool = True
    ) -> List[MemoryRecord]:
        """
        Search memories using hybrid retrieval.
        
        Combines keyword search with semantic search via embeddings.
        
        Args:
            query: Search query
            scope: Optional scope filter
            memory_type: Optional memory type filter
            tags: Optional tags filter
            limit: Maximum results
            use_hybrid: Whether to use hybrid retrieval (default True)
            
        Returns:
            List of matching MemoryRecord objects
        """
        if use_hybrid:
            try:
                from app.memory.retrieval import get_retriever
                retriever = get_retriever()
                
                # Use hybrid retrieval
                results = retriever.retrieve(
                    query=query,
                    scope=scope,
                    memory_type=memory_type,
                    tags=tags,
                    limit=limit,
                )
                
                # Convert to MemoryRecord objects
                memory_ids = [r["memory_id"] for r in results]
                if not memory_ids:
                    return []
                
                # Fetch memories in order
                memories = {
                    m.id: m for m in 
                    self._session.query(MemoryRecord)
                    .filter(MemoryRecord.id.in_(memory_ids))
                    .all()
                }
                
                # Return in relevance order
                return [memories[mid] for mid in memory_ids if mid in memories]
                
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Hybrid search failed, falling back to keyword: {e}")
        
        # Fallback to keyword search
        search_query = f"%{query}%"
        
        base_query = self._session.query(MemoryRecord)
        
        if scope:
            base_query = base_query.filter(MemoryRecord.scope == scope)
        
        if memory_type:
            base_query = base_query.filter(MemoryRecord.memory_type == memory_type)
        
        if tags:
            base_query = base_query.filter(MemoryRecord.tags.overlap(tags))
        
        # Simple text search on content
        results = (
            base_query.filter(MemoryRecord.content.ilike(search_query))
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        
        return results
    
    # =========================================================================
    # Audit Trail
    # =========================================================================
    
    def audit_memory(self, memory_id: int, action: str, reason: Optional[str] = None) -> MemoryAudit:
        """Create an audit record for a memory."""
        audit = MemoryAudit(
            memory_id=memory_id,
            action=action,
            reason=reason
        )
        self._session.add(audit)
        self._session.commit()
        return audit
    
    def get_memory_audit_trail(self, memory_id: int, limit: int = 50) -> List[MemoryAudit]:
        """Get audit trail for a memory."""
        return (
            self._session.query(MemoryAudit)
            .filter(MemoryAudit.memory_id == memory_id)
            .order_by(MemoryAudit.created_at.desc())
            .limit(limit)
            .all()
        )
    
    # =========================================================================
    # Embedding Management
    # =========================================================================
    
    def create_embedding(
        self, 
        source_type: str, 
        source_id: int, 
        content_hash: str,
        embedding_model: str,
        vector_dim: int,
        embedding: List[float]
    ) -> EmbeddingRecord:
        """Create an embedding record."""
        embedding_record = EmbeddingRecord(
            source_type=source_type,
            source_id=source_id,
            content_hash=content_hash,
            embedding_model=embedding_model,
            vector_dim=vector_dim,
            embedding=embedding
        )
        self._session.add(embedding_record)
        self._session.commit()
        self._session.refresh(embedding_record)
        return embedding_record
    
    def get_embedding(
        self, 
        source_type: str, 
        source_id: int, 
        embedding_model: str
    ) -> Optional[EmbeddingRecord]:
        """Get an embedding by source."""
        return (
            self._session.query(EmbeddingRecord)
            .filter(
                EmbeddingRecord.source_type == source_type,
                EmbeddingRecord.source_id == source_id,
                EmbeddingRecord.embedding_model == embedding_model
            )
            .first()
        )
    
    # =========================================================================
    # Control State Management
    # =========================================================================
    
    def get_control_state(self, key: str) -> Optional[Dict]:
        """Get control state value."""
        state = (
            self._session.query(ControlState)
            .filter(ControlState.key == key)
            .first()
        )
        return state.value if state else None
    
    def set_control_state(self, key: str, value: Dict) -> ControlState:
        """Set control state value."""
        state = (
            self._session.query(ControlState)
            .filter(ControlState.key == key)
            .first()
        )
        
        if state:
            state.value = value
            state.updated_at = datetime.now()
        else:
            state = ControlState(key=key, value=value)
            self._session.add(state)
        
        self._session.commit()
        self._session.refresh(state)
        return state
    
    # =========================================================================
    # Idempotency Management
    # =========================================================================
    
    def create_idempotency_key(self, key: str, expires_at: datetime) -> IdempotencyKey:
        """Create an idempotency key."""
        idempotency_key = IdempotencyKey(
            key=key,
            expires_at=expires_at
        )
        self._session.add(idempotency_key)
        self._session.commit()
        self._session.refresh(idempotency_key)
        return idempotency_key
    
    def get_idempotency_key(self, key: str) -> Optional[IdempotencyKey]:
        """Get an idempotency key."""
        return (
            self._session.query(IdempotencyKey)
            .filter(ControlState.key == key)
            .first()
        )
    
    # =========================================================================
    # Event Management
    # =========================================================================
    
    def create_event(self, event_type: str, event_data: Dict) -> AppEvent:
        """Create an application event."""
        event = AppEvent(
            event_type=event_type,
            event_data=event_data
        )
        self._session.add(event)
        self._session.commit()
        self._session.refresh(event)
        return event
    
    def get_events_by_type(self, event_type: str, limit: int = 100) -> List[AppEvent]:
        """Get events by type."""
        return (
            self._session.query(AppEvent)
            .filter(AppEvent.event_type == event_type)
            .order_by(AppEvent.created_at.desc())
            .limit(limit)
            .all()
        )
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    def cleanup_old_messages(self, cutoff_days: int = 30) -> int:
        """Cleanup old messages."""
        cutoff_date = datetime.now() - timedelta(days=cutoff_days)
        
        deleted = (
            self._session.query(SessionMessage)
            .filter(SessionMessage.created_at < cutoff_date)
            .delete(synchronize_session=False)
        )
        
        self._session.commit()
        return deleted
    
    def cleanup_old_memories(self, cutoff_days: int = 365) -> int:
        """Cleanup old memories."""
        cutoff_date = datetime.now() - timedelta(days=cutoff_days)
        
        deleted = (
            self._session.query(MemoryRecord)
            .filter(
                MemoryRecord.created_at < cutoff_date,
                MemoryRecord.scope == "user"  # Only cleanup user memories, keep global
            )
            .delete(synchronize_session=False)
        )
        
        self._session.commit()
        return deleted
    
    def close(self) -> None:
        """Close the database session."""
        self._session.close()


# =============================================================================
# Global Memory Store Instance
# =============================================================================

_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    """Get or create the global memory store instance."""
    global _memory_store
    
    if _memory_store is None:
        _memory_store = MemoryStore()
    
    return _memory_store


def set_memory_store(store: MemoryStore) -> None:
    """Set the global memory store instance (for testing or DI)."""
    global _memory_store
    _memory_store = store