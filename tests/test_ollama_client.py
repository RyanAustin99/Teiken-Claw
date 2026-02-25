"""
Tests for Ollama client, retry logic, and circuit breaker.

This module contains comprehensive tests for:
- OllamaClient: HTTP client for Ollama API
- RetryPolicy: Retry configuration and backoff logic
- CircuitBreaker: Fault tolerance pattern

Test Categories:
    - Unit tests for individual components
    - Integration tests for component interactions
    - Error handling tests
    - State transition tests
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.agent.errors import (
    OllamaTransportError,
    OllamaResponseError,
    OllamaModelError,
    CircuitBreakerOpenError,
    is_retryable_error,
    classify_http_status,
)
from app.agent.retries import (
    RetryPolicy,
    exponential_backoff_with_jitter,
    should_retry,
    retry_async,
    OLLAMA_CHAT_RETRY_POLICY,
    OLLAMA_EMBED_RETRY_POLICY,
    reset_retry_stats,
    get_retry_stats,
)
from app.agent.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    circuit_breaker_protect,
    get_ollama_circuit_breaker,
    reset_ollama_circuit_breaker,
    get_circuit_breaker_metrics,
)
from app.agent.ollama_client import (
    OllamaClient,
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    ModelInfo,
    get_ollama_client,
    reset_ollama_client,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_ollama_client()
    reset_ollama_circuit_breaker()
    reset_retry_stats()
    yield
    reset_ollama_client()
    reset_ollama_circuit_breaker()
    reset_retry_stats()


@pytest.fixture
def circuit_breaker():
    """Create a fresh circuit breaker for testing."""
    return CircuitBreaker(
        name="test",
        failure_threshold=3,
        success_threshold=2,
        timeout_sec=1.0,
    )


@pytest.fixture
def retry_policy():
    """Create a fast retry policy for testing."""
    return RetryPolicy(
        max_attempts=3,
        base_delay_sec=0.01,
        max_delay_sec=0.1,
        exponential_base=2.0,
        jitter=False,  # Disable jitter for predictable tests
    )


@pytest.fixture
def ollama_client(circuit_breaker, retry_policy):
    """Create an Ollama client with test configuration."""
    return OllamaClient(
        base_url="http://test:11434",
        timeout_sec=5.0,
        chat_model="test-model",
        embed_model="test-embed",
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
    )


# =============================================================================
# Error Classification Tests
# =============================================================================


class TestErrorClassification:
    """Tests for error classification functions."""

    def test_transport_error_is_retryable(self):
        """OllamaTransportError should be retryable."""
        error = OllamaTransportError("Connection failed", endpoint="/api/chat")
        assert is_retryable_error(error) is True

    def test_timeout_error_is_retryable(self):
        """Timeout errors should be retryable."""
        error = OllamaTransportError("Timeout", timeout=True)
        assert is_retryable_error(error) is True

    def test_response_error_is_not_retryable(self):
        """OllamaResponseError should not be retryable."""
        error = OllamaResponseError("Invalid response", status_code=400)
        assert is_retryable_error(error) is False

    def test_model_error_is_not_retryable(self):
        """OllamaModelError should not be retryable."""
        error = OllamaModelError("Model not found", model_name="bad-model")
        assert is_retryable_error(error) is False

    def test_circuit_breaker_open_is_retryable(self):
        """CircuitBreakerOpenError should be retryable (after timeout)."""
        error = CircuitBreakerOpenError(breaker_name="test")
        assert is_retryable_error(error) is True

    def test_classify_http_status_5xx_retryable(self):
        """5xx status codes should be retryable."""
        assert classify_http_status(500) == "retryable"
        assert classify_http_status(502) == "retryable"
        assert classify_http_status(503) == "retryable"

    def test_classify_http_status_429_retryable(self):
        """429 (rate limit) should be retryable."""
        assert classify_http_status(429) == "retryable"

    def test_classify_http_status_4xx_permanent(self):
        """4xx status codes should be permanent."""
        assert classify_http_status(400) == "permanent"
        assert classify_http_status(401) == "permanent"
        assert classify_http_status(404) == "permanent"


# =============================================================================
# Retry Policy Tests
# =============================================================================


class TestRetryPolicy:
    """Tests for retry policy and backoff logic."""

    def test_default_retry_policy(self):
        """Default retry policy should have sensible values."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay_sec == 1.0
        assert policy.max_delay_sec == 30.0
        assert policy.exponential_base == 2.0
        assert policy.jitter is True

    def test_max_retries_property(self):
        """max_retries should be max_attempts - 1."""
        policy = RetryPolicy(max_attempts=5)
        assert policy.max_retries == 4

    def test_exponential_backoff_without_jitter(self):
        """Backoff should follow exponential pattern without jitter."""
        policy = RetryPolicy(
            base_delay_sec=1.0,
            max_delay_sec=30.0,
            exponential_base=2.0,
            jitter=False,
        )

        # First retry: 1 * 2^0 = 1
        delay0 = exponential_backoff_with_jitter(0, policy)
        assert delay0 == 1.0

        # Second retry: 1 * 2^1 = 2
        delay1 = exponential_backoff_with_jitter(1, policy)
        assert delay1 == 2.0

        # Third retry: 1 * 2^2 = 4
        delay2 = exponential_backoff_with_jitter(2, policy)
        assert delay2 == 4.0

    def test_exponential_backoff_with_cap(self):
        """Backoff should be capped at max_delay_sec."""
        policy = RetryPolicy(
            base_delay_sec=1.0,
            max_delay_sec=10.0,
            exponential_base=2.0,
            jitter=False,
        )

        # 2^10 = 1024, but should be capped at 10
        delay = exponential_backoff_with_jitter(10, policy)
        assert delay == 10.0

    def test_exponential_backoff_with_jitter(self):
        """Backoff with jitter should add random factor."""
        policy = RetryPolicy(
            base_delay_sec=1.0,
            max_delay_sec=30.0,
            exponential_base=2.0,
            jitter=True,
        )

        # Run multiple times to verify jitter is applied
        delays = [exponential_backoff_with_jitter(0, policy) for _ in range(10)]

        # All delays should be between 0.5 and 1.5 (jitter factor 0.5-1.5)
        for delay in delays:
            assert 0.5 <= delay <= 1.5

        # Not all delays should be the same (jitter should vary)
        assert len(set(delays)) > 1

    def test_should_retry_within_attempts(self):
        """should_retry should return True for retryable errors within attempt limit."""
        policy = RetryPolicy(max_attempts=3)
        error = OllamaTransportError("Connection failed")

        assert should_retry(error, policy, attempt=0) is True
        assert should_retry(error, policy, attempt=1) is True

    def test_should_retry_exhausted_attempts(self):
        """should_retry should return False when attempts are exhausted."""
        policy = RetryPolicy(max_attempts=3)
        error = OllamaTransportError("Connection failed")

        # attempt 2 is the last attempt (0, 1, 2 = 3 total)
        assert should_retry(error, policy, attempt=2) is False

    def test_should_retry_permanent_error(self):
        """should_retry should return False for permanent errors."""
        policy = RetryPolicy(max_attempts=3)
        error = OllamaResponseError("Bad request", status_code=400)

        assert should_retry(error, policy, attempt=0) is False


