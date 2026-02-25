"""
Tests for the agent runtime module.

This module tests:
- AgentRuntime class
- AgentResult model
- Tool calling loop
- Error handling
- Max turns guard
- Duplicate tool detection
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

from app.agent.runtime import (
    AgentRuntime,
    AgentResult,
    ToolCallRecord,
    MAX_TOOL_TURNS,
    MAX_RETRIES,
)
from app.agent.ollama_client import ChatResponse, ChatMessage
from app.agent.errors import (
    OllamaTransportError,
    CircuitBreakerOpenError,
)
from app.queue.jobs import Job, JobType, JobSource, JobPriority
from app.tools.base import Tool, ToolResult, ToolPolicy


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_ollama_client():
    """Create a mock Ollama client."""
    client = AsyncMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def mock_tool_registry():
    """Create a mock tool registry."""
    registry = MagicMock()
    registry.get_allowed_schemas = MagicMock(return_value=[])
    registry.execute_tool_call = AsyncMock()
    return registry


@pytest.fixture
def mock_context_builder():
    """Create a mock context builder."""
    builder = MagicMock()
    builder.build_with_user_message = MagicMock(return_value=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
    ])
    return builder


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return Job(
        job_id="test-job-123",
        source=JobSource.TELEGRAM,
        type=JobType.CHAT_MESSAGE,
        priority=JobPriority.INTERACTIVE,
        chat_id="123456",
        session_id="session-123",
        thread_id="thread-456",
        payload={"text": "Hello!"},
    )


@pytest.fixture
def simple_response():
    """Create a simple chat response without tool calls."""
    return ChatResponse(
        model="llama3.2",
        message=ChatMessage(
            role="assistant",
            content="Hello! How can I help you today?",
        ),
        done=True,
    )


@pytest.fixture
def tool_call_response():
    """Create a chat response with a tool call."""
    return ChatResponse(
        model="llama3.2",
        message=ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "function": {
                        "name": "echo",
                        "arguments": {"message": "test"},
                    }
                }
            ],
        ),
        done=True,
    )


# =============================================================================
# AgentResult Tests
# =============================================================================

class TestAgentResult:
    """Tests for the AgentResult model."""
    
    def test_success_result(self):
        """Test creating a successful result."""
        result = AgentResult(
            ok=True,
            response="Hello!",
            tool_calls=0,
        )
        
        assert result.ok is True
        assert result.response == "Hello!"
        assert result.tool_calls == 0
        assert result.error is None
        assert result.error_code is None
    
    def test_error_result(self):
        """Test creating an error result."""
        result = AgentResult(
            ok=False,
            error="Something went wrong",
            error_code="INTERNAL_ERROR",
        )
        
        assert result.ok is False
        assert result.error == "Something went wrong"
        assert result.error_code == "INTERNAL_ERROR"
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = AgentResult(
            ok=True,
            response="Done",
            metadata={"turns": 3, "tools_used": ["echo"]},
        )
        
        assert result.metadata["turns"] == 3
        assert result.metadata["tools_used"] == ["echo"]


# =============================================================================
# ToolCallRecord Tests
# =============================================================================

class TestToolCallRecord:
    """Tests for the ToolCallRecord class."""
    
    def test_from_call(self):
        """Test creating a record from a tool call."""
        tool_call = {
            "function": {
                "name": "echo",
                "arguments": {"message": "hello"},
            }
        }
        
        record = ToolCallRecord.from_call(tool_call)
        
        assert record.tool_name == "echo"
        assert record.arguments_hash is not None
        assert record.timestamp is not None
    
    def test_duplicate_detection(self):
        """Test that duplicate calls have the same hash."""
        tool_call1 = {
            "function": {
                "name": "echo",
                "arguments": {"message": "hello"},
            }
        }
        tool_call2 = {
            "function": {
                "name": "echo",
                "arguments": {"message": "hello"},
            }
        }
        
        record1 = ToolCallRecord.from_call(tool_call1)
        record2 = ToolCallRecord.from_call(tool_call2)
        
        assert record1.arguments_hash == record2.arguments_hash
    
    def test_different_arguments_different_hash(self):
        """Test that different arguments produce different hashes."""
        tool_call1 = {
            "function": {
                "name": "echo",
                "arguments": {"message": "hello"},
            }
        }
        tool_call2 = {
            "function": {
                "name": "echo",
                "arguments": {"message": "world"},
            }
        }
        
        record1 = ToolCallRecord.from_call(tool_call1)
        record2 = ToolCallRecord.from_call(tool_call2)
        
        assert record1.arguments_hash != record2.arguments_hash


# =============================================================================
# AgentRuntime Tests
# =============================================================================

class TestAgentRuntime:
    """Tests for the AgentRuntime class."""
    
    @pytest.mark.asyncio
    async def test_simple_run_no_tools(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        simple_response,
    ):
        """Test a simple run without tool calls."""
        mock_ollama_client.chat.return_value = simple_response
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is True
        assert result.response == "Hello! How can I help you today?"
        assert result.tool_calls == 0
        mock_ollama_client.chat.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tool_call_loop(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        tool_call_response,
        simple_response,
    ):
        """Test the tool-calling loop."""
        # First call returns tool call, second returns final response
        mock_ollama_client.chat.side_effect = [
            tool_call_response,
            simple_response,
        ]
        
        mock_tool_registry.execute_tool_call.return_value = ToolResult.success(
            content="Echo: test"
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is True
        assert result.tool_calls == 1
        assert mock_ollama_client.chat.call_count == 2
    
    @pytest.mark.asyncio
    async def test_max_tool_turns_guard(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        tool_call_response,
    ):
        """Test that max tool turns is enforced."""
        # Always return a tool call
        mock_ollama_client.chat.return_value = tool_call_response
        
        mock_tool_registry.execute_tool_call.return_value = ToolResult.success(
            content="Echo: test"
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
            max_tool_turns=3,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is False
        assert result.error_code == "MAX_TURNS_EXCEEDED"
    
    @pytest.mark.asyncio
    async def test_duplicate_tool_detection(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        tool_call_response,
        simple_response,
    ):
        """Test that duplicate tool calls are detected."""
        # Return same tool call twice, then final response
        mock_ollama_client.chat.side_effect = [
            tool_call_response,
            tool_call_response,
            simple_response,
        ]
        
        mock_tool_registry.execute_tool_call.return_value = ToolResult.success(
            content="Echo: test"
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        # Should have detected duplicate on second call
        assert result.ok is True
    
    @pytest.mark.asyncio
    async def test_ollama_transport_error(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
    ):
        """Test handling of Ollama transport errors."""
        mock_ollama_client.chat.side_effect = OllamaTransportError(
            message="Connection failed",
            endpoint="/api/chat",
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is False
        assert result.error_code == "TRANSPORT_ERROR"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
    ):
        """Test handling of circuit breaker open errors."""
        mock_ollama_client.chat.side_effect = CircuitBreakerOpenError(
            message="Circuit breaker open",
            breaker_name="ollama",
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is False
        assert result.error_code == "CIRCUIT_BREAKER_OPEN"
    
    @pytest.mark.asyncio
    async def test_tool_error_handling(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        tool_call_response,
        simple_response,
    ):
        """Test that tool errors don't crash the runtime."""
        mock_ollama_client.chat.side_effect = [
            tool_call_response,
            simple_response,
        ]
        
        mock_tool_registry.execute_tool_call.return_value = ToolResult.error(
            error_code="EXECUTION_ERROR",
            error_message="Tool failed",
        )
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        # Should still complete successfully
        assert result.ok is True
    
    @pytest.mark.asyncio
    async def test_retry_on_transient_error(
        self,
        mock_ollama_client,
        mock_tool_registry,
        mock_context_builder,
        sample_job,
        simple_response,
    ):
        """Test retry logic for transient errors."""
        # First two calls fail, third succeeds
        mock_ollama_client.chat.side_effect = [
            OllamaTransportError(message="Timeout", endpoint="/api/chat"),
            OllamaTransportError(message="Timeout", endpoint="/api/chat"),
            simple_response,
        ]
        
        runtime = AgentRuntime(
            ollama_client=mock_ollama_client,
            tool_registry=mock_tool_registry,
            context_builder=mock_context_builder,
        )
        
        result = await runtime.run(sample_job)
        
        assert result.ok is True
        assert mock_ollama_client.chat.call_count == 3


# =============================================================================
# Integration Tests
# =============================================================================

class TestAgentRuntimeIntegration:
    """Integration tests for the agent runtime."""
    
    @pytest.mark.asyncio
    async def test_full_tool_call_flow(self, sample_job):
        """Test a full tool call flow with real components."""
        # This test would require actual Ollama connection
        # Skip in CI/CD
        pytest.skip("Integration test requires Ollama connection")


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
