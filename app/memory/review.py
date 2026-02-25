"""
Memory review commands for Teiken Claw.

This module provides:
- Memory listing and searching
- Memory editing and deletion
- Memory pinning and unpinning
- Auto-memory control
- Memory policy display
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from app.memory.store import MemoryStore


class MemoryReview:
    """Memory review and management commands."""
    
    def __init__(self):
        self.store = MemoryStore()
    
    # =========================================================================
    # Memory Listing
    # =========================================================================
    
    def list_memories(
        self, 
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """List memories with filtering."""
        memories = self.store.list_memories(
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=limit,
            offset=offset
        )
        
        # Format for display
        return [{
            "id": memory.id,
            "type": memory.memory_type,
            "content": memory.content,
            "tags": memory.tags,
            "scope": memory.scope,
            "confidence": memory.confidence,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "audit_count": len(self.store.get_memory_audit_trail(memory.id, limit=1))
        } for memory in memories]
    
    def search_memories(
        self, 
        query: str, 
        scope: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search memories."""
        memories = self.store.search_memories(
            query=query,
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=limit
        )
        
        # Format for display
        return [{
            "id": memory.id,
            "type": memory.memory_type,
            "content": memory.content,
            "tags": memory.tags,
            "scope": memory.scope,
            "confidence": memory.confidence,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "relevance": self._calculate_relevance(memory.content, query)
        } for memory in memories]
    
    def get_memory(self, memory_id: int) -> Optional[Dict]:
        """Get detailed memory information."""
        memory = self.store.get_memory(memory_id)
        if not memory:
            return None
        
        return {
            "id": memory.id,
            "type": memory.memory_type,
            "content": memory.content,
            "tags": memory.tags,
            "scope": memory.scope,
            "confidence": memory.confidence,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "audit_trail": self._format_audit_trail(memory_id),
            "similar_memories": self._find_similar_memories(memory_id)
        }
    
    # =========================================================================
    # Memory Editing
    # =========================================================================
    
    def edit_memory(self, memory_id: int, updates: Dict[str, Any]) -> bool:
        """Edit a memory record."""
        # Validate updates
        allowed_fields = {"content", "tags", "scope", "confidence"}
        update_data = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not update_data:
            return False
        
        # Update memory
        memory = self.store.update_memory(memory_id, update_data)
        if memory:
            # Create audit record
            self.store.audit_memory(memory_id, "edited", "Manual edit")
            return True
        
        return False
    
    def delete_memory(self, memory_id: int, reason: Optional[str] = None) -> bool:
        """Delete a memory record."""
        return self.store.delete_memory(memory_id, reason)
    
    def pin_memory(self, memory_id: int) -> bool:
        """Pin a memory (prevent auto-deletion)."""
        memory = self.store.get_memory(memory_id)
        if memory:
            # Add special tag to indicate pinned status
            tags = memory.tags or []
            if "pinned" not in tags:
                tags.append("pinned")
                self.store.update_memory(memory_id, {"tags": tags})
                self.store.audit_memory(memory_id, "pinned", "Manual pin")
                return True
        return False
    
    def unpin_memory(self, memory_id: int) -> bool:
        """Unpin a memory."""
        memory = self.store.get_memory(memory_id)
        if memory:
            # Remove pinned tag
            tags = memory.tags or []
            if "pinned" in tags:
                tags.remove("pinned")
                self.store.update_memory(memory_id, {"tags": tags})
                self.store.audit_memory(memory_id, "unpinned", "Manual unpin")
                return True
        return False
    
    # =========================================================================
    # Auto-Memory Control
    # =========================================================================
    
    def pause_auto_memory(self) -> bool:
        """Pause auto-memory creation."""
        # Set control state to pause auto-memory
        self.store.set_control_state("auto_memory_paused", True)
        return True
    
    def resume_auto_memory(self) -> bool:
        """Resume auto-memory creation."""
        # Clear control state to resume auto-memory
        self.store.set_control_state("auto_memory_paused", False)
        return True
    
    def get_auto_memory_status(self) -> Dict:
        """Get auto-memory status."""
        paused = self.store.get_control_state("auto_memory_paused")
        return {
            "paused": paused,
            "can_resume": paused is not None,
            "last_auto_memory": self._get_last_auto_memory_time()
        }
    
    # =========================================================================
    # Memory Policy
    # =========================================================================
    
    def get_memory_policy(self) -> Dict:
        """Get memory system policy."""
        return {
            "retention_period": "1 year",
            "auto_deletion": "enabled",
            "pinned_protection": "enabled",
            "sensitive_content_filter": "enabled",
            "allowed_categories": list(self._get_allowed_categories()),
            "max_memory_size": "10,000 records",
            "max_session_size": "1,000 records",
            "audit_trail": "enabled",
            "data_portability": "enabled",
            "right_to_be_forgotten": "enabled"
        }
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _calculate_relevance(self, content: str, query: str) -> float:
        """Calculate relevance score for search."""
        # Simple relevance calculation
        content_lower = content.lower()
        query_lower = query.lower()
        
        # Exact match
        if query_lower in content_lower:
            return 1.0
        
        # Partial match
        words = query_lower.split()
        matches = sum(1 for word in words if word in content_lower)
        return matches / len(words) if words else 0.0
    
    def _format_audit_trail(self, memory_id: int) -> List[Dict]:
        """Format audit trail for display."""
        audits = self.store.get_memory_audit_trail(memory_id, limit=20)
        return [{
            "action": audit.action,
            "reason": audit.reason,
            "timestamp": audit.created_at
        } for audit in audits]
    
    def _find_similar_memories(self, memory_id: int) -> List[Dict]:
        """Find memories similar to the given memory."""
        memory = self.store.get_memory(memory_id)
        if not memory:
            return []
        
        # Find memories with same type and similar content
        similar = []
        
        # Get memories of same type
        same_type = self.store.get_memories_by_type(memory.memory_type, limit=20)
        
        for other in same_type:
            if other.id != memory_id:
                similarity = self._calculate_content_similarity(memory.content, other.content)
                if similarity > 0.3:  # Threshold for similarity
                    similar.append({
                        "id": other.id,
                        "type": other.memory_type,
                        "content_preview": other.content[:100] + "..." if len(other.content) > 100 else other.content,
                        "similarity": similarity,
                        "created_at": other.created_at
                    })
        
        # Sort by similarity
        similar.sort(key=lambda x: x["similarity"], reverse=True)
        return similar[:5]  # Return top 5 similar memories
    
    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate content similarity."""
        # Simple similarity - count common words
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        common = words1 & words2
        return len(common) / max(len(words1), len(words2))
    
    def _get_last_auto_memory_time(self) -> Optional[datetime]:
        """Get time of last auto-memory creation."""
        # Find most recent memory created by auto-memory
        # This is a placeholder - would need metadata to track auto vs manual
        return None
    
    def _get_allowed_categories(self) -> set:
        """Get allowed memory categories."""
        # This would be configurable in a real system
        return {
            "preference", "project", "workflow", "environment", 
            "schedule_pattern", "fact", "note"
        }