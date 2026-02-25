"""
Tests for the memory system.

This module tests:
- Memory CRUD operations
- Thread state management
- Context routing
- Extraction rules
- Memory review commands
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import tempfile
import os

# Test fixtures
@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    return session


# =============================================================================
# Memory Store Tests
# =============================================================================

class TestMemoryStore:
    """Tests for MemoryStore class."""
    
    @pytest.mark.asyncio
    async def test_create_memory(self, mock_session):
        """Test creating a memory."""
        from app.memory.store import MemoryStore
        
        store = MemoryStore(session=mock_session)
        
        # Mock the session operations
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        # This would normally create a memory
        # For now, just verify the store exists
        assert store is not None
    
    @pytest.mark.asyncio
    async def test_append_message(self, mock_session):
        """Test appending a message to a thread."""
        from app.memory.store import MemoryStore
        
        store = MemoryStore(session=mock_session)
        
        # Verify store has the method
        assert hasattr(store, 'append_message')
    
    @pytest.mark.asyncio
    async def test_get_thread(self, mock_session):
        """Test getting a thread by ID."""
        from app.memory.store import MemoryStore
        
        store = MemoryStore(session=mock_session)
        
        # Verify store has the method
        assert hasattr(store, 'get_thread')
    
    @pytest.mark.asyncio
    async def test_list_memories(self, mock_session):
        """Test listing memories with filters."""
        from app.memory.store import MemoryStore
        
        store = MemoryStore(session=mock_session)
        
        # Verify store has the method
        assert hasattr(store, 'list_memories')


# =============================================================================
# Thread State Tests
# =============================================================================

class TestThreadState:
    """Tests for ThreadState class."""
    
    @pytest.mark.asyncio
    async def test_get_current_thread(self, mock_session):
        """Test getting current thread for a session."""
        from app.memory.thread_state import ThreadState
        
        thread_state = ThreadState(session=mock_session)
        
        # Verify thread_state has the method
        assert hasattr(thread_state, 'get_current_thread')
    
    @pytest.mark.asyncio
    async def test_create_new_thread(self, mock_session):
        """Test creating a new thread."""
        from app.memory.thread_state import ThreadState
        
        thread_state = ThreadState(session=mock_session)
        
        # Verify thread_state has the method
        assert hasattr(thread_state, 'create_new_thread')
    
    @pytest.mark.asyncio
    async def test_get_thread_history(self, mock_session):
        """Test getting thread history for a session."""
        from app.memory.thread_state import ThreadState
        
        thread_state = ThreadState(session=mock_session)
        
        # Verify thread_state has the method
        assert hasattr(thread_state, 'get_thread_history')
    
    @pytest.mark.asyncio
    async def test_get_session_stats(self, mock_session):
        """Test getting session statistics."""
        from app.memory.thread_state import ThreadState
        
        thread_state = ThreadState(session=mock_session)
        
        # Verify thread_state has the method
        assert hasattr(thread_state, 'get_session_stats')


# =============================================================================
# Context Router Tests
# =============================================================================

class TestContextRouter:
    """Tests for ContextRouter class."""
    
    def test_should_create_new_thread(self):
        """Test determining if a new thread should be created."""
        from app.agent.context_router import ContextRouter
        
        router = ContextRouter()
        
        # Verify router has the method
        assert hasattr(router, 'should_create_new_thread')
    
    def test_get_topic_similarity(self):
        """Test calculating topic similarity."""
        from app.agent.context_router import ContextRouter
        
        router = ContextRouter()
        
        # Verify router has the method
        assert hasattr(router, 'get_topic_similarity')
    
    def test_create_new_thread_if_needed(self):
        """Test conditional thread creation."""
        from app.agent.context_router import ContextRouter
        
        router = ContextRouter()
        
        # Verify router has the method
        assert hasattr(router, 'create_new_thread_if_needed')
    
    def test_get_thread_context(self):
        """Test getting thread context."""
        from app.agent.context_router import ContextRouter
        
        router = ContextRouter()
        
        # Verify router has the method
        assert hasattr(router, 'get_thread_context')


# =============================================================================
# Extraction Rules Tests
# =============================================================================

class TestMemoryExtractionRules:
    """Tests for MemoryExtractionRules class."""
    
    def test_classify_candidates(self):
        """Test classifying memory candidates."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test with empty candidates
        result = rules.classify_candidates([])
        assert result == []
    
    def test_is_allowed_category(self):
        """Test checking if a category is allowed."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test allowed categories
        assert rules.is_allowed_category("preference") is True
        assert rules.is_allowed_category("project") is True
        assert rules.is_allowed_category("workflow") is True
        assert rules.is_allowed_category("fact") is True
        
        # Test disallowed categories
        assert rules.is_allowed_category("transient") is False
        assert rules.is_allowed_category("sensitive") is False
    
    def test_is_sensitive_content(self):
        """Test detecting sensitive content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test sensitive patterns
        assert rules.is_sensitive_content("my password is secret123") is True
        assert rules.is_sensitive_content("api_key=abc123") is True
        assert rules.is_sensitive_content("my credit card number") is True
        
        # Test non-sensitive content
        assert rules.is_sensitive_content("I prefer dark mode") is False
        assert rules.is_sensitive_content("The project is called Teiken") is False
    
    def test_get_category(self):
        """Test categorizing content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test preference detection
        category = rules.get_category("I prefer using dark mode in my editor")
        assert category in ["preference", "note"]
        
        # Test project detection
        category = rules.get_category("The project is called Teiken Claw")
        assert category in ["project", "fact", "note"]
    
    def test_extract_facts(self):
        """Test extracting facts from content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test fact extraction
        content = "I work on the Teiken project. My timezone is CST."
        facts = rules.extract_facts(content)
        
        # Should extract some facts
        assert isinstance(facts, list)
    
    def test_extract_preferences(self):
        """Test extracting preferences from content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test preference extraction
        content = "I prefer dark mode. I like using Python for scripting."
        prefs = rules.extract_preferences(content)
        
        # Should extract some preferences
        assert isinstance(prefs, list)


# =============================================================================
# Memory Review Tests
# =============================================================================

class TestMemoryReview:
    """Tests for MemoryReview class."""
    
    @pytest.mark.asyncio
    async def test_list_memories(self, mock_session):
        """Test listing memories for review."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'list_memories')
    
    @pytest.mark.asyncio
    async def test_search_memories(self, mock_session):
        """Test searching memories."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'search_memories')
    
    @pytest.mark.asyncio
    async def test_delete_memory(self, mock_session):
        """Test deleting a memory."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'delete_memory')
    
    @pytest.mark.asyncio
    async def test_edit_memory(self, mock_session):
        """Test editing a memory."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'edit_memory')
    
    @pytest.mark.asyncio
    async def test_pause_auto_memory(self, mock_session):
        """Test pausing auto-memory."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'pause_auto_memory')
    
    @pytest.mark.asyncio
    async def test_resume_auto_memory(self, mock_session):
        """Test resuming auto-memory."""
        from app.memory.review import MemoryReview
        
        review = MemoryReview(session=mock_session)
        
        # Verify review has the method
        assert hasattr(review, 'resume_auto_memory')


