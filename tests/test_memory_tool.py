"""
Tests for Memory Tool.

This module tests the MemoryTool class for:
- Memory storage
- Memory search
- Memory deletion
- Memory review
- Auto-memory pause/resume
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from app.tools.memory_tool import MemoryTool, MEMORY_TYPES, MEMORY_SCOPES
from app.tools.base import ToolPolicy


class TestMemoryTool:
    """Tests for MemoryTool class."""
    
    def test_init_default(self):
        """Test initialization with default settings."""
        tool = MemoryTool()
        assert tool.name == "memory"
        assert tool._auto_memory_enabled
    
    def test_init_custom(self):
        """Test initialization with custom settings."""
        policy = ToolPolicy(timeout_sec=60.0)
        tool = MemoryTool(
            policy=policy,
            auto_memory_enabled=False,
        )
        assert not tool._auto_memory_enabled
    
    def test_name_property(self):
        """Test name property."""
        tool = MemoryTool()
        assert tool.name == "memory"
    
    def test_description_property(self):
        """Test description property."""
        tool = MemoryTool()
        assert "memory" in tool.description.lower()
    
    def test_json_schema(self):
        """Test JSON schema structure."""
        tool = MemoryTool()
        schema = tool.json_schema
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "memory"
        assert "action" in schema["function"]["parameters"]["properties"]
        assert "content" in schema["function"]["parameters"]["properties"]
        assert "query" in schema["function"]["parameters"]["properties"]
    
    def test_memory_types_defined(self):
        """Test that memory types are defined."""
        assert "fact" in MEMORY_TYPES
        assert "preference" in MEMORY_TYPES
        assert "context" in MEMORY_TYPES
        assert "instruction" in MEMORY_TYPES
        assert "note" in MEMORY_TYPES
    
    def test_memory_scopes_defined(self):
        """Test that memory scopes are defined."""
        assert "global" in MEMORY_SCOPES
        assert "chat" in MEMORY_SCOPES
        assert "session" in MEMORY_SCOPES
    
    @pytest.mark.asyncio
    async def test_execute_missing_action(self):
        """Test execute with missing action."""
        tool = MemoryTool()
        result = await tool.execute()
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code
    
    @pytest.mark.asyncio
    async def test_execute_invalid_action(self):
        """Test execute with invalid action."""
        tool = MemoryTool()
        result = await tool.execute(action="invalid")
        assert not result.ok
        assert "INVALID_ACTION" in result.error_code


class TestMemoryToolRemember:
    """Tests for memory storage."""
    
    @pytest.mark.asyncio
    async def test_remember_missing_content(self):
        """Test remember with missing content."""
        tool = MemoryTool()
        result = await tool.execute(action="remember")
        assert not result.ok
        assert "MISSING_CONTENT" in result.error_code
    
    @pytest.mark.asyncio
    async def test_remember_invalid_type(self):
        """Test remember with invalid memory type."""
        tool = MemoryTool()
        result = await tool.execute(
            action="remember",
            content="Test content",
            memory_type="invalid_type"
        )
        assert not result.ok
        assert "INVALID_MEMORY_TYPE" in result.error_code
    
    @pytest.mark.asyncio
    async def test_remember_invalid_scope(self):
        """Test remember with invalid scope."""
        tool = MemoryTool()
        result = await tool.execute(
            action="remember",
            content="Test content",
            memory_type="fact",
            scope="invalid_scope"
        )
        assert not result.ok
        assert "INVALID_SCOPE" in result.error_code
    
    @pytest.mark.asyncio
    async def test_remember_success(self):
        """Test successful memory storage."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.create_memory.return_value = mock_memory
            
            result = await tool.execute(
                action="remember",
                content="Test memory content",
                memory_type="fact",
                scope="chat",
                tags=["test"]
            )
            
            assert result.ok
            assert "stored successfully" in result.content.lower()
            mock_store.create_memory.assert_called_once()


