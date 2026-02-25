"""
Ollama HTTP client for the Teiken Claw agent system.

This module provides an async HTTP client for communicating with the Ollama API,
supporting chat completions, embeddings, and model management.

Key Features:
    - Async HTTP using httpx
    - Automatic retry with exponential backoff
    - Circuit breaker protection
    - Timeout handling
    - Error classification (transport vs permanent)
    - Tool calling support

Usage:
    client = OllamaClient()

    # Chat completion
    response = await client.chat(
        messages=[{"role": "user", "content": "Hello!"}],
        model="llama3.2"
    )

    # Get embeddings
    embedding = await client.embeddings("Hello, world!")

    # List available models
    models = await client.list_models()
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config.settings import settings
from app.agent.errors import (
    OllamaTransportError,
    OllamaResponseError,
    OllamaModelError,
)
from app.agent.retries import (
    RetryPolicy,
    exponential_backoff_with_jitter,
    OLLAMA_CHAT_RETRY_POLICY,
    OLLAMA_EMBED_RETRY_POLICY,
)
from app.agent.circuit_breaker import (
    CircuitBreaker,
    circuit_breaker_protect,
    get_ollama_circuit_breaker,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class ChatMessage:
    """Represents a chat message."""

    def __init__(
        self,
        role: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
    ):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API requests."""
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        """Create from API response dictionary."""
        return cls(
            role=data.get("role", "assistant"),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
        )


class ChatResponse:
    """Represents a chat completion response."""

    def __init__(
        self,
        model: str,
        message: ChatMessage,
        done: bool,
        total_duration_ns: Optional[int] = None,
        eval_count: Optional[int] = None,
        prompt_eval_count: Optional[int] = None,
        raw_response: Optional[dict[str, Any]] = None,
    ):
        self.model = model
        self.message = message
        self.done = done
        self.total_duration_ns = total_duration_ns
        self.eval_count = eval_count
        self.prompt_eval_count = prompt_eval_count
        self.raw_response = raw_response

    @property
    def total_duration_sec(self) -> Optional[float]:
        """Total duration in seconds."""
        if self.total_duration_ns is None:
            return None
        return self.total_duration_ns / 1_000_000_000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatResponse":
        """Create from API response dictionary."""
        message_data = data.get("message", {})
        return cls(
            model=data.get("model", ""),
            message=ChatMessage.from_dict(message_data),
            done=data.get("done", True),
            total_duration_ns=data.get("total_duration"),
            eval_count=data.get("eval_count"),
            prompt_eval_count=data.get("prompt_eval_count"),
            raw_response=data,
        )


class EmbeddingResponse:
    """Represents an embedding response."""

    def __init__(
        self,
        embedding: list[float],
        model: str,
        raw_response: Optional[dict[str, Any]] = None,
    ):
        self.embedding = embedding
        self.model = model
        self.raw_response = raw_response

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmbeddingResponse":
        """Create from API response dictionary."""
        return cls(
            embedding=data.get("embedding", []),
            model=data.get("model", ""),
            raw_response=data,
        )


