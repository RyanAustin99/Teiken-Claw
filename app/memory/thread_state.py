"""
Thread state management for Teiken Claw.

This module provides thread tracking and session management functionality,
including:
- Current thread tracking per session
- Thread history management
- Session statistics
- Thread creation and switching
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from app.memory.store import MemoryStore


class ThreadState:
    """Thread state management for tracking conversation threads."""
    
    def __init__(self):
        self.store = MemoryStore()
        self._thread_cache = {}
        self._session_cache = {}
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def get_current_thread(self, session_id: int) -> Optional[int]:
        """Get the current thread ID for a session."""
        # Check cache first
        if session_id in self._thread_cache:
            return self._thread_cache[session_id]
        
        # Get from database
        session = self.store.get_session(session_id)
        if session and session.metadata:
            current_thread_id = session.metadata.get("current_thread_id")
            if current_thread_id:
                self._thread_cache[session_id] = current_thread_id
                return current_thread_id
        
        return None
    
    def set_current_thread(self, session_id: int, thread_id: int) -> bool:
        """Set the current thread for a session."""
        session = self.store.get_session(session_id)
        if session:
            if not session.metadata:
                session.metadata = {}
            session.metadata["current_thread_id"] = thread_id
            
            # Update session to refresh cache
            self.store.update_session(session_id, {"metadata": session.metadata})
            
            # Update cache
            self._thread_cache[session_id] = thread_id
            return True
        return False
    
    def create_new_thread(self, session_id: int, metadata: Optional[Dict] = None) -> int:
        """Create a new thread and set it as current."""
        # Create the thread
        thread = self.store.create_thread(session_id, metadata)
        
        # Set as current thread
        self.set_current_thread(session_id, thread.id)
        
        return thread.id
    
    def get_thread_history(self, session_id: int) -> List[Dict]:
        """Get thread history for a session."""
        threads = self.store._session.query(Thread).filter(Thread.session_id == session_id).all()
        
        history = []
        for thread in threads:
            history.append({
                "thread_id": thread.id,
                "created_at": thread.created_at,
                "summary": thread.summary,
                "message_count": self.store._session.query(Thread).filter(Thread.id == thread.id).count()
            })
        
        return history
    
    def get_all_sessions(self) -> List[Dict]:
        """Get all sessions."""
        sessions = self.store._session.query(Session).all()
        
        session_list = []
        for session in sessions:
            session_list.append({
                "session_id": session.id,
                "chat_id": session.chat_id,
                "mode": session.mode,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "current_thread_id": self.get_current_thread(session.id)
            })
        
        return session_list
    
    def get_session_stats(self, session_id: int) -> Dict:
        """Get statistics for a session."""
        session = self.store.get_session(session_id)
        if not session:
            return {}
        
        # Get thread count
        thread_count = self.store._session.query(Thread).filter(Thread.session_id == session_id).count()
        
        # Get message count
        message_count = self.store._session.query(SessionMessage).join(Thread).filter(Thread.session_id == session_id).count()
        
        # Get memory count
        memory_count = self.store._session.query(MemoryRecord).filter(MemoryRecord.scope == "session").count()
        
        return {
            "session_id": session.id,
            "chat_id": session.chat_id,
            "mode": session.mode,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "thread_count": thread_count,
            "message_count": message_count,
            "memory_count": memory_count,
            "current_thread_id": self.get_current_thread(session.id)
        }
    
    # =========================================================================
    # Thread Management
    # =========================================================================
    
    def switch_thread(self, session_id: int, thread_id: int) -> bool:
        """Switch to an existing thread."""
        # Verify thread exists and belongs to session
        thread = self.store.get_thread(thread_id)
        if thread and thread.session_id == session_id:
            return self.set_current_thread(session_id, thread_id)
        return False
    
    def close_thread(self, session_id: int, thread_id: int) -> bool:
        """Close a thread (mark as completed)."""
        thread = self.store.get_thread(thread_id)
        if thread and thread.session_id == session_id:
            # Update thread summary with completion
            thread.summary = "Thread completed"
            self.store.update_thread(thread_id, {"summary": thread.summary})
            return True
        return False
    
    def get_thread_context(self, thread_id: int, max_messages: int = 20) -> Dict:
        """Get context for a thread."""
        thread = self.store.get_thread(thread_id)
        if not thread:
            return {}
        
        # Get recent messages
        messages = self.store.get_messages_by_thread(thread_id, limit=max_messages)
        
        # Format messages for context
        formatted_messages = []
        for message in messages:
            formatted_messages.append({
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at
            })
        
        return {
            "thread_id": thread.id,
            "session_id": thread.session_id,
            "created_at": thread.created_at,
            "summary": thread.summary,
            "messages": formatted_messages,
            "message_count": len(messages)
        }
    
    # =========================================================================
    # Cache Management
    # =========================================================================
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._thread_cache.clear()
        self._session_cache.clear()
    
    def invalidate_session_cache(self, session_id: int) -> None:
        """Invalidate cache for a specific session."""
        if session_id in self._thread_cache:
            del self._thread_cache[session_id]
        if session_id in self._session_cache:
            del self._session_cache[session_id]
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def is_thread_active(self, session_id: int, thread_id: int) -> bool:
        """Check if a thread is the current active thread."""
        current_thread_id = self.get_current_thread(session_id)
        return current_thread_id == thread_id
    
    def get_inactive_threads(self, session_id: int, inactivity_threshold: int = 30) -> List[int]:
        """Get threads that have been inactive for a given threshold."""
        threshold_time = datetime.now() - timedelta(minutes=inactivity_threshold)
        
        inactive_threads = []
        threads = self.store._session.query(Thread).filter(Thread.session_id == session_id).all()
        
        for thread in threads:
            # Check if thread has recent messages
            recent_message = (
                self.store._session.query(SessionMessage)
                .filter(SessionMessage.thread_id == thread.id)
                .filter(SessionMessage.created_at > threshold_time)
                .first()
            )
            
            if not recent_message:
                inactive_threads.append(thread.id)
        
        return inactive_threads
    
    def cleanup_inactive_threads(self, session_id: int, inactivity_threshold: int = 30) -> int:
        """Cleanup inactive threads."""
        inactive_threads = self.get_inactive_threads(session_id, inactivity_threshold)
        
        for thread_id in inactive_threads:
            self.close_thread(session_id, thread_id)
        
        return len(inactive_threads)