class TestMemoryToolSearch:
    """Tests for memory search."""
    
    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        """Test search with missing query."""
        tool = MemoryTool()
        result = await tool.execute(action="search")
        assert not result.ok
        assert "MISSING_QUERY" in result.error_code
    
    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """Test search with no results."""
        tool = MemoryTool()
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.search_memories.return_value = []
            
            result = await tool.execute(
                action="search",
                query="nonexistent"
            )
            
            assert result.ok
            assert "No memories found" in result.content
    
    @pytest.mark.asyncio
    async def test_search_with_results(self):
        """Test search with results."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.content = "Test memory"
        mock_memory.memory_type = "fact"
        mock_memory.scope = "chat"
        mock_memory.tags = ["test"]
        mock_memory.created_at = datetime.utcnow()
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.search_memories.return_value = [mock_memory]
            
            result = await tool.execute(
                action="search",
                query="test"
            )
            
            assert result.ok
            assert "Test memory" in result.content


class TestMemoryToolForget:
    """Tests for memory deletion."""
    
    @pytest.mark.asyncio
    async def test_forget_missing_id(self):
        """Test forget with missing memory ID."""
        tool = MemoryTool()
        result = await tool.execute(action="forget")
        assert not result.ok
        assert "MISSING_MEMORY_ID" in result.error_code
    
    @pytest.mark.asyncio
    async def test_forget_not_found(self):
        """Test forget with non-existent memory."""
        tool = MemoryTool()
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.get_memory.return_value = None
            
            result = await tool.execute(
                action="forget",
                memory_id=999
            )
            
            assert not result.ok
            assert "NOT_FOUND" in result.error_code
    
    @pytest.mark.asyncio
    async def test_forget_permission_denied(self):
        """Test forget with permission denied."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.chat_id = "other_chat"
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.get_memory.return_value = mock_memory
            
            result = await tool.execute(
                action="forget",
                memory_id=1,
                _chat_id="current_chat",
                _is_admin=False
            )
            
            assert not result.ok
            assert "PERMISSION_DENIED" in result.error_code
    
    @pytest.mark.asyncio
    async def test_forget_success(self):
        """Test successful memory deletion."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.chat_id = "test_chat"
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.get_memory.return_value = mock_memory
            mock_store.delete_memory.return_value = True
            
            result = await tool.execute(
                action="forget",
                memory_id=1,
                _chat_id="test_chat",
                _is_admin=False
            )
            
            assert result.ok
            assert "deleted" in result.content.lower()


class TestMemoryToolReview:
    """Tests for memory review."""
    
    @pytest.mark.asyncio
    async def test_review_no_memories(self):
        """Test review with no memories."""
        tool = MemoryTool()
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.list_memories.return_value = []
            mock_store.count_memories.return_value = 0
            
            result = await tool.execute(action="review")
            
            assert result.ok
            assert "No memories" in result.content
    
    @pytest.mark.asyncio
    async def test_review_with_memories(self):
        """Test review with memories."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.content = "Test memory content"
        mock_memory.memory_type = "fact"
        
        with patch.object(tool, '_memory_store') as mock_store:
            mock_store.list_memories.return_value = [mock_memory]
            mock_store.count_memories.return_value = 1
            
            result = await tool.execute(action="review")
            
            assert result.ok
            assert "Test memory" in result.content


class TestMemoryToolPauseResume:
    """Tests for auto-memory pause/resume."""
    
    @pytest.mark.asyncio
    async def test_pause(self):
        """Test pausing auto-memory."""
        tool = MemoryTool()
        
        result = await tool.execute(action="pause")
        
        assert result.ok
        assert "paused" in result.content.lower()
        assert not tool._auto_memory_enabled
    
    @pytest.mark.asyncio
    async def test_resume(self):
        """Test resuming auto-memory."""
        tool = MemoryTool()
        tool._auto_memory_enabled = False
        
        result = await tool.execute(action="resume")
        
        assert result.ok
        assert "resumed" in result.content.lower()
        assert tool._auto_memory_enabled


class TestMemoryToolFormatting:
    """Tests for result formatting."""
    
    def test_format_search_results(self):
        """Test search results formatting."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.content = "Test content"
        mock_memory.memory_type = "fact"
        mock_memory.scope = "chat"
        mock_memory.tags = ["test"]
        mock_memory.created_at = datetime.utcnow()
        
        result = tool._format_search_results([mock_memory])
        
        assert "Memory #1" in result
        assert "Test content" in result
        assert "fact" in result
    
    def test_format_memory_list(self):
        """Test memory list formatting."""
        tool = MemoryTool()
        
        mock_memory = MagicMock()
        mock_memory.id = 1
        mock_memory.content = "Test content"
        mock_memory.memory_type = "fact"
        
        result = tool._format_memory_list([mock_memory], 1, 0, 10)
        
        assert "Memory #1" in result
        assert "1 total" in result


class TestMemoryToolPolicy:
    """Tests for MemoryTool policy enforcement."""
    
    def test_policy_applied(self):
        """Test that policy is properly applied."""
        policy = ToolPolicy(
            enabled=True,
            admin_only=False,
            timeout_sec=45.0,
        )
        tool = MemoryTool(policy=policy)
        
        assert tool.policy.enabled
        assert tool.policy.timeout_sec == 45.0
    
    def test_to_ollama_tool(self):
        """Test conversion to Ollama tool format."""
        tool = MemoryTool()
        ollama_tool = tool.to_ollama_tool()
        
        assert ollama_tool == tool.json_schema