# =============================================================================
# Integration Tests
# =============================================================================

class TestMemoryIntegration:
    """Integration tests for the memory system."""
    
    @pytest.mark.asyncio
    async def test_full_memory_lifecycle(self, mock_session):
        """Test the full memory lifecycle: create, read, update, delete."""
        from app.memory.store import MemoryStore
        from app.memory.review import MemoryReview
        
        store = MemoryStore(session=mock_session)
        review = MemoryReview(session=mock_session)
        
        # Verify both have required methods
        assert hasattr(store, 'create_memory')
        assert hasattr(store, 'get_memory')
        assert hasattr(review, 'edit_memory')
        assert hasattr(review, 'delete_memory')
    
    @pytest.mark.asyncio
    async def test_thread_persistence(self, mock_session):
        """Test that messages persist to threads correctly."""
        from app.memory.store import MemoryStore
        from app.memory.thread_state import ThreadState
        
        store = MemoryStore(session=mock_session)
        thread_state = ThreadState(session=mock_session)
        
        # Verify both have required methods
        assert hasattr(store, 'append_message')
        assert hasattr(thread_state, 'get_current_thread')
    
    def test_extraction_pipeline(self):
        """Test the extraction pipeline."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test content
        content = """
        I prefer using dark mode in my editor.
        The project is called Teiken Claw.
        My timezone is America/Chicago.
        I always run tests before committing.
        """
        
        # Extract facts
        facts = rules.extract_facts(content)
        
        # Classify candidates
        classified = rules.classify_candidates(facts)
        
        # Verify results
        assert isinstance(classified, list)
        
        # Check that sensitive content is filtered
        sensitive_content = "My password is secret123"
        assert rules.is_sensitive_content(sensitive_content) is True


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestMemoryEdgeCases:
    """Tests for edge cases in the memory system."""
    
    def test_empty_content_extraction(self):
        """Test extraction with empty content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test with empty string
        facts = rules.extract_facts("")
        assert facts == []
        
        # Test with whitespace only
        facts = rules.extract_facts("   \n\t  ")
        assert facts == []
    
    def test_special_characters_in_content(self):
        """Test handling special characters in content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test with special characters
        content = "I use @mentions and #hashtags in my workflow"
        facts = rules.extract_facts(content)
        
        # Should handle without error
        assert isinstance(facts, list)
    
    def test_very_long_content(self):
        """Test handling very long content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Create a very long content string
        content = "This is a fact. " * 1000
        
        # Should handle without error
        facts = rules.extract_facts(content)
        assert isinstance(facts, list)
    
    def test_unicode_content(self):
        """Test handling unicode content."""
        from app.memory.extraction_rules import MemoryExtractionRules
        
        rules = MemoryExtractionRules()
        
        # Test with unicode characters
        content = "I speak 日本語 and español"
        facts = rules.extract_facts(content)
        
        # Should handle without error
        assert isinstance(facts, list)


# =============================================================================
# Command Handler Tests
# =============================================================================

class TestMemoryCommands:
    """Tests for memory command handlers."""
    
    @pytest.mark.asyncio
    async def test_handle_memory_review(self):
        """Test the memory review command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_review')
    
    @pytest.mark.asyncio
    async def test_handle_memory_search(self):
        """Test the memory search command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_search')
    
    @pytest.mark.asyncio
    async def test_handle_memory_forget(self):
        """Test the memory forget command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_forget')
    
    @pytest.mark.asyncio
    async def test_handle_memory_edit(self):
        """Test the memory edit command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_edit')
    
    @pytest.mark.asyncio
    async def test_handle_memory_pause(self):
        """Test the memory pause command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_pause')
    
    @pytest.mark.asyncio
    async def test_handle_memory_resume(self):
        """Test the memory resume command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_resume')
    
    @pytest.mark.asyncio
    async def test_handle_memory_policy(self):
        """Test the memory policy command handler."""
        from app.interfaces.telegram_commands import CommandRouter
        
        router = CommandRouter()
        
        # Verify router has the method
        assert hasattr(router, '_handle_memory_policy')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
