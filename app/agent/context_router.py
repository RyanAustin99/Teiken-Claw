"""
Context router for topic detection and thread management.

This module provides:
- Topic similarity detection using semantic analysis
- Thread creation logic based on topic changes
- Command detection for thread management
- Inactivity-based thread switching
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import re

from app.memory.store import MemoryStore
from app.memory.thread_state import ThreadState


class ContextRouter:
    """Context router for managing conversation topics and threads."""
    
    def __init__(self):
        self.store = MemoryStore()
        self.thread_state = ThreadState()
        self._similarity_threshold = 0.7  # Default similarity threshold
        self._inactivity_timeout = 30  # Minutes
        self._max_thread_messages = 100
    
    # =========================================================================
    # Thread Management
    # =========================================================================
    
    def should_create_new_thread(
        self, 
        current_thread_id: Optional[int], 
        new_message: str,
        session_id: int
    ) -> bool:
        """Determine if a new thread should be created."""
        # Check for explicit thread commands
        if self._is_thread_command(new_message):
            return True
        
        # Check for mode changes
        if self._is_mode_change(new_message):
            return True
        
        # Check for inactivity timeout
        if self._is_inactive_timeout(session_id):
            return True
        
        # Check topic similarity
        if current_thread_id:
            thread_context = self.thread_state.get_thread_context(current_thread_id)
            if thread_context:
                similarity = self.get_topic_similarity(thread_context, new_message)
                if similarity < self._similarity_threshold:
                    return True
        
        return False
    
    def create_new_thread_if_needed(
        self, 
        session_id: int, 
        current_thread_id: Optional[int], 
        new_message: str
    ) -> Optional[int]:
        """Create a new thread if needed based on context."""
        if self.should_create_new_thread(current_thread_id, new_message, session_id):
            # Create new thread
            new_thread_id = self.thread_state.create_new_thread(session_id)
            
            # Log the thread creation
            self.store.create_event(
                event_type="thread_created",
                event_data={
                    "session_id": session_id,
                    "old_thread_id": current_thread_id,
                    "new_thread_id": new_thread_id,
                    "reason": "topic_change",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            return new_thread_id
        
        return current_thread_id
    
    def get_thread_context(self, thread_id: int, max_messages: int = 20) -> Dict:
        """Get context for a thread."""
        return self.thread_state.get_thread_context(thread_id, max_messages)
    
    # =========================================================================
    # Topic Similarity
    # =========================================================================
    
    def get_topic_similarity(self, thread_context: Dict, new_message: str) -> float:
        """Calculate topic similarity between thread context and new message."""
        # Placeholder implementation - in Phase 7 this will use embeddings
        # For now, use simple keyword matching
        
        # Extract keywords from thread context
        thread_keywords = self._extract_keywords(thread_context)
        
        # Extract keywords from new message
        message_keywords = self._extract_keywords_from_text(new_message)
        
        # Calculate similarity
        if not thread_keywords or not message_keywords:
            return 0.0
        
        common_keywords = set(thread_keywords) & set(message_keywords)
        similarity = len(common_keywords) / max(len(thread_keywords), len(message_keywords))
        
        return similarity
    
    def _extract_keywords(self, context: Dict) -> List[str]:
        """Extract keywords from thread context."""
        keywords = []
        
        # Extract from messages
        for message in context.get("messages", []):
            keywords.extend(self._extract_keywords_from_text(message["content"]))
        
        # Extract from summary
        if context.get("summary"):
            keywords.extend(self._extract_keywords_from_text(context["summary"]))
        
        return list(set(keywords))  # Remove duplicates
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """Extract keywords from text."""
        # Simple keyword extraction - in Phase 7 this will be more sophisticated
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter out common words
        common_words = {'the', 'and', 'is', 'in', 'it', 'to', 'of', 'a', 'with', 'for'}
        keywords = [word for word in words if word not in common_words and len(word) > 3]
        
        return keywords
    
    # =========================================================================
    # Command Detection
    # =========================================================================
    
    def _is_thread_command(self, message: str) -> bool:
        """Check if message is a thread command."""
        thread_commands = [
            r'^/thread new$', r'^/thread create$', r'^/new thread$', r'^/create thread$',
            r'^/thread switch$', r'^/switch thread$', r'^/thread change$', r'^/change thread$'
        ]
        
        for command in thread_commands:
            if re.match(command, message.strip(), re.IGNORECASE):
                return True
        
        return False
    
    def _is_mode_change(self, message: str) -> bool:
        """Check if message indicates a mode change."""
        mode_change_patterns = [
            r'^/mode\s+', r'^mode\s+', r'^switch to\s+', r'^change to\s+'
        ]
        
        for pattern in mode_change_patterns:
            if re.match(pattern, message.strip(), re.IGNORECASE):
                return True
        
        return False
    
    # =========================================================================
    # Inactivity Detection
    # =========================================================================
    
    def _is_inactive_timeout(self, session_id: int) -> bool:
        """Check if session has been inactive for too long."""
        current_thread_id = self.thread_state.get_current_thread(session_id)
        if not current_thread_id:
            return False
        
        # Get last message time
        last_message = (
            self.store._session.query(SessionMessage)
            .filter(SessionMessage.thread_id == current_thread_id)
            .order_by(SessionMessage.created_at.desc())
            .first()
        )
        
        if last_message:
            inactivity_time = datetime.now() - last_message.created_at
            return inactivity_time > timedelta(minutes=self._inactivity_timeout)
        
        return False
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    def set_similarity_threshold(self, threshold: float) -> None:
        """Set the similarity threshold."""
        self._similarity_threshold = max(0.0, min(1.0, threshold))
    
    def set_inactivity_timeout(self, minutes: int) -> None:
        """Set the inactivity timeout."""
        self._inactivity_timeout = max(1, minutes)
    
    def set_max_thread_messages(self, max_messages: int) -> None:
        """Set the maximum messages per thread."""
        self._max_thread_messages = max(10, max_messages)