class ModelInfo:
    """Represents information about an Ollama model."""

    def __init__(
        self,
        name: str,
        size: Optional[int] = None,
        digest: Optional[str] = None,
        modified_at: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        self.name = name
        self.size = size
        self.digest = digest
        self.modified_at = modified_at
        self.details = details

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelInfo":
        """Create from API response dictionary."""
        return cls(
            name=data.get("name", ""),
            size=data.get("size"),
            digest=data.get("digest"),
            modified_at=data.get("modified_at"),
            details=data.get("details"),
        )


# =============================================================================
# Ollama Client
# =============================================================================


class OllamaClient:
    """
    Async HTTP client for the Ollama API.

    This client provides methods for chat completions, embeddings, and model
    management. It includes automatic retry with exponential backoff and
    circuit breaker protection.

    Attributes:
        base_url: The base URL for the Ollama API.
        timeout_sec: Request timeout in seconds.
        chat_model: Default model for chat completions.
        embed_model: Default model for embeddings.
        circuit_breaker: Circuit breaker for fault tolerance.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        chat_model: Optional[str] = None,
        embed_model: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        """
        Initialize the Ollama client.

        Args:
            base_url: Ollama API base URL (default from settings).
            timeout_sec: Request timeout in seconds (default from settings).
            chat_model: Default chat model (default from settings).
            embed_model: Default embedding model (default from settings).
            retry_policy: Retry policy for requests.
            circuit_breaker: Circuit breaker instance.
        """
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.timeout_sec = timeout_sec or settings.OLLAMA_TIMEOUT_SEC
        self.chat_model = chat_model or settings.OLLAMA_CHAT_MODEL
        self.embed_model = embed_model or settings.OLLAMA_EMBED_MODEL
        self.retry_policy = retry_policy or OLLAMA_CHAT_RETRY_POLICY

        # Get or create circuit breaker
        if circuit_breaker:
            self.circuit_breaker = circuit_breaker
        else:
            self.circuit_breaker = get_ollama_circuit_breaker(
                failure_threshold=getattr(
                    settings, "OLLAMA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5
                ),
                success_threshold=getattr(
                    settings, "OLLAMA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD", 1
                ),
                timeout_sec=getattr(
                    settings, "OLLAMA_CIRCUIT_BREAKER_TIMEOUT_SEC", 60.0
                ),
            )

        # HTTP client (created lazily)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_sec),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "OllamaClient":
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint."""
        return f"{self.base_url}{endpoint}"

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict[str, Any]] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry and circuit breaker protection.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path.
            json_data: JSON body for POST requests.
            retry_policy: Retry policy to use.

        Returns:
            Parsed JSON response.

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open.
            OllamaTransportError: If network/timeout error occurs.
            OllamaResponseError: If response is invalid.
            OllamaModelError: If model is not found.
        """
        policy = retry_policy or self.retry_policy
        last_error: Optional[Exception] = None

        for attempt in range(policy.max_attempts):
            # Check circuit breaker
            if attempt == 0 and not self.circuit_breaker.can_execute():
                from app.agent.errors import CircuitBreakerOpenError

                raise CircuitBreakerOpenError(
                    message="Ollama circuit breaker is open",
                    breaker_name=self.circuit_breaker.name,
                    failure_count=self.circuit_breaker.failure_count,
                    timeout_sec=self.circuit_breaker.timeout_sec,
                )

            try:
                client = await self._get_client()
                url = self._build_url(endpoint)

                logger.debug(
                    f"Ollama API request: {method} {endpoint}",
                    extra={"method": method, "endpoint": endpoint, "attempt": attempt + 1},
                )

                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                )

                # Test/compatibility path: callers may provide a parsed dict.
                if isinstance(response, dict):
                    self.circuit_breaker.record_success()
                    return response

                # Check for HTTP errors
                if response.status_code >= 500:
                    # Server error - retryable
                    self.circuit_breaker.record_failure()
                    raise OllamaTransportError(
                        message=f"Ollama server error: {response.status_code}",
                        endpoint=endpoint,
                        details={"status_code": response.status_code},
                    )

                if response.status_code == 404:
                    # Not found - could be model not found
                    self.circuit_breaker.record_failure()
                    error_body = response.text[:500] if response.text else ""
                    raise OllamaModelError(
                        message="Resource or model not found",
                        model_name=json_data.get("model") if json_data else None,
                        details={"status_code": 404, "response": error_body},
                    )

                if response.status_code >= 400:
                    # Client error - permanent
                    self.circuit_breaker.record_failure()
                    raise OllamaResponseError(
                        message=f"Ollama client error: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text[:500] if response.text else None,
                    )

                # Parse response
                try:
                    result = response.json()
                except Exception as e:
                    self.circuit_breaker.record_failure()
                    raise OllamaResponseError(
                        message=f"Failed to parse Ollama response: {e}",
                        response_body=response.text[:500] if response.text else None,
                    )

                # Success
                self.circuit_breaker.record_success()
                return result

            except OllamaTransportError as e:
                last_error = e
                if attempt < policy.max_attempts - 1:
                    delay = exponential_backoff_with_jitter(attempt, policy)
                    logger.warning(
                        f"Ollama transport error, retrying in {delay:.2f}s: {e}",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": policy.max_attempts,
                            "delay_sec": delay,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

            except (OllamaResponseError, OllamaModelError):
                # Permanent errors - don't retry
                raise

            except httpx.TimeoutException as e:
                self.circuit_breaker.record_failure()
                last_error = OllamaTransportError(
                    message=f"Ollama request timed out: {e}",
                    endpoint=endpoint,
                    timeout=True,
                )
                if attempt < policy.max_attempts - 1:
                    delay = exponential_backoff_with_jitter(attempt, policy)
                    logger.warning(
                        f"Ollama timeout, retrying in {delay:.2f}s",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": policy.max_attempts,
                            "delay_sec": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    raise last_error

            except httpx.NetworkError as e:
                self.circuit_breaker.record_failure()
                last_error = OllamaTransportError(
                    message=f"Ollama network error: {e}",
                    endpoint=endpoint,
                )
                if attempt < policy.max_attempts - 1:
                    delay = exponential_backoff_with_jitter(attempt, policy)
                    logger.warning(
                        f"Ollama network error, retrying in {delay:.2f}s: {e}",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": policy.max_attempts,
                            "delay_sec": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    raise last_error

        # Should not reach here
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state in Ollama client retry logic")

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        options: Optional[dict[str, Any]] = None,
        stream: bool = False,
    ) -> ChatResponse:
        """
        Send a chat completion request to Ollama.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Model to use (default from settings).
            tools: List of tool definitions for function calling.
            options: Additional model options (temperature, etc.).
            stream: Whether to stream the response (not implemented for v1).

        Returns:
            ChatResponse with the assistant's message.

        Raises:
            OllamaTransportError: If network/timeout error occurs.
            OllamaResponseError: If response is invalid.
            OllamaModelError: If model is not found.

        Example:
            >>> response = await client.chat(
            ...     messages=[{"role": "user", "content": "Hello!"}],
            ...     model="llama3.2"
            ... )
            >>> print(response.message.content)
        """
        if stream:
            logger.warning("Streaming not implemented for v1, using non-streaming")

        request_body: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            request_body["tools"] = tools

        if options:
            request_body["options"] = options

        logger.debug(
            f"Sending chat request to Ollama",
            extra={
                "model": request_body["model"],
                "message_count": len(messages),
                "has_tools": tools is not None,
            },
        )

        response_data = await self._request_with_retry(
            method="POST",
            endpoint="/api/chat",
            json_data=request_body,
            retry_policy=OLLAMA_CHAT_RETRY_POLICY,
        )

        return ChatResponse.from_dict(response_data)

    async def embeddings(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> EmbeddingResponse:
        """
        Get embeddings for text from Ollama.

        Args:
            text: Text to embed.
            model: Model to use (default from settings).

        Returns:
            EmbeddingResponse with the embedding vector.

        Raises:
            OllamaTransportError: If network/timeout error occurs.
            OllamaResponseError: If response is invalid.
            OllamaModelError: If model is not found.

        Example:
            >>> response = await client.embeddings("Hello, world!")
            >>> print(len(response.embedding))
            768
        """
        request_body = {
            "model": model or self.embed_model,
            "prompt": text,
        }

        logger.debug(
            f"Sending embeddings request to Ollama",
            extra={
                "model": request_body["model"],
                "text_length": len(text),
            },
        )

        response_data = await self._request_with_retry(
            method="POST",
            endpoint="/api/embeddings",
            json_data=request_body,
            retry_policy=OLLAMA_EMBED_RETRY_POLICY,
        )

        return EmbeddingResponse.from_dict(response_data)

    async def list_models(self) -> list[ModelInfo]:
        """
        List available models in Ollama.

        Returns:
            List of ModelInfo objects for each available model.

        Raises:
            OllamaTransportError: If network/timeout error occurs.
            OllamaResponseError: If response is invalid.

        Example:
            >>> models = await client.list_models()
            >>> for model in models:
            ...     print(model.name)
        """
        response_data = await self._request_with_retry(
            method="GET",
            endpoint="/api/tags",
        )

        models = []
        for model_data in response_data.get("models", []):
            models.append(ModelInfo.from_dict(model_data))

        return models

    async def check_health(self) -> dict[str, Any]:
        """
        Check if Ollama is healthy and accessible.

        Returns:
            Dictionary with health status and available models.

        Example:
            >>> health = await client.check_health()
            >>> print(health["status"])
            "healthy"
        """
        try:
            models = await self.list_models()
            return {
                "status": "healthy",
                "base_url": self.base_url,
                "model_count": len(models),
                "models": [m.name for m in models],
                "circuit_breaker": self.circuit_breaker.get_status(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "base_url": self.base_url,
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.get_status(),
            }

    def get_status(self) -> dict[str, Any]:
        """
        Get client status for health checks.

        Returns:
            Dictionary with client configuration and circuit breaker status.
        """
        return {
            "base_url": self.base_url,
            "chat_model": self.chat_model,
            "embed_model": self.embed_model,
            "timeout_sec": self.timeout_sec,
            "circuit_breaker": self.circuit_breaker.get_status(),
        }


# =============================================================================
# Global Client Instance
# =============================================================================

_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """
    Get or create the global Ollama client instance.

    Returns:
        The global OllamaClient instance.
    """
    global _ollama_client

    if _ollama_client is None:
        _ollama_client = OllamaClient()
        logger.info(
            f"Created Ollama client: base_url={settings.OLLAMA_BASE_URL}, "
            f"chat_model={settings.OLLAMA_CHAT_MODEL}"
        )

    return _ollama_client


def reset_ollama_client() -> None:
    """Reset the global Ollama client (for testing)."""
    global _ollama_client

    if _ollama_client is not None:
        # Note: Can't await close here, caller should handle cleanup
        _ollama_client = None