# =============================================================================
# Retry Decorator Tests
# =============================================================================


class TestRetryDecorator:
    """Tests for the retry_async decorator."""

    @pytest.mark.asyncio
    async def test_retry_decorator_success_first_try(self, retry_policy):
        """Decorator should return result on first success."""
        call_count = 0

        @retry_async(retry_policy)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_decorator_success_after_retry(self, retry_policy):
        """Decorator should retry on retryable errors."""
        call_count = 0

        @retry_async(retry_policy)
        async def eventually_successful_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OllamaTransportError("Connection failed")
            return "success"

        result = await eventually_successful_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_decorator_fail_after_max_attempts(self, retry_policy):
        """Decorator should raise after max attempts exhausted."""
        call_count = 0

        @retry_async(retry_policy)
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise OllamaTransportError("Connection failed")

        with pytest.raises(OllamaTransportError):
            await always_failing_func()

        assert call_count == retry_policy.max_attempts

    @pytest.mark.asyncio
    async def test_retry_decorator_no_retry_on_permanent_error(self, retry_policy):
        """Decorator should not retry on permanent errors."""
        call_count = 0

        @retry_async(retry_policy)
        async def permanent_error_func():
            nonlocal call_count
            call_count += 1
            raise OllamaResponseError("Bad request", status_code=400)

        with pytest.raises(OllamaResponseError):
            await permanent_error_func()

        assert call_count == 1  # Should not retry


# =============================================================================
# Circuit Breaker Tests
# =============================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker state transitions."""

    def test_initial_state_is_closed(self, circuit_breaker):
        """Circuit breaker should start in CLOSED state."""
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.is_closed is True

    def test_closed_allows_requests(self, circuit_breaker):
        """CLOSED state should allow all requests."""
        assert circuit_breaker.can_execute() is True

    def test_record_success_in_closed_resets_failure_count(self, circuit_breaker):
        """Success in CLOSED state should reset failure count."""
        circuit_breaker.failure_count = 2
        circuit_breaker.record_success()
        assert circuit_breaker.failure_count == 0

    def test_transitions_to_open_after_threshold(self, circuit_breaker):
        """Should transition to OPEN after failure threshold."""
        assert circuit_breaker.failure_threshold == 3

        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.CLOSED

        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.CLOSED

        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

    def test_open_blocks_requests(self, circuit_breaker):
        """OPEN state should block all requests."""
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.last_failure_time = datetime.now(timezone.utc)

        assert circuit_breaker.can_execute() is False

    def test_open_transitions_to_half_open_after_timeout(self, circuit_breaker):
        """OPEN should transition to HALF_OPEN after timeout."""
        circuit_breaker.state = CircuitState.OPEN
        # Set last failure time to more than timeout ago
        circuit_breaker.last_failure_time = datetime.now(
            timezone.utc
        ) - timedelta(seconds=2)

        assert circuit_breaker.can_execute() is True
        assert circuit_breaker.state == CircuitState.HALF_OPEN

    def test_half_open_allows_probe_requests(self, circuit_breaker):
        """HALF_OPEN state should allow probe requests."""
        circuit_breaker.state = CircuitState.HALF_OPEN

        assert circuit_breaker.can_execute() is True

    def test_half_open_transitions_to_closed_after_successes(self, circuit_breaker):
        """HALF_OPEN should transition to CLOSED after success threshold."""
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.success_threshold = 2

        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.HALF_OPEN

        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_half_open_transitions_to_open_on_failure(self, circuit_breaker):
        """HALF_OPEN should transition to OPEN on any failure."""
        circuit_breaker.state = CircuitState.HALF_OPEN

        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

    def test_reset_returns_to_closed(self, circuit_breaker):
        """Reset should return to CLOSED state."""
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.failure_count = 5

        circuit_breaker.reset()

        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0

    def test_get_status(self, circuit_breaker):
        """get_status should return current state and metrics."""
        circuit_breaker.failure_count = 2
        status = circuit_breaker.get_status()

        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["failure_count"] == 2
        assert status["failure_threshold"] == 3


class TestCircuitBreakerDecorator:
    """Tests for the circuit_breaker_protect decorator."""

    @pytest.mark.asyncio
    async def test_decorator_allows_when_closed(self, circuit_breaker):
        """Decorator should allow execution when circuit is closed."""

        @circuit_breaker_protect(circuit_breaker)
        async def protected_func():
            return "success"

        result = await protected_func()
        assert result == "success"
        assert circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_decorator_records_success(self, circuit_breaker):
        """Decorator should record success on successful execution."""

        @circuit_breaker_protect(circuit_breaker)
        async def protected_func():
            return "success"

        await protected_func()
        assert circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_decorator_records_failure(self, circuit_breaker):
        """Decorator should record failure on exception."""

        @circuit_breaker_protect(circuit_breaker)
        async def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_func()

        assert circuit_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_decorator_blocks_when_open(self, circuit_breaker):
        """Decorator should raise CircuitBreakerOpenError when open."""
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.last_failure_time = datetime.now(timezone.utc)

        @circuit_breaker_protect(circuit_breaker)
        async def blocked_func():
            return "should not reach"

        with pytest.raises(CircuitBreakerOpenError):
            await blocked_func()


# =============================================================================
# Ollama Client Tests
# =============================================================================


class TestOllamaClient:
    """Tests for OllamaClient."""

    def test_client_initialization(self, ollama_client):
        """Client should initialize with correct settings."""
        assert ollama_client.base_url == "http://test:11434"
        assert ollama_client.timeout_sec == 5.0
        assert ollama_client.chat_model == "test-model"
        assert ollama_client.embed_model == "test-embed"

    def test_build_url(self, ollama_client):
        """_build_url should construct correct URLs."""
        url = ollama_client._build_url("/api/chat")
        assert url == "http://test:11434/api/chat"

    @pytest.mark.asyncio
    async def test_chat_success(self, ollama_client):
        """chat should return ChatResponse on success."""
        mock_response = {
            "model": "test-model",
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
        }

        with patch.object(
            ollama_client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            response = await ollama_client.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )

            assert isinstance(response, ChatResponse)
            assert response.message.content == "Hello!"
            assert response.done is True

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, ollama_client):
        """chat should include tools in request."""
        mock_response = {
            "model": "test-model",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "test_tool"}}],
            },
            "done": True,
        }

        with patch.object(
            ollama_client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            tools = [{"type": "function", "function": {"name": "test_tool"}}]
            response = await ollama_client.chat(
                messages=[{"role": "user", "content": "Use tool"}], tools=tools
            )

            # Verify tools were passed in request
            call_args = mock_request.call_args
            assert call_args[1]["json_data"]["tools"] == tools
            assert len(response.message.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_embeddings_success(self, ollama_client):
        """embeddings should return EmbeddingResponse on success."""
        mock_response = {
            "embedding": [0.1, 0.2, 0.3, 0.4, 0.5],
            "model": "test-embed",
        }

        with patch.object(
            ollama_client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            response = await ollama_client.embeddings("Hello, world!")

            assert isinstance(response, EmbeddingResponse)
            assert len(response.embedding) == 5
            assert response.model == "test-embed"

    @pytest.mark.asyncio
    async def test_list_models_success(self, ollama_client):
        """list_models should return list of ModelInfo."""
        mock_response = {
            "models": [
                {"name": "llama3.2", "size": 2000000000},
                {"name": "nomic-embed-text", "size": 274000000},
            ]
        }

        with patch.object(
            ollama_client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            models = await ollama_client.list_models()

            assert len(models) == 2
            assert all(isinstance(m, ModelInfo) for m in models)
            assert models[0].name == "llama3.2"

    @pytest.mark.asyncio
    async def test_check_health_success(self, ollama_client):
        """check_health should return healthy status."""
        mock_models = [ModelInfo(name="test-model")]

        with patch.object(
            ollama_client, "list_models", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = mock_models

            health = await ollama_client.check_health()

            assert health["status"] == "healthy"
            assert health["model_count"] == 1

    @pytest.mark.asyncio
    async def test_check_health_failure(self, ollama_client):
        """check_health should return unhealthy status on error."""
        with patch.object(
            ollama_client, "list_models", new_callable=AsyncMock
        ) as mock_list:
            mock_list.side_effect = OllamaTransportError("Connection refused")

            health = await ollama_client.check_health()

            assert health["status"] == "unhealthy"
            assert "Connection refused" in health["error"]

    def test_get_status(self, ollama_client):
        """get_status should return client configuration."""
        status = ollama_client.get_status()

        assert status["base_url"] == "http://test:11434"
        assert status["chat_model"] == "test-model"
        assert status["embed_model"] == "test-embed"
        assert "circuit_breaker" in status


class TestOllamaClientErrorHandling:
    """Tests for OllamaClient error handling."""

    @pytest.mark.asyncio
    async def test_timeout_error_triggers_retry(self, ollama_client, retry_policy):
        """Timeout errors should trigger retry."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Request timed out")
            return {"model": "test", "message": {"role": "assistant", "content": "OK"}}

        with patch.object(
            ollama_client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = mock_request
            mock_client.return_value = mock_http_client

            # This should succeed after retries
            result = await ollama_client._request_with_retry(
                "POST", "/api/chat", {"model": "test"}
            )

            assert call_count == 3

    @pytest.mark.asyncio
    async def test_network_error_triggers_retry(self, ollama_client):
        """Network errors should trigger retry."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.NetworkError("Connection refused")
            return {"model": "test", "message": {"role": "assistant", "content": "OK"}}

        with patch.object(
            ollama_client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = mock_request
            mock_client.return_value = mock_http_client

            result = await ollama_client._request_with_retry(
                "POST", "/api/chat", {"model": "test"}
            )

            assert call_count == 2

    @pytest.mark.asyncio
    async def test_404_raises_model_error(self, ollama_client):
        """404 response should raise OllamaModelError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "model not found"

        with patch.object(
            ollama_client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http_client

            with pytest.raises(OllamaModelError):
                await ollama_client._request_with_retry(
                    "POST", "/api/chat", {"model": "nonexistent"}
                )

    @pytest.mark.asyncio
    async def test_400_raises_response_error(self, ollama_client):
        """400 response should raise OllamaResponseError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch.object(
            ollama_client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http_client

            with pytest.raises(OllamaResponseError) as exc_info:
                await ollama_client._request_with_retry(
                    "POST", "/api/chat", {"model": "test"}
                )

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self, ollama_client, circuit_breaker):
        """Should raise CircuitBreakerOpenError when breaker is open."""
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.last_failure_time = datetime.now(timezone.utc)

        with pytest.raises(CircuitBreakerOpenError):
            await ollama_client._request_with_retry("POST", "/api/chat", {})


# =============================================================================
# Response Model Tests
# =============================================================================


class TestChatMessage:
    """Tests for ChatMessage model."""

    def test_to_dict(self):
        """to_dict should return correct dictionary."""
        msg = ChatMessage(role="user", content="Hello")
        result = msg.to_dict()

        assert result == {"role": "user", "content": "Hello"}

    def test_to_dict_with_tool_calls(self):
        """to_dict should include tool_calls if present."""
        msg = ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"function": {"name": "test"}}],
        )
        result = msg.to_dict()

        assert "tool_calls" in result

    def test_from_dict(self):
        """from_dict should create ChatMessage from dict."""
        data = {"role": "assistant", "content": "Hi there!"}
        msg = ChatMessage.from_dict(data)

        assert msg.role == "assistant"
        assert msg.content == "Hi there!"


class TestChatResponse:
    """Tests for ChatResponse model."""

    def test_from_dict(self):
        """from_dict should create ChatResponse from API response."""
        data = {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
            "total_duration": 1000000000,  # 1 second in nanoseconds
            "eval_count": 10,
        }
        response = ChatResponse.from_dict(data)

        assert response.model == "llama3.2"
        assert response.message.content == "Hello!"
        assert response.done is True
        assert response.total_duration_sec == 1.0
        assert response.eval_count == 10


class TestEmbeddingResponse:
    """Tests for EmbeddingResponse model."""

    def test_from_dict(self):
        """from_dict should create EmbeddingResponse from API response."""
        data = {"embedding": [0.1, 0.2, 0.3], "model": "nomic-embed-text"}
        response = EmbeddingResponse.from_dict(data)

        assert response.embedding == [0.1, 0.2, 0.3]
        assert response.model == "nomic-embed-text"


class TestModelInfo:
    """Tests for ModelInfo model."""

    def test_from_dict(self):
        """from_dict should create ModelInfo from API response."""
        data = {
            "name": "llama3.2",
            "size": 2000000000,
            "digest": "abc123",
        }
        model = ModelInfo.from_dict(data)

        assert model.name == "llama3.2"
        assert model.size == 2000000000
        assert model.digest == "abc123"


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingletons:
    """Tests for singleton instances."""

    def test_get_ollama_client_singleton(self):
        """get_ollama_client should return same instance."""
        client1 = get_ollama_client()
        client2 = get_ollama_client()

        assert client1 is client2

    def test_reset_ollama_client(self):
        """reset_ollama_client should create new instance."""
        client1 = get_ollama_client()
        reset_ollama_client()
        client2 = get_ollama_client()

        assert client1 is not client2

    def test_get_ollama_circuit_breaker_singleton(self):
        """get_ollama_circuit_breaker should return same instance."""
        breaker1 = get_ollama_circuit_breaker()
        breaker2 = get_ollama_circuit_breaker()

        assert breaker1 is breaker2

    def test_get_circuit_breaker_metrics(self):
        """get_circuit_breaker_metrics should return aggregated metrics."""
        # Create the breaker
        breaker = get_ollama_circuit_breaker()

        metrics = get_circuit_breaker_metrics()

        assert metrics.total_breakers >= 1
        assert metrics.closed_count >= 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for Ollama client with retry and circuit breaker."""

    @pytest.mark.asyncio
    async def test_retry_and_circuit_breaker_integration(self, retry_policy):
        """Test that retries and circuit breaker work together."""
        # Create a circuit breaker with low threshold
        breaker = CircuitBreaker(
            name="integration_test",
            failure_threshold=2,
            timeout_sec=1.0,
        )

        client = OllamaClient(
            base_url="http://test:11434",
            retry_policy=retry_policy,
            circuit_breaker=breaker,
        )

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.NetworkError("Connection refused")

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = mock_request
            mock_client.return_value = mock_http_client

            # First call should fail after retries
            with pytest.raises(OllamaTransportError):
                await client._request_with_retry("POST", "/api/chat", {})

            # Circuit breaker should have recorded failures
            assert breaker.failure_count >= 1

    @pytest.mark.asyncio
    async def test_successful_request_resets_failure_count(self, retry_policy):
        """Successful request should reset circuit breaker failure count."""
        breaker = CircuitBreaker(
            name="reset_test",
            failure_threshold=3,
        )
        breaker.failure_count = 2  # Simulate previous failures

        client = OllamaClient(
            base_url="http://test:11434",
            retry_policy=retry_policy,
            circuit_breaker=breaker,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"model": "test", "message": {"content": "OK"}}

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_client:
            mock_http_client = MagicMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_http_client

            await client._request_with_retry("POST", "/api/chat", {})

            # Failure count should be reset
            assert breaker.failure_count == 